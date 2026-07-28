#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

client = ResearchApiClient()
out = {}
co = client._get("companies/1413/")
out["company"] = {
    "id": co.get("id"),
    "name": co.get("name"),
    "country": co.get("country"),
    "website": co.get("website"),
}
robots = client._get(
    "robots/robots/",
    params={"company_ref": 1413, "status": "pending_review", "page_size": 50},
)["results"]
rows = []
for r in robots:
    rows.append(
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "has_image": bool(r.get("s3_image") or r.get("image")),
            "features_len": len((r.get("features") or "").strip()),
            "categories": r.get("categories"),
            "uses": r.get("uses"),
            "manufacturer_countries": r.get("manufacturer_countries"),
            "country": r.get("country"),
        }
    )
out["pending_count"] = len(rows)
out["robots"] = rows
# also spot-check a few clean companies for soft warns rate
Path("staging/reports/_probe_pangolin_ready.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"pending={len(rows)} country={co.get('country')}")
print(
    "all_have_image",
    all(x["has_image"] for x in rows),
    "all_features",
    all(x["features_len"] >= 40 for x in rows),
    "all_cats",
    all(x["categories"] for x in rows),
    "all_uses",
    all(x["uses"] for x in rows),
    "any_mc",
    any(x["manufacturer_countries"] for x in rows),
)
