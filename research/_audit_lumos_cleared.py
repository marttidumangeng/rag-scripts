"""Verify Lumos 70 after stakeholder approve."""
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
robots = c.list_robots_for_company(70) or []
print("status", dict(Counter(r.get("status") for r in robots)))
for r in sorted(robots, key=lambda x: (x.get("status") or "", x.get("id") or 0)):
    print(f"{r.get('id')}\t{r.get('status')}\t{r.get('name')}")
