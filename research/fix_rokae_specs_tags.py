"""
fix_rokae_specs_tags.py
-----------------------
Fixes missing specs (payload_kg, reach_mm, repeatability_mm, dof, weight_kg)
and tags for all ROKAE robots (company 1416).

Strategy (in priority order):
  1. Parse specs directly from model_name (e.g. "CR7-7/0.98C" → payload=7, reach=980)
  2. Scrape the official ROKAE EN product page spec table for the variant row
  3. Fall back to family-level defaults from the scraped page

Tags are derived from robot category (cobot vs industrial) and family.

Usage:
  python fix_rokae_specs_tags.py [--dry-run] [--company-id 1416]
"""

import argparse
import io
import json
import os
import re
import sys
import time

# Fix Windows cp1252 encoding errors when printing Chinese characters
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient
from web_extract import parse_page, WebFetcher

COMPANY_ID = 1416

# ---------------------------------------------------------------------------
# ROKAE product page URLs by family (used for scraping spec tables)
# ---------------------------------------------------------------------------
FAMILY_PAGES = {
    "CR":  "https://www.rokae.com/en/product/show/545/xMateCR.html",
    "SR":  "https://www.rokae.com/en/product/show/349/SR-Cobots.html",
    "ER":  "https://www.rokae.com/en/product/show/349/SR-Cobots.html",
    "NB25h": "https://www.rokae.com/en/product/show/560/NB25h.html",
    "NB25":  "https://www.rokae.com/en/product/show/515/NB25.html",
    "NB80":  "https://www.rokae.com/en/product/show/516/NB80.html",
    "NB":    "https://www.rokae.com/en/product/show/515/NB25.html",  # fallback
    "XB":    "https://www.rokae.com/en/product/show/517/XB.html",
}

# ---------------------------------------------------------------------------
# Tags by robot family/type
# ---------------------------------------------------------------------------
FAMILY_TAGS = {
    "CR": ["Collaborative Robot", "Cobot", "Robot Arm", "6-DOF", "Industrial Automation"],
    "SR": ["Collaborative Robot", "Cobot", "SCARA Robot", "Robot Arm", "Assembly"],
    "ER": ["Collaborative Robot", "Cobot", "Robot Arm", "6-DOF", "Extended Reach"],
    "NB": ["Industrial Robot", "Robot Arm", "6-DOF", "High Payload", "Industrial Automation"],
    "XB": ["Industrial Robot", "Robot Arm", "6-DOF", "Industrial Automation"],
}

# ---------------------------------------------------------------------------
# Hardcoded specs for Chinese series-level robots (no parseable model code)
# ---------------------------------------------------------------------------
CHINESE_SERIES_SPECS = {
    # NB industrial series
    "NB80系列":   {"payload_kg": 80.0,  "reach_mm": 2100.0, "dof": 6, "weight_kg": 560.0},
    "NB185系列":  {"payload_kg": 185.0, "reach_mm": 2800.0, "dof": 6},
    "NB220系列":  {"payload_kg": 220.0, "reach_mm": 2800.0, "dof": 6},
    "NB80":      {"payload_kg": 80.0,  "reach_mm": 2100.0, "dof": 6, "weight_kg": 560.0},
    "NB25h系列":  {"payload_kg": 25.0,  "reach_mm": 2258.0, "dof": 6},
    "NB25h":     {"payload_kg": 25.0,  "reach_mm": 2258.0, "dof": 6},
    "NB25系列":   {"payload_kg": 25.0,  "reach_mm": 2013.0, "dof": 6},
    "NB25":      {"payload_kg": 25.0,  "reach_mm": 2013.0, "dof": 6},
    "NB12h系列":  {"payload_kg": 12.0,  "reach_mm": 1440.0, "dof": 6},
    "NB12系列":   {"payload_kg": 12.0,  "reach_mm": 1440.0, "dof": 6},
    "NB10系列":   {"payload_kg": 10.0,  "reach_mm": 1450.0, "dof": 6},
    "NB4系列":    {"payload_kg": 4.0,   "reach_mm": 580.0,  "dof": 6},
    # SCARA
    "SCARA系列":  {"payload_kg": 5.0,   "reach_mm": 650.0,  "dof": 4},
    # SR cobot variants
    "SR3-C-H":   {"payload_kg": 3.0,   "reach_mm": 700.0,  "dof": 6},
    # xMate Pro series (older cobot branding)
    "xMate3 Pro": {"payload_kg": 3.0,  "reach_mm": 700.0,  "dof": 6},
    "xMate6 Pro": {"payload_kg": 6.0,  "reach_mm": 900.0,  "dof": 6},
    "xMate7 Pro": {"payload_kg": 7.0,  "reach_mm": 980.0,  "dof": 6},
    # XB industrial
    "XB7 Series": {"payload_kg": 7.0,  "reach_mm": 927.0,  "dof": 6},
    "XB7":        {"payload_kg": 7.0,  "reach_mm": 927.0,  "dof": 6},
    # Short names without suffix
    "NB12h":      {"payload_kg": 12.0, "reach_mm": 1440.0, "dof": 6},
    "NB12":       {"payload_kg": 12.0, "reach_mm": 1440.0, "dof": 6},
    "NB10":       {"payload_kg": 10.0, "reach_mm": 1450.0, "dof": 6},
    "NB4":        {"payload_kg": 4.0,  "reach_mm": 580.0,  "dof": 6},
    # ER series (7-axis flexible cobots) — specs from official ROKAE site
    # ER3: payload 3 kg, reach 1010 mm, 6-DOF (source: encycam.com/rokae-xmate-er3)
    # ER7 Pro-M: payload 7 kg, reach 850 mm, 7-DOF (source: rokae.com case studies)
    "ER3":        {"payload_kg": 3.0,  "reach_mm": 1010.0, "dof": 6, "repeatability_mm": 0.03},
    "ER3 Pro-M":  {"payload_kg": 3.0,  "reach_mm": 1010.0, "dof": 6, "repeatability_mm": 0.03},
    "ER7 Pro-M":  {"payload_kg": 7.0,  "reach_mm": 850.0,  "dof": 7, "repeatability_mm": 0.03},
}

# ---------------------------------------------------------------------------
# model_name parser: "CR7-7/0.98C" → {payload_kg:7, reach_mm:980, dof:6}
# Format: {FAMILY}{n}-{payload}/{reach}C[-{variant}]
# ---------------------------------------------------------------------------
MODEL_NAME_RE = re.compile(
    r"^(?P<family>[A-Z]+\d*)-(?P<payload>[\d.]+)/(?P<reach>[\d.]+)[A-Z]",
    re.IGNORECASE,
)

def parse_model_name(model_name: str) -> dict:
    """Extract payload_kg and reach_mm from ROKAE model name string."""
    m = MODEL_NAME_RE.match(model_name or "")
    if not m:
        return {}
    specs = {}
    try:
        specs["payload_kg"] = float(m.group("payload"))
    except ValueError:
        pass
    try:
        reach_m = float(m.group("reach"))
        specs["reach_mm"] = round(reach_m * 1000)
    except ValueError:
        pass
    specs["dof"] = 6  # all ROKAE arms are 6-DOF
    return specs


# ---------------------------------------------------------------------------
# Spec table scraper: parse the HTML spec table from a ROKAE product page
# Returns a dict keyed by model variant string, e.g. "CR7-7/0.98C": {...}
# ---------------------------------------------------------------------------
_fetcher: WebFetcher | None = None

def get_fetcher() -> WebFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = WebFetcher()
    return _fetcher


def scrape_spec_table(url: str) -> dict[str, dict]:
    """
    Scrape the spec table from a ROKAE product page.
    Returns {model_variant: {payload_kg, reach_mm, repeatability_mm, weight_kg, dof}}
    """
    try:
        page = parse_page(get_fetcher(), url)
        if page is None:
            print(f"  [scrape] parse_page returned None for {url}")
            return {}
        if isinstance(page, str):
            text = page
        else:
            text = getattr(page, "text", "") or getattr(page, "markdown", "") or str(page)
    except Exception as e:
        print(f"  [scrape] Failed to fetch {url}: {e}")
        return {}

    results = {}

    # Find spec table blocks — look for lines like "Payload | X kg | Weight | Y kg | Reach | Z mm"
    # The markdown table format from parse_page uses | separators
    lines = text.splitlines()
    current_variant = None

    for i, line in enumerate(lines):
        # Detect variant header lines like "CR7-7/0.98C Specifications" or "## CR7-7/0.98C"
        variant_match = re.search(
            r"\b((?:CR|SR|ER|NB|XB)[\w\-/\.]+(?:C|H)?(?:-\d+)?)\s*(?:Specifications?|Specs?)?",
            line, re.IGNORECASE
        )
        if variant_match and "Specification" in line:
            current_variant = variant_match.group(1).strip()
            if current_variant not in results:
                results[current_variant] = {}

        # Parse spec table rows
        if "|" in line and current_variant:
            cells = [c.strip() for c in line.split("|") if c.strip()]

            # Walk pairs: label, value, label, value ...
            for j in range(0, len(cells) - 1, 2):
                label = cells[j].lower()
                value = cells[j + 1] if j + 1 < len(cells) else ""

                if "payload" in label:
                    m = re.search(r"([\d.]+)\s*kg", value, re.IGNORECASE)
                    if m:
                        results[current_variant]["payload_kg"] = float(m.group(1))

                elif "reach" in label or "radius" in label:
                    m = re.search(r"([\d.]+)\s*mm", value, re.IGNORECASE)
                    if m:
                        results[current_variant]["reach_mm"] = float(m.group(1))

                elif "repeatability" in label:
                    m = re.search(r"±?\s*([\d.]+)\s*mm", value, re.IGNORECASE)
                    if m:
                        results[current_variant]["repeatability_mm"] = float(m.group(1))

                elif "weight" in label and "payload" not in label:
                    m = re.search(r"([\d.]+)\s*kg", value, re.IGNORECASE)
                    if m:
                        results[current_variant]["weight_kg"] = float(m.group(1))

                elif "dof" in label or "degrees of freedom" in label:
                    m = re.search(r"(\d+)", value)
                    if m:
                        results[current_variant]["dof"] = int(m.group(1))

    return results


def get_family(model_name: str) -> str:
    """Extract family prefix from model name."""
    m = re.match(r"^([A-Z]+)", model_name or "", re.IGNORECASE)
    return m.group(1).upper() if m else ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Fix specs and tags for ROKAE robots")
    parser.add_argument("--company-id", type=int, default=COMPANY_ID)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = client.list_robots_for_company(args.company_id)
    print(f"Fetched {len(robots)} robots for company {args.company_id}")

    # Pre-scrape spec tables per family page (cache to avoid re-fetching)
    scraped_tables: dict[str, dict] = {}

    fixed = skipped = failed = 0
    results_log = []

    for robot in robots:
        rid        = robot["id"]
        name       = robot.get("name", f"Robot {rid}")
        model_name = robot.get("model_name", "")
        url        = robot.get("url", "")
        current_tags = robot.get("tags") or []

        # Check what's already set
        has_payload = robot.get("payload_kg") is not None
        has_reach   = robot.get("reach_mm") is not None
        has_repeat  = robot.get("repeatability_mm") is not None
        has_dof     = robot.get("dof") is not None
        has_tags    = bool(current_tags)

        needs_specs = not (has_payload and has_reach)
        needs_tags  = not has_tags

        if not needs_specs and not needs_tags:
            print(f"[{rid}] {name} — already complete, skipping")
            skipped += 1
            continue

        print(f"\n[{rid}] {name}")
        print(f"  model_name={model_name!r}  needs_specs={needs_specs}  needs_tags={needs_tags}")

        patch = {}

        # ---- SPECS ----
        if needs_specs:
            # Tier 0: hardcoded for Chinese series-level robots
            if model_name in CHINESE_SERIES_SPECS:
                hardcoded = CHINESE_SERIES_SPECS[model_name]
                print(f"  [hardcoded] {hardcoded}")
                patch.update(hardcoded)
                needs_specs = False

            # Tier 1: parse from model_name
            parsed = parse_model_name(model_name) if needs_specs else {}
            if needs_specs and parsed.get("payload_kg") and parsed.get("reach_mm"):
                print(f"  [model_name] payload={parsed['payload_kg']}kg  reach={parsed['reach_mm']}mm")
                patch.update(parsed)
            elif needs_specs:
                # Tier 2: scrape product page
                family = get_family(model_name)
                # Pick the right page key
                page_key = None
                for k in ["NB25h", "NB25", "NB80", "NB", "CR", "SR", "ER", "XB"]:
                    if model_name.upper().startswith(k.upper()):
                        page_key = k
                        break

                if page_key and page_key in FAMILY_PAGES:
                    page_url = FAMILY_PAGES[page_key]
                    if page_url not in scraped_tables:
                        print(f"  [scrape] Fetching spec table from {page_url}")
                        scraped_tables[page_url] = scrape_spec_table(page_url)
                        time.sleep(0.5)

                    table = scraped_tables.get(page_url, {})
                    # Try to find the exact variant
                    variant_specs = None
                    for variant_key, variant_data in table.items():
                        if model_name.upper() in variant_key.upper() or variant_key.upper() in model_name.upper():
                            variant_specs = variant_data
                            print(f"  [scrape] Matched variant {variant_key!r}: {variant_data}")
                            break

                    if not variant_specs and table:
                        # Use first entry as family-level fallback
                        first_key = next(iter(table))
                        variant_specs = table[first_key]
                        print(f"  [scrape] Using family fallback {first_key!r}: {variant_specs}")

                    if variant_specs:
                        patch.update(variant_specs)
                    else:
                        print(f"  [WARN] No spec data found for {model_name!r}")

        # ---- TAGS ----
        if needs_tags:
            family = get_family(model_name)
            # Map to tag set
            tag_key = None
            for k in ["CR", "SR", "ER", "NB", "XB"]:
                if model_name.upper().startswith(k):
                    tag_key = k
                    break
            tags = FAMILY_TAGS.get(tag_key, ["Robot Arm", "Industrial Automation"])
            print(f"  [tags] Assigning: {tags}")
            patch["tags"] = tags

        if not patch:
            print(f"  [SKIP] Nothing to patch")
            skipped += 1
            continue

        print(f"  -> Patch: {patch}")

        if args.dry_run:
            print(f"  [DRY RUN] Would PATCH robot {rid}")
            fixed += 1
            results_log.append({"id": rid, "name": name, "patch": patch, "status": "dry_run"})
        else:
            try:
                client._patch(f"robots/robots/{rid}/", patch)
                print(f"  [OK] Patched robot {rid}")
                fixed += 1
                results_log.append({"id": rid, "name": name, "patch": patch, "status": "ok"})
            except Exception as e:
                print(f"  [ERROR] Failed to patch robot {rid}: {e}")
                failed += 1
                results_log.append({"id": rid, "name": name, "patch": patch, "status": "error", "error": str(e)})

    print(f"\n{'='*60}")
    print(f"Summary: fixed={fixed}, skipped={skipped}, failed={failed}")

    out_path = os.path.join(
        os.path.dirname(__file__), "staging", "reports",
        f"specs_tags_fix_company_{args.company_id}.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"fixed": fixed, "skipped": skipped, "failed": failed, "results": results_log},
                  f, indent=2, ensure_ascii=False)
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
