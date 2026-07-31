"""Post-run QA pass over staging/gap_discovery/staged_import.json.

The harvest is intentionally broad, so some junk survives to Stage E. This
script applies conservative, explainable filters and writes a cleaned file
(the original is preserved with a .raw.json suffix):

  1. Hash-slug names harvested from robolist ("Cn 07A84A885E", "Us 12Ab...").
  2. Fictional / pop-culture robots that slipped in via Wikipedia categories
     (no website resolved AND zero robots staged AND name matches a known
     fiction pattern is NOT auto-detectable, so instead: entries whose only
     source is wikipedia AND no website AND no robots are dropped — they give
     reviewers nothing actionable).
  3. Companies with no website AND no robots from any source are moved to a
     `low_signal` bucket in the cleaned file rather than deleted, so reviewers
     can still rescue them.
  4. Robots whose cleaned name is still navigation-like junk.

Usage:
  python gap_staging_qa.py            # clean staged_import.json in place
  python gap_staging_qa.py --dry-run  # report only
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
STAGED = BASE / "staging" / "gap_discovery" / "staged_import.json"

# robolist hash-slug artifacts: country code + hex blob
HASH_NAME_RE = re.compile(r"^[A-Z][a-z]?\s+[0-9A-Fa-f]{8,}$")

ROBOT_JUNK_RE = re.compile(
    r"^(robots?|products?|view |see |all |learn |read |explore |discover |"
    r"shop |buy |our |the )", re.I,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(STAGED.read_text(encoding="utf-8"))
    companies = data.get("companies", [])
    robots = data.get("robots", [])

    robots_per_co: dict[str, int] = {}
    for r in robots:
        robots_per_co[r["company_slug"]] = robots_per_co.get(r["company_slug"], 0) + 1

    kept_companies = []
    low_signal = []
    dropped_hash = []
    for c in companies:
        name = c.get("name") or ""
        slug = c.get("slug") or ""
        website = (c.get("website") or "").strip()
        n_robots = robots_per_co.get(slug, 0)
        if HASH_NAME_RE.match(name):
            dropped_hash.append(name)
            continue
        srcs = " ".join(
            (s.get("title") or "") + (s.get("url") or "") for s in c.get("sources", [])
        ).lower()
        wikipedia_only = "wikipedia" in srcs and "robolist" not in srcs and "aparobot" not in srcs
        if not website and n_robots == 0 and wikipedia_only:
            low_signal.append(c)
            continue
        if not website and n_robots == 0:
            low_signal.append(c)
            continue
        kept_companies.append(c)

    kept_slugs = {c["slug"] for c in kept_companies}
    kept_robots = []
    dropped_robots = []
    for r in robots:
        if r["company_slug"] not in kept_slugs:
            dropped_robots.append(r["name"])
            continue
        if ROBOT_JUNK_RE.match(r.get("name") or "") and len((r.get("name") or "").split()) <= 3:
            dropped_robots.append(r["name"])
            continue
        kept_robots.append(r)

    print(f"companies: {len(companies)} -> kept {len(kept_companies)}, "
          f"low-signal {len(low_signal)}, hash-junk {len(dropped_hash)}")
    print(f"robots: {len(robots)} -> kept {len(kept_robots)}, dropped {len(dropped_robots)}")
    if dropped_robots[:10]:
        print("dropped robot sample:", dropped_robots[:10])

    if args.dry_run:
        return

    raw_path = STAGED.with_suffix(".raw.json")
    if not raw_path.exists():
        raw_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    data["company_count"] = len(kept_companies)
    data["robot_count"] = len(kept_robots)
    data["companies"] = kept_companies
    data["robots"] = kept_robots
    data["low_signal_companies"] = low_signal
    data["qa_dropped"] = {
        "hash_named_companies": dropped_hash,
        "junk_robots": dropped_robots,
    }
    STAGED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"cleaned file written: {STAGED}")
    print(f"raw preserved: {raw_path}")


if __name__ == "__main__":
    main()
