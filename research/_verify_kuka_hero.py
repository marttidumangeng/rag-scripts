#!/usr/bin/env python3
"""Verify one KUKA robot hero is no longer the AVIF stub cluster."""
from __future__ import annotations

import hashlib
import sys
import time

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

STUB = "51d34593d7c8"  # old quantec AVIF cluster prefix
rid = int(sys.argv[1]) if len(sys.argv) > 1 else 5414
c = ResearchApiClient()
r = c._get(f"robots/robots/{rid}/")
url = (r.get("s3_image") or r.get("image") or "").strip()
print("url:", url[:120])
print("status:", r.get("status"))
body = requests.get(url, timeout=60).content
md5 = hashlib.md5(body).hexdigest()
print("md5:", md5, "bytes:", len(body), "magic:", body[:12])
print("STUB_GONE:" if not md5.startswith(STUB) else "STILL_STUB:", md5[:12])
# also check photos
photos = r.get("photos") or r.get("images") or []
print("n_photos:", len(photos) if isinstance(photos, list) else photos)
if isinstance(photos, list) and photos:
    p0 = photos[0]
    pu = p0.get("url") if isinstance(p0, dict) else p0
    if pu:
        pb = requests.get(pu, timeout=60).content
        print("photo0 md5:", hashlib.md5(pb).hexdigest()[:12], "bytes:", len(pb), "magic:", pb[:12])
