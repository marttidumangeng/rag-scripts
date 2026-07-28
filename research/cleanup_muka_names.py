#!/usr/bin/env python3
"""
cleanup_muka_names.py
=====================
Clean up robot names and family names for Xiamen MUKA (Company 1480).

Problem:
  Many robots were originally imported from made-in-china.com or with
  URL-slug-derived names (e.g. "High-Performance 6-Axis 20kg Industrial
  Collaborative Robot Arm Cobot Palletizing Welding Robot with Comprehensive
  Application Solutions"). These are SEO product listing titles, not real
  robot names.

Strategy:
  1. Fetch all robots for company 1480 from the API.
  2. For each robot with a bad name (too long, or matches known bad patterns):
       a. If the robot has a muka-tech.com URL, fetch that page and extract
          the clean product name from the <h1> or <title>.
       b. If the robot has a made-in-china.com URL or no URL, derive a short
          clean name from the model_name field (e.g. "M20" -> "Muka M20").
  3. Derive a family name from the clean name using the model code prefix.
  4. PATCH the robot via the API with the new name and family_name.

Usage:
  python cleanup_muka_names.py [--dry-run] [--company-id 1480]

Options:
  --dry-run     Print what would be changed without making API calls.
  --company-id  Company ID to clean (default: 1480).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
load_research_env()

from api_client import ResearchApiClient
from web_extract import WebFetcher, parse_page

# ---------------------------------------------------------------------------
# Heuristics for detecting bad names
# ---------------------------------------------------------------------------

# Names longer than this are almost certainly SEO titles, not real names
MAX_GOOD_NAME_LEN = 80

# Patterns that indicate a name is a product listing title, not a robot name
BAD_NAME_PATTERNS = [
    r"\bIntelligent\b.*\bRobot\b.*\bWith\b",
    r"\bHigh[- ]Performance\b",
    r"\bComprehensive Application\b",
    r"\bApplication Solutions\b",
    r"\bWelding Robot with\b",
    r"\bCobot Palletizing\b",
    r"[|].*\bUltra[- ]Light\b",          # "Muka FIT-U ... | Lightweight with..."
    r"[|].*\bPortable and Easy\b",
    r"[|].*\bWidely Applic",
    r"[|].*\bStrong Assistance\b",
    r"[|].*\bWith \d+kg\b",
    r"[|].*\bLightweight\b",              # pipe-separated tagline still present
    r"\buum Clean And Efficient\b",        # corrupted slug artifact
    r"\bButlerBot\b",                      # slug collision artifact
    r"\bQbing\b",                          # slug collision artifact
    r"\bSCANNING-ROBOT\b",                 # uppercase slug leaked into name
    r"\bCLEANING-BUTLER\b",
    r"\|t\s+\u2014\u2014",                 # corrupted pipe truncation artifact
    r"\|t\s+——",                 # same with actual em-dashes
    r"Robot\s+\|t\b",                      # "Robot |t" truncation artifact
    r"\buum\b",                            # slug corruption artifact
    r"\bEHABILITACION\b",                  # Spanish slug leaked into family_name
    r"MUKA-AKSO-\d+",                      # slug collision in family_name
    r"APRENDIZAJE",                        # Spanish slug artifact
]

BAD_FAMILY_PATTERNS = [
    r"EHABILITACION",
    r"MUKA-AKSO-\d+",
    r"APRENDIZAJE",
    r"BUTLERBOT",
    r"QBING",
    r"SCANNING-ROBOT",
    r"CLEANING-BUTLER",
    r"[A-Z]{3,}-[A-Z]{3,}-[A-Z]{3,}",    # multi-word uppercase slug
    r"EPIC-[A-Z]FIT",                      # two families concatenated: "EPIC-AFIT-GS-ULTRA"
    r"FIT-[A-Z0-9]+-[A-Z]+[A-Z]{3,}",    # FIT-GS-ULTRAEHABILITACION etc.
]

_BAD_FAMILY_RE = re.compile("|".join(BAD_FAMILY_PATTERNS), re.IGNORECASE)

_BAD_RE = re.compile("|".join(BAD_NAME_PATTERNS), re.IGNORECASE)


def is_bad_name(name: str) -> bool:
    """Return True if the name looks like an SEO title or slug artifact."""
    if len(name) > MAX_GOOD_NAME_LEN:
        return True
    if _BAD_RE.search(name):
        return True
    # Uppercase slug leaked into name field (e.g. "6-METER-PLASTERING-ROBOT")
    if re.search(r"[A-Z]{3,}-[A-Z]{3,}", name):
        return True
    return False


# ---------------------------------------------------------------------------
# Name derivation from a fetched product page
# ---------------------------------------------------------------------------

def _clean_muka_title(raw: str) -> str:
    """Strip site suffix and pipe-separated marketing taglines from a page title."""
    # "Muka EPIC-A Passive Arm Support Exoskeleton | 1.9kg Ultra-Light Carbon Fiber - Muka Tech"
    # -> "Muka EPIC-A Passive Arm Support Exoskeleton"
    # Strip trailing site name
    for sep in (" - Muka Tech", " – Muka Tech", " | Muka Tech", " - Xiamen Muka", " – Xiamen Muka"):
        if sep.lower() in raw.lower():
            raw = raw[: raw.lower().index(sep.lower())].strip()
    # Strip pipe-separated marketing suffix (keep only the first segment)
    if "|" in raw:
        raw = raw.split("|")[0].strip()
    return raw.strip()


def _h1_from_page(page) -> str:
    """Extract the first <h1> text from a PageContent object."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page.html, "html.parser")
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def strip_pipe_tagline(name: str) -> str:
    """Strip a pipe-separated marketing tagline from a name.
    e.g. 'Muka FIT-U Upper Limb Exoskeleton Robot | Lightweight' -> 'Muka FIT-U Upper Limb Exoskeleton Robot'
    Also strips trailing ' | ' or '| ' artifacts.
    """
    if "|" not in name:
        return name
    clean = name.split("|")[0].strip().rstrip(",;:")
    return clean if len(clean) >= 5 else name


def derive_name_from_page(page, old_name: str, model_name: str) -> str:
    """
    Try to extract a clean robot name from the fetched product page.
    Priority: H1 > cleaned title > model_name fallback.
    """
    h1 = _h1_from_page(page)
    title = _clean_muka_title(page.title or "")

    # H1 is usually the cleanest: "EPIC-A Passive Arm Support Exoskeleton"
    # Prefix "Muka" if it's not already there and doesn't start with a number
    if h1 and 5 < len(h1) < 100 and not is_bad_name(h1):
        if not h1.lower().startswith("muka") and not re.match(r"^\d", h1):
            h1 = f"Muka {h1}"
        return h1

    # Cleaned title is second best
    if title and 5 < len(title) < 100 and not is_bad_name(title):
        if not title.lower().startswith("muka") and not re.match(r"^\d", title):
            title = f"Muka {title}"
        return title

    return ""


# ---------------------------------------------------------------------------
# Family name derivation
# ---------------------------------------------------------------------------

# Known MUKA product families — maps model code prefix to family name
_FAMILY_MAP = {
    "EPIC": "EPIC Series",
    "FIT":  "FIT Series",
    "AKSO": "AKSO Series",
    "TN":   "TN Series",
    "DT":   "DT Series",
    "A0":   "A Series",
    "A1":   "A Series",
    "A2":   "A Series",
    "M":    "M Series",
}

_MODEL_CODE_RE = re.compile(
    r"\b(EPIC-[A-Z0-9]+|FIT-[A-Z0-9\-]+|AKSO-\d+|TN\d+|DT\d+|A\d+|M\d+)\b",
    re.IGNORECASE,
)


def derive_family_name(clean_name: str, model_name: str) -> str:
    """Derive a short family name from the clean robot name or model_name."""
    for src in (clean_name, model_name):
        m = _MODEL_CODE_RE.search(src or "")
        if m:
            code = m.group(1).upper()
            # Try longest prefix match first
            for prefix in sorted(_FAMILY_MAP, key=len, reverse=True):
                if code.startswith(prefix):
                    return _FAMILY_MAP[prefix]
            # No map entry — use the code itself as the family name
            # Strip trailing digits to get the series root (e.g. "TN10" -> "TN Series")
            root = re.sub(r"\d+$", "", code).rstrip("-")
            if root and len(root) >= 2:
                return f"{root} Series"
    return ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print changes without applying them")
    parser.add_argument("--company-id", type=int, default=1480, help="Company ID to clean (default: 1480)")
    args = parser.parse_args()

    client = ResearchApiClient()
    fetcher = WebFetcher()

    company_id = args.company_id
    dry_run = args.dry_run

    print(f"Fetching robots for company {company_id}...")
    robots = client.list_robots_for_company(company_id)
    print(f"Found {len(robots)} robots.")
    if dry_run:
        print("[DRY RUN] No changes will be written.\n")

    skipped = 0
    to_update: list[dict] = []

    for r in robots:
        rid = r.get("id")
        old_name = (r.get("name") or "").strip()
        old_family = (r.get("family_name") or "").strip()
        model_name = (r.get("model_name") or "").strip()
        url = (r.get("url") or "").strip()

        name_bad = is_bad_name(old_name)
        family_bad = bool(old_family) and _BAD_FAMILY_RE.search(old_family)
        if not name_bad and not family_bad:
            skipped += 1
            continue

        print(f"\nID {rid}: {old_name[:80]}")

        new_name = ""
        new_family = ""

        # --- Fast pass: strip pipe-separated tagline from name ---
        if name_bad and "|" in old_name:
            stripped = strip_pipe_tagline(old_name)
            if stripped and not is_bad_name(stripped):
                new_name = stripped
                print(f"  [pipe-strip] -> {new_name}")

        # --- Try to fetch the official product page (skip if pipe-strip already gave us a clean name) ---
        if not new_name and "muka-tech.com" in url:
            try:
                page = parse_page(fetcher, url)
                if page:
                    new_name = derive_name_from_page(page, old_name, model_name)
                    if new_name:
                        print(f"  [page] -> {new_name}")
            except Exception as exc:
                print(f"  [page] fetch error: {exc}")

        # --- Fallback: use model_name if it's short and clean ---
        if not new_name:
            if model_name and len(model_name) <= 20 and not is_bad_name(model_name):
                # e.g. "M20" -> "Muka M20"
                if not model_name.lower().startswith("muka"):
                    new_name = f"Muka {model_name}"
                else:
                    new_name = model_name
                print(f"  [model] -> {new_name}")
            else:
                # Last resort: take the first 6 words of the old name
                words = old_name.split()
                new_name = " ".join(words[:6]).rstrip(",;:")
                if not new_name.lower().startswith("muka") and not re.match(r"^\d", new_name):
                    new_name = f"Muka {new_name}"
                print(f"  [trunc] -> {new_name}")

        # --- Derive family name ---
        new_family = derive_family_name(new_name, model_name)
        if new_family:
            print(f"  family -> {new_family}")

        # --- Build the patch payload ---
        patch: dict = {}
        if name_bad and new_name and new_name != old_name:
            patch["name"] = new_name
        # Clear a bad family name: set to empty string so it can be re-derived
        # by the enrichment pipeline, or set to the newly derived value.
        if family_bad:
            patch["family_name"] = new_family  # may be "" to clear it
        elif new_family and new_family != old_family:
            patch["family_name"] = new_family

        if patch:
            to_update.append({"id": rid, **patch})
        else:
            print(f"  (no change needed)")

    print(f"\n{'=' * 60}")
    print(f"Robots skipped (name already clean): {skipped}")
    print(f"Robots to update: {len(to_update)}")

    if not to_update:
        print("Nothing to do.")
        return

    if dry_run:
        print("\n[DRY RUN] Would apply the following patches:")
        for u in to_update:
            print(f"  ID {u['id']}: {u}")
        return

    print("\nApplying patches...")
    success = 0
    failed = 0
    for u in to_update:
        rid = u.pop("id")
        try:
            client._patch(f"robots/robots/{rid}/", u)
            print(f"  {rid}: OK  ({u})")
            success += 1
        except Exception as exc:
            print(f"  {rid}: FAILED — {exc}")
            failed += 1
        time.sleep(0.3)

    print(f"\nDone. {success} updated, {failed} failed.")


if __name__ == "__main__":
    main()
