#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

p = Path(__file__).resolve().parent / "staging" / "robolist_gap"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    s = json.loads((p / "summary.json").read_text(encoding="utf-8"))
    miss_r = json.loads((p / "missing_robots.json").read_text(encoding="utf-8"))
    miss_c = json.loads((p / "missing_companies.json").read_text(encoding="utf-8"))
    our = json.loads((p / "our_inventory.json").read_text(encoding="utf-8"))

    by_mfr = Counter()
    by_mfr_in_db = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    for r in miss_r:
        mfr = r.get("manufacturer") or "(unknown)"
        by_mfr[mfr] += 1
        if r.get("manufacturer_in_db"):
            by_mfr_in_db[mfr] += 1
        if len(samples[mfr]) < 5:
            samples[mfr].append(r.get("name") or r.get("slug") or "")

    depth = [
        {
            "manufacturer": m,
            "missing": n,
            "in_db": True,
            "samples": samples[m],
        }
        for m, n in by_mfr_in_db.most_common(25)
    ]
    in_db_set = set(by_mfr_in_db)
    breadth_mfr = [
        {
            "manufacturer": m,
            "missing": n,
            "in_db": False,
            "samples": samples[m],
        }
        for m, n in by_mfr.most_common(80)
        if m != "(unknown)" and m not in in_db_set
    ][:25]

    miss_company_slugs = {c["slug"] for c in miss_c}
    mfr_slug_counts: Counter[str] = Counter()
    mfr_slug_name: dict[str, str] = {}
    for r in miss_r:
        slug = r.get("manufacturer_slug")
        if slug and slug in miss_company_slugs:
            mfr_slug_counts[slug] += 1
            mfr_slug_name[slug] = r.get("manufacturer") or slug

    top_missing_cos = [
        {
            "slug": slug,
            "name": mfr_slug_name[slug],
            "missing_robots": n,
            "url": f"https://www.robolist.ai/companies/{slug}",
        }
        for slug, n in mfr_slug_counts.most_common(30)
    ]

    status = Counter(r.get("status") or "?" for r in our["robots"])
    unknown = by_mfr.get("(unknown)", 0)
    in_db_missing = sum(by_mfr_in_db.values())

    out = {
        "summary": s["gap"],
        "counts": {
            "robolist": s["robolist"],
            "ours": s["ours"],
            "our_status": dict(status),
        },
        "by_category": s["by_category"],
        "depth_gaps_company_in_db": depth,
        "breadth_gaps_new_oem_names": breadth_mfr,
        "top_missing_companies_by_robot_gap": top_missing_cos,
        "unknown_manufacturer_missing_robots": unknown,
        "missing_robots_where_company_in_db": in_db_missing,
        "missing_robots_new_or_unmatched_oem": len(miss_r) - in_db_missing - unknown,
    }
    (p / "canvas_payload.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("company coverage", s["gap"]["company_coverage_pct"])
    print("robot coverage", s["gap"]["robot_coverage_pct"])
    print("our status", dict(status))
    print("depth top", [(d["manufacturer"], d["missing"]) for d in depth[:12]])
    print("missing cos", [(c["name"], c["missing_robots"]) for c in top_missing_cos[:12]])
    print("unknown mfr missing", unknown, "in_db depth", in_db_missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
