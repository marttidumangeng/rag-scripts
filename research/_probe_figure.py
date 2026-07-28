"""Inspect Figure AI (36) fleet + Figure 03 gaps."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
co = c.get_company(36)
print("company", co.get("id"), co.get("name"))
print("website", co.get("website") or co.get("website_url"))
print("country", co.get("country"))
print("desc", (co.get("description") or "")[:200])
for r in c.list_robots_for_company(36) or []:
    d = c._get(f"robots/robots/{r['id']}/")
    img = d.get("s3_image") or d.get("image") or ""
    print("===", d["id"], d.get("name"), d.get("status"))
    print("  url", (d.get("url") or "")[:110])
    print("  img", (img or "")[:110])
    print("  feats", len(d.get("features") or ""), (d.get("features") or "")[:120])
    print("  avail", d.get("availability_status"), "year", d.get("release_year"))
    print("  country", d.get("manufacturer_countries"))
    print("  cats", d.get("categories"), "uses", d.get("uses"))
    print(
        "  w",
        d.get("weight_kg"),
        "payload",
        d.get("payload_kg"),
        "h",
        d.get("height_mm"),
        "speed",
        d.get("speed"),
        "dof",
        d.get("dof"),
    )
    print(
        "  family",
        d.get("family_key"),
        d.get("family_name"),
        d.get("family_url"),
        d.get("product_url_scope"),
    )
    print("  videos", len(d.get("videos") or []), "tags", d.get("tags"))
    if img:
        resp = requests.get(img, timeout=60)
        print(
            "  hash",
            hashlib.md5(resp.content).hexdigest()[:12],
            len(resp.content),
            resp.status_code,
            resp.content[:12],
        )
