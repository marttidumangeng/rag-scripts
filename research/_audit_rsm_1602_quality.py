"""Audit content-queue gaps for company 1602 pending robots."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
for r in sorted(c.list_robots_for_company(1602), key=lambda x: int(x["id"])):
    if str(r.get("status") or "") not in ("pending_review", "published"):
        continue
    full = c._get(f"robots/robots/{r['id']}/")
    print(
        json.dumps(
            {
                "id": full["id"],
                "status": full.get("status"),
                "name": full.get("name"),
                "url": full.get("url"),
                "purpose_len": len((full.get("purpose") or "").strip()),
                "purpose": (full.get("purpose") or "")[:120],
                "features_len": len((full.get("features") or "").strip()),
                "features": (full.get("features") or "")[:120],
                "description_len": len((full.get("description") or "").strip()),
                "payload_kg": full.get("payload_kg"),
                "reach_mm": full.get("reach_mm"),
                "dof": full.get("dof"),
                "repeatability_mm": full.get("repeatability_mm"),
                "weight_kg": full.get("weight_kg"),
                "voltage": (full.get("voltage") or "")[:60],
                "sensors": (full.get("sensors") or "")[:60],
                "connectivity": (full.get("connectivity") or "")[:60],
                "country_ref": (full.get("manufacturer_country_ref") or {}).get("id")
                if isinstance(full.get("manufacturer_country_ref"), dict)
                else full.get("manufacturer_country_ref"),
            },
            ensure_ascii=False,
        )
    )
