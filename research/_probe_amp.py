"""Inspect AMP Robotics (259) fleet."""
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
co = c.get_company(259)
print("company", co.get("id"), co.get("name"))
print("website", co.get("website") or co.get("website_url"))
print("country", co.get("country"))
print("desc", (co.get("description") or "")[:180])
hashes = {}
for r in c.list_robots_for_company(259) or []:
    d = c._get(f"robots/robots/{r['id']}/")
    img = d.get("s3_image") or d.get("image") or ""
    print("===", d["id"], d.get("name"), d.get("status"))
    print("  url", (d.get("url") or "")[:110])
    print("  img", bool(img), (img or "")[:100])
    print("  feats", len(d.get("features") or ""), (d.get("features") or "")[:90])
    print("  avail", d.get("availability_status"), "year", d.get("release_year"))
    print("  country", bool(d.get("manufacturer_countries")), "fam", d.get("family_key"))
    print("  cats", d.get("categories"), "uses", [u.get("key") if isinstance(u, dict) else u for u in (d.get("uses") or [])])
    print(
        "  w",
        d.get("weight_kg"),
        "payload",
        d.get("payload_kg"),
        "LWH",
        d.get("length_mm"),
        d.get("width_mm"),
        d.get("height_mm"),
        "speed",
        d.get("speed"),
        "dof",
        d.get("dof"),
    )
    print("  videos", len(d.get("videos") or []), "tags", d.get("tags"))
    if img:
        try:
            resp = requests.get(img, timeout=60)
            h = hashlib.md5(resp.content).hexdigest()[:12]
            hashes[d["id"]] = (h, len(resp.content), resp.status_code, resp.content[:8])
            print("  hash", h, len(resp.content), resp.status_code)
        except Exception as e:
            print("  img err", e)
print("unique", len(set(v[0] for v in hashes.values())), "of", len(hashes))
