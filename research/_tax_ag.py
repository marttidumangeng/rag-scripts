"""Taxonomy sample for ag robots."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
for cid in (263, 265, 268, 266):
    for r in c.list_robots_for_company(cid) or []:
        if r.get("status") != "published" and cid != 266:
            continue
        d = c._get(f"robots/robots/{r['id']}/")
        print(
            cid,
            d["id"],
            d.get("name"),
            "cats",
            d.get("categories"),
            "uses",
            d.get("uses"),
            "move",
            d.get("movement_types"),
            "ind",
            d.get("industries"),
        )
        if cid != 266:
            break
