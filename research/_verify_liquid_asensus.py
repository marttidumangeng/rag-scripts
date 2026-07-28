"""Verify Liquid/Asensus overnight enrich results."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

IDS = [3869, 1635, 4032, 1654]


def main() -> int:
    client = ResearchApiClient()
    out = {}
    for rid in IDS:
        r = client._get(f"robots/robots/{rid}/")
        avail = r.get("availability_status") or {}
        mcr = r.get("manufacturer_country_ref") or {}
        sources = r.get("information_sources") or r.get("information_source_urls") or []
        purpose = r.get("purpose") or ""
        desc = r.get("description") or ""
        row = {
            "id": rid,
            "name": r.get("name"),
            "status": r.get("status"),
            "rejection_reason": (r.get("rejection_reason") or "")[:200],
            "url": r.get("url"),
            "family_key": r.get("family_key"),
            "family_name": r.get("family_name"),
            "family_url": r.get("family_url"),
            "product_url_scope": r.get("product_url_scope"),
            "availability": avail.get("key") if isinstance(avail, dict) else avail,
            "country": mcr.get("code") if isinstance(mcr, dict) else mcr,
            "purpose": purpose,
            "purpose_dup_desc": purpose.strip()
            and purpose.strip()[:80] in desc.replace("\n", " "),
            "features_preview": (r.get("features") or "")[:180],
            "features_len": len(r.get("features") or ""),
            "payload_kg": r.get("payload_kg"),
            "length_mm": r.get("length_mm"),
            "weight_kg": r.get("weight_kg"),
            "speed": r.get("speed"),
            "dof": r.get("dof"),
            "tags": r.get("tags"),
            "sources": sources if isinstance(sources, list) else sources,
            "has_image": bool(r.get("image") or r.get("s3_image")),
        }
        out[str(rid)] = row
        print(json.dumps(row, ensure_ascii=False, indent=2)[:800])
        print("---")
    path = _RESEARCH / "staging" / "reports" / "liquid-asensus-verify.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
