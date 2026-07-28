#!/usr/bin/env python3
from __future__ import annotations

import sys
from collections import Counter

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
for cid in (428, 1490, 400, 73):
    rs = c.list_robots_for_company(cid)
    st = Counter(str(r.get("status") or "").lower() for r in rs)
    name = "?"
    if rs:
        d = c._get(f"robots/robots/{int(rs[0]['id'])}/")
        cref = d.get("company_ref") or {}
        name = (cref.get("name") if isinstance(cref, dict) else "?") or "?"
    print(cid, name, dict(st), "total", len(rs))
