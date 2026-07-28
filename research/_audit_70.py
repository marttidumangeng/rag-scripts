"""Audit company 70 for full enrich."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
co = c.get_company(70) or {}
print("company", co.get("id"), co.get("name"))
print("website", co.get("website"))
print("country", co.get("country") or co.get("country_id"))
robots = c.list_robots_for_company(70) or []
print("status", dict(Counter(r.get("status") for r in robots)))
print("total", len(robots))
pending = [r for r in robots if r.get("status") == "pending_review"]
print("pending", len(pending))
for r in sorted(pending, key=lambda x: x.get("id") or 0)[:40]:
    print(f"  {r.get('id')}\t{r.get('name')}")
if len(pending) > 40:
    print(f"  ... +{len(pending)-40} more")
