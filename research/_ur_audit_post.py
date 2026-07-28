"""Post-apply audit for Universal Robots company 192."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

SAMPLE = {2535, 3543, 3544, 4882, 4883, 2524, 4322, 2525}


def main() -> None:
    client = ResearchApiClient()
    robots = client.list_robots_for_company(192)
    pending = [r for r in robots if str(r.get("status") or "").lower() == "pending_review"]
    print(f"pending={len(pending)}")

    no_img = no_feat = no_country = no_cat = no_uses = 0
    names: dict[str, list[int]] = defaultdict(list)
    imageless: list[tuple[int, str]] = []

    for r in pending:
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        name = (full.get("name") or "").strip()
        names[name].append(rid)
        img = (full.get("image") or full.get("s3_image") or "").strip()
        if not img:
            no_img += 1
            imageless.append((rid, name))
        if not (full.get("features") or "").strip():
            no_feat += 1
        if not (full.get("manufacturer_country") or full.get("manufacturer_countries")):
            no_country += 1
        if not (full.get("categories") or []):
            no_cat += 1
        if not (full.get("uses") or []):
            no_uses += 1
        if rid in SAMPLE:
            notes = full.get("notes") or ""
            print(
                f"{rid} name={name!r} country={full.get('manufacturer_country')!r} "
                f"p={full.get('payload_kg')} r={full.get('reach_mm')} "
                f"cats={full.get('categories')} uses={full.get('uses')} "
                f"img={(img[:55] if img else None)} "
                f"todo={'[IMAGE TO-DO' in notes}"
            )

    print(
        f"gaps no_img={no_img} no_feat={no_feat} no_country={no_country} "
        f"no_cat={no_cat} no_uses={no_uses}"
    )
    print("imageless:")
    for rid, name in imageless:
        print(f"  {rid} {name}")

    dups = {k: v for k, v in names.items() if len(v) > 1}
    print(f"exact-name duplicate clusters: {len(dups)}")
    for k, v in sorted(dups.items(), key=lambda x: -len(x[1])):
        print(f"  {k!r}: {v}")


if __name__ == "__main__":
    main()
