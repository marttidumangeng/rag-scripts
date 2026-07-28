"""Spot-check Stryker post-enrich fields + hero hashes."""
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
hashes = {}
for rid in (4308, 2385, 2386, 3288, 225):
    d = c._get(f"robots/robots/{rid}/")
    img = d.get("image") or d.get("s3_image") or ""
    print("===", rid, d.get("name"), d.get("status"))
    print("  img", img[:110])
    print("  feats", len(d.get("features") or ""))
    print("  avail", d.get("availability_status"))
    print("  country", d.get("manufacturer_countries"))
    print("  cats", d.get("categories"), "uses", d.get("uses"))
    if img:
        r = requests.get(img, timeout=60)
        h = hashlib.md5(r.content).hexdigest()[:12]
        hashes[rid] = h
        print("  http", r.status_code, len(r.content), h)
print("unique hashes among pending", len(set(hashes[i] for i in (4308, 2385, 2386, 3288))))
