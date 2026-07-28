"""Inspect siblings for tags/videos/specs/years to clone onto pending gaps."""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

IDS = [
    213,
    3425,
    3427,
    3429,
    3430,
    3431,
    4076,
    4077,
    4078,
    4079,
    4080,
    4081,
    4085,
    4090,
    4091,
    4092,
    # siblings with good data
    5509,
    4093,
    4078,
]
c = ResearchApiClient()
# also find any LBR Med / nano / scara / kmp with tags
for rid in [213, 3425, 3427, 3429, 3430, 3431, 4076, 4077, 4078, 4079, 4080, 4081, 4085, 4090, 4091, 4092]:
    r = c._get(f"robots/robots/{rid}/")
    tags = r.get("tags") or []
    if isinstance(tags, list):
        tag_s = [t.get("name") if isinstance(t, dict) else t for t in tags]
    else:
        tag_s = tags
    vids = r.get("videos") or []
    print(
        json.dumps(
            {
                "id": rid,
                "name": r.get("name"),
                "family_key": r.get("family_key"),
                "year": r.get("release_year"),
                "tags": tag_s,
                "videos_n": len(vids) if isinstance(vids, list) else 0,
                "video0": (vids[0] if isinstance(vids, list) and vids else None),
                "payload": r.get("payload_kg"),
                "reach": r.get("reach_mm"),
                "dof": r.get("dof"),
                "weight": r.get("weight_kg"),
                "url": r.get("url"),
            },
            ensure_ascii=False,
        )
    )
    time.sleep(0.05)
