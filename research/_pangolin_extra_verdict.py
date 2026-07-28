#!/usr/bin/env python3
"""Classify Pangolin PDP extras: unique-to-model vs shared/sibling contamination."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPORT = Path("staging/reports/pangolin-pdp-deep.json")
OUT = Path("staging/reports/_pangolin_extra_photo_verdict.json")


def main() -> int:
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    md5_owners: dict[str, list[str]] = defaultdict(list)
    for rid, row in data.items():
        for ex in row.get("extras") or []:
            md5_owners[ex["md5"]].append(f"{rid}:{row['model']}")

    unique_per_robot: dict[str, list] = defaultdict(list)
    shared = []
    for md5, owners in md5_owners.items():
        uniq_owners = sorted(set(owners))
        if len(uniq_owners) == 1:
            rid = uniq_owners[0].split(":")[0]
            # find url
            for ex in data[rid].get("extras") or []:
                if ex["md5"] == md5:
                    unique_per_robot[rid].append(ex)
                    break
        else:
            shared.append({"md5": md5, "owners": uniq_owners})

    # Also note: hero already on robot — extras that match hero path aren't "new variants"
    from fix_pangolin_robots import HERO

    hero_urls = {rid: cfg["hero"] for rid, cfg in HERO.items()}
    addable = {}
    for rid, extras in unique_per_robot.items():
        hero = hero_urls.get(int(rid), "")
        new = [e for e in extras if e["url"] != hero and e["md5"] not in hero]
        # exclude if URL basename equals hero basename
        hero_base = hero.rsplit("/", 1)[-1] if hero else ""
        new = [e for e in new if e["url"].rsplit("/", 1)[-1] != hero_base]
        addable[rid] = {
            "model": data[rid]["model"],
            "unique_extras": new,
            "count": len(new),
        }

    verdict = {
        "shared_extra_hashes": len(shared),
        "shared_samples": shared[:15],
        "robots_with_unique_extras": {
            rid: v for rid, v in addable.items() if v["count"] > 0
        },
        "robots_without_unique_extras": [
            {"id": rid, "model": data[rid]["model"]}
            for rid in data
            if addable.get(rid, {}).get("count", 0) == 0
        ],
    }
    OUT.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"shared hashes across models: {len(shared)}")
    print("robots with UNIQUE extras (candidate add):")
    for rid, v in sorted(addable.items(), key=lambda x: -x[1]["count"]):
        if v["count"]:
            print(f"  {rid} {v['model']}: +{v['count']}")
            for e in v["unique_extras"][:4]:
                print(f"      {e['md5'][:12]} {e['url']}")
    empty = [rid for rid, v in addable.items() if not v["count"]]
    missing = [rid for rid in data if rid not in addable]
    print(f"no unique extras: {len(empty)+len(missing)} robots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
