#!/usr/bin/env python3
from __future__ import annotations

import sys

import requests

sys.path.insert(0, ".")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
for cid in (239, 1028):
    robots = c.list_robots_for_company(cid)
    pub = [r for r in robots if str(r.get("status") or "").lower() in ("published", "approved")]
    print(f"company {cid} published={len(pub)} pending={sum(1 for r in robots if str(r.get('status')).lower()=='pending_review')}")
    if cid == 239:
        for lite in sorted(pub, key=lambda x: int(x["id"])):
            r = c._get(f"robots/robots/{int(lite['id'])}/")
            u1280 = (r.get("image_variants") or {}).get("1280") or ""
            code = requests.get(u1280, headers={"Range": "bytes=0-32"}, timeout=15).status_code if u1280 else None
            name = (r.get("name") or "")[:30]
            print(f"  {r['id']} {name:30} 1280={code}")
