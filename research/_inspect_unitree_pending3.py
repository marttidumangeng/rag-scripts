#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
co = c._get("companies/109/")
print(
    "company",
    {
        "country": co.get("country"),
        "country_id": co.get("country_id"),
        "website": co.get("website"),
    },
)

for rid in [5362, 5355, 5353]:
    r = c._get(f"robots/robots/{rid}/")
    print("===", rid, r.get("name"))
    for k in (
        "manufacturer_country_ref",
        "manufacturer_country",
        "manufacturer_countries",
        "country",
        "country_code",
        "categories",
        "uses",
        "industries",
        "tags",
        "features",
        "description",
        "purpose",
        "url",
        "s3_image",
        "image",
        "release_year",
        "payload_kg",
        "weight_kg",
        "dof",
        "notes",
        "family_key",
        "videos",
        "photos",
    ):
        v = r.get(k)
        if k in ("features", "description", "purpose", "notes") and isinstance(v, str):
            print(f"  {k}: len={len(v)} {v[:120]!r}")
        elif k == "photos" and isinstance(v, list):
            print(f"  photos: n={len(v)}")
            for i, p in enumerate(v[:3]):
                print(
                    f"    [{i}] primary={p.get('is_primary')} "
                    f"{(p.get('s3_image') or p.get('url') or '')[:90]}"
                )
        elif k == "videos" and isinstance(v, list):
            print(f"  videos: n={len(v)}")
            for i, vid in enumerate(v[:2]):
                print(f"    [{i}] {vid.get('title','')[:60]} {vid.get('url')}")
        elif k == "tags" and isinstance(v, list):
            names = [t.get("name") if isinstance(t, dict) else t for t in v]
            print(f"  tags: {names}")
        else:
            s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            if s and len(s) > 180:
                s = s[:180] + "..."
            print(f"  {k}: {s}")

# published sibling country sample
robots = c.list_robots_for_company(109)
for r in robots:
    if str(r.get("status") or "").lower() != "published":
        continue
    d = c._get(f"robots/robots/{int(r['id'])}/")
    print(
        "published sample",
        d["id"],
        d.get("name"),
        "mc_ref",
        d.get("manufacturer_country_ref"),
        "mcs",
        d.get("manufacturer_countries"),
        "country",
        d.get("country"),
    )
    break
