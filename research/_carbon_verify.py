"""Verify Carbon typed specs + soft warns."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
for rid in (2699, 2700, 2701, 2702, 2703):
    d = c._get(f"robots/robots/{rid}/")
    print(
        rid,
        d.get("name"),
        "avail",
        d.get("availability_status"),
        "US",
        bool(d.get("manufacturer_countries")),
        "w",
        d.get("weight_kg"),
        "LWH",
        d.get("length_mm"),
        d.get("width_mm"),
        d.get("height_mm"),
        "fam",
        d.get("family_key"),
        "cats",
        d.get("categories"),
        "feat",
        len(d.get("features") or ""),
    )
