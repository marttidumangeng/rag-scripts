"""Inspect Stryker (350) fleet for enrich."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
co = c.get_company(350)
print("company", co.get("id"), co.get("name"))
print("website", co.get("website") or co.get("website_url"))
print("desc", (co.get("description") or "")[:200])
for r in c.list_robots_for_company(350) or []:
    d = c._get(f"robots/robots/{r['id']}/")
    print("===", d["id"], d.get("name"), d.get("status"))
    print("  url", (d.get("url") or "")[:110])
    print("  img", (d.get("s3_image") or d.get("image") or "")[:110])
    print("  feats", len(d.get("features") or ""), (d.get("features") or "")[:100])
    print("  avail", d.get("availability_status"), "year", d.get("release_year"))
    print("  country", d.get("manufacturer_countries"))
    print("  cats", d.get("categories"))
    print("  uses", d.get("uses"))
    print(
        "  payload",
        d.get("payload_kg"),
        "weight",
        d.get("weight_kg"),
        "dims",
        d.get("length_mm"),
        d.get("width_mm"),
        d.get("height_mm"),
    )
    print("  videos", len(d.get("videos") or []), "tags", d.get("tags"))
    print("  purpose", (d.get("purpose") or "")[:80])
    print("  desc", (d.get("description") or "")[:100])
