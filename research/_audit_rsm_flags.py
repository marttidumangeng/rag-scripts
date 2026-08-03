"""Dump quality_flags for company 1602 pending robots."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
for r in sorted(c.list_robots_for_company(1602), key=lambda x: int(x["id"])):
    if str(r.get("status") or "") not in ("pending_review", "published"):
        continue
    full = c._get(f"robots/robots/{r['id']}/")
    flags = full.get("quality_flags") or []
    print(
        full["id"],
        full.get("name"),
        "flags=",
        json.dumps(flags, ensure_ascii=False)[:500],
    )
    print(
        "  purpose=",
        repr((full.get("purpose") or "")[:80]),
        "features_len=",
        len((full.get("features") or "").strip()),
        "url=",
        full.get("url"),
    )
