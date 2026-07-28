"""Probe Trossen 307 pending gaps (UTF-8 safe)."""
from __future__ import annotations

import sys
from pathlib import Path

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
rows = c.list_robots_for_company(307)
for r in sorted(rows, key=lambda x: x.get("id", 0)):
    if r.get("status") != "pending_review":
        continue
    rid = r["id"]
    full = c._session.get(c._url(f"robots/robots/{rid}/"), timeout=60).json()
    img = full.get("primary_image_url") or full.get("image") or ""
    cats = full.get("categories") or full.get("category_slugs") or []
    uses = full.get("uses") or full.get("use_keys") or []
    print("===", rid, full.get("name"))
    print(" feat", len(full.get("features") or ""))
    print(" purpose", (full.get("purpose") or "")[:120])
    print(
        " specs",
        {
            k: full.get(k)
            for k in (
                "weight_kg",
                "payload_kg",
                "height_mm",
                "reach_mm",
                "dof",
                "speed",
                "length_mm",
                "width_mm",
                "release_year",
            )
            if full.get(k) not in (None, "", 0)
        },
    )
    print(" fam", full.get("family_key"), full.get("family_name"))
    print(" country", full.get("manufacturer_country_ref") or full.get("manufacturer_countries"))
    print(" cats", cats[:3] if isinstance(cats, list) else cats)
    print(" uses", uses[:3] if isinstance(uses, list) else uses)
    print(" img", (img or "")[:100])
    if img:
        ir = requests.get(img, timeout=30)
        print(" img_http", ir.status_code, len(ir.content), ir.content[:4])
