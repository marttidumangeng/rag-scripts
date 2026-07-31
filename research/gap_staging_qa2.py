"""QA round 2 for staging/gap_discovery/staged_import.json.

Fixes issues visible after QA round 1:

  1. Same-domain duplicate companies (e.g. GOJON + Shandong Gojon Precision
     Technology both -> gojongroup.com). Keep the entry with the more complete
     name (longer), merge sources/categories, reassign robots.
  2. Wrong-domain resolutions: the resolved domain neither matches the company
     name tokens nor was seeded — these are moved to low_signal (website
     cleared) rather than kept with a misleading URL. Uses the same
     domain_matches_company() check as the workflow, applied strictly.
  3. Companies whose "name" is actually a robot model or non-company artifact
     (e.g. "MANOI PF01", "Protocol droid", "Honda E series", "Hk") that
     resolved to an unrelated shop/aggregator domain.

Run AFTER gap_staging_qa.py. Writes in place; previous state preserved as
staged_import.qa1.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from company_website_resolve import domain_matches_company  # noqa: E402

BASE = _HERE / "staging" / "gap_discovery"
STAGED = BASE / "staged_import.json"

# Known robot-model / artifact names staged as companies
ARTIFACT_NAME_RE = re.compile(
    r"^(protocol droid|manoi ?pf ?\d+|honda e series|hk|de|plus|rna|bumblebee|"
    r"delta robot|diagnostic robot|disability robot)$",
    re.I,
)

# Universities / labs are not manufacturers for the DB
LAB_RE = re.compile(r"(universit|technische|institute of technology|research lab)", re.I)

# Known-good resolutions that fail the token match (brand != domain)
DOMAIN_EXCEPTIONS = {
    "fbr.com.au": "Fastbrick Robotics",
    "aurora.tech": "Aurora Innovation",
    "thehumanoid.ai": "Humanoid",
    "airbus.com": "Airbus",
    "turtlebot.com": "Willow Garage",  # TurtleBot originated at Willow Garage
}


def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "").lower()
    except Exception:  # noqa: BLE001
        return ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(STAGED.read_text(encoding="utf-8"))
    cos = data["companies"]
    robs = data["robots"]
    low = data.get("low_signal_companies", [])

    # ── 1. artifact / lab names → drop or demote ─────────────────────────────
    kept: list[dict] = []
    demoted: list[dict] = []
    dropped_names: list[str] = []
    for c in cos:
        name = (c.get("name") or "").strip()
        if ARTIFACT_NAME_RE.match(name):
            dropped_names.append(name)
            continue
        if LAB_RE.search(name):
            c["website"] = ""
            demoted.append(c)
            continue
        kept.append(c)

    # ── 2. wrong-domain check (strict) ───────────────────────────────────────
    kept2: list[dict] = []
    for c in kept:
        website = c.get("website") or ""
        host = host_of(website)
        seeded = "seed" in (c.get("research_notes") or "").lower()
        if host in DOMAIN_EXCEPTIONS:
            kept2.append(c)
            continue
        if host and not seeded and not domain_matches_company(website, c["name"]):
            # domain shares no tokens with company name — likely misresolved
            c["research_notes"] = (c.get("research_notes") or "") + (
                " [QA2] Website cleared: resolved domain '" + host +
                "' does not match company name tokens; needs manual verification."
            )
            c["website"] = ""
            demoted.append(c)
            continue
        kept2.append(c)

    # ── 3. same-domain merge ────────────────────────────────────────────────
    by_host: dict[str, list[dict]] = defaultdict(list)
    for c in kept2:
        h = host_of(c.get("website") or "")
        if h:
            by_host[h].append(c)

    slug_remap: dict[str, str] = {}
    merged_away: list[str] = []
    final: list[dict] = []
    for c in kept2:
        h = host_of(c.get("website") or "")
        group = by_host.get(h, [])
        if h and len(group) > 1:
            # prefer the canonical name for known domains, otherwise the entry
            # whose name best matches the domain, then the longest name
            canonical = DOMAIN_EXCEPTIONS.get(h)
            winner = None
            if canonical:
                winner = next((x for x in group if x["name"] == canonical), None)
            if winner is None:
                matching = [x for x in group
                            if domain_matches_company(x.get("website") or "", x["name"])]
                pool = matching or group
                winner = max(pool, key=lambda x: len(x.get("name") or ""))
            if c is not winner:
                slug_remap[c["slug"]] = winner["slug"]
                merged_away.append(f"{c['name']} -> {winner['name']}")
                # merge categories + sources into the winner
                for cat in c.get("primary_focus", []):
                    if cat not in winner.setdefault("primary_focus", []):
                        winner["primary_focus"].append(cat)
                for s in c.get("sources", []):
                    if s not in winner.setdefault("sources", []):
                        winner["sources"].append(s)
                continue
        final.append(c)

    # reassign robots; dedupe robots that collide after remap
    seen: set[tuple[str, str]] = set()
    final_slugs = {c["slug"] for c in final}
    kept_robots: list[dict] = []
    dropped_robots = 0
    for r in robs:
        slug = slug_remap.get(r["company_slug"], r["company_slug"])
        if slug not in final_slugs:
            dropped_robots += 1
            continue
        key = (slug, (r.get("name") or "").lower())
        if key in seen:
            dropped_robots += 1
            continue
        seen.add(key)
        r["company_slug"] = slug
        winner = next(c for c in final if c["slug"] == slug)
        r["company_name"] = winner["name"]
        kept_robots.append(r)

    print(f"companies: {len(cos)} -> {len(final)} "
          f"(dropped artifacts: {len(dropped_names)}, demoted to low-signal: {len(demoted)}, "
          f"same-domain merged: {len(merged_away)})")
    print(f"robots: {len(robs)} -> {len(kept_robots)} (removed {dropped_robots})")
    print("artifacts:", dropped_names)
    print("merged sample:", merged_away[:12])
    print("demoted sample:", [c["name"] for c in demoted[:12]])

    if args.dry_run:
        return

    prev = STAGED.with_suffix(".qa1.json")
    if not prev.exists():
        prev.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    data["companies"] = final
    data["robots"] = kept_robots
    data["company_count"] = len(final)
    data["robot_count"] = len(kept_robots)
    data["low_signal_companies"] = low + demoted
    data.setdefault("qa_dropped", {})["qa2"] = {
        "artifact_companies": dropped_names,
        "same_domain_merged": merged_away,
        "demoted_wrong_domain": [c["name"] for c in demoted],
    }
    STAGED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {STAGED}")


if __name__ == "__main__":
    main()
