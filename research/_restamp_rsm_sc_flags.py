"""Restamp SC sibling quality_flags via bulk-import (drops AI URL-mismatch chips).

bulk_import replaces quality_flags with cheap robot_quality_flags() only — it does
not carry VERIFICATION_FLAG_KEYS. Use after aligning family-page copy so the queue
no longer shows false url_content_mismatch for SC7/SC15/SC20 on the SC6 family PDP.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

IDS = [6806, 6807, 6808, 6809]
COMPANY_SLUG = "rsm-machinery"
COMPANY_NAME = "RSM Machinery"


def main() -> int:
    client = ResearchApiClient()
    for rid in IDS:
        r = client._get(f"robots/robots/{rid}/")
        row = {
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "source_locale": "en",
            "name": r.get("name"),
            "model_name": r.get("model_name") or r.get("name"),
            "url": r.get("url"),
            "description": r.get("description") or "ERSM SC cobot.",
            "purpose": r.get("purpose") or "Arc welding",
            "features": r.get("features") or "ERSM SC-series collaborative welding robot.",
            "information_source_urls": [r.get("url")],
            "notes": r.get("notes") or "[AI Research] Family PDP restamp.",
        }
        # keep owned CDN hero
        img = r.get("s3_image") or r.get("image")
        if img:
            row["image"] = img
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        bulk["status"] = "pending_review"
        result = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=False,
            replace_media=False,
            replace_videos=False,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(1),
        )
        print(f"{rid} {r.get('name')}: updated={result.get('updated_count')} err={result.get('error_count')}")
        # re-assert typed + country (import can soft-touch)
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "pending_review",
                "payload_kg": r.get("payload_kg"),
                "reach_mm": r.get("reach_mm"),
                "dof": r.get("dof") or 6,
                "repeatability_mm": r.get("repeatability_mm"),
                "weight_kg": r.get("weight_kg"),
                "purpose": r.get("purpose"),
                "features": r.get("features"),
                "manufacturer_countries": [3],
                "manufacturer_country_ref": 3,
                "availability_status": 11,
                "product_url_scope": "family",
                "family_key": "rsm-machinery:sc-cobot-welding",
                "family_name": "SC Cobot Welding",
                "family_url": r.get("url"),
            },
        )
        r2 = client._get(f"robots/robots/{rid}/")
        errs = [
            f.get("flag")
            for f in (r2.get("quality_flags") or [])
            if isinstance(f, dict) and f.get("severity") == "error"
        ]
        print(f"  errors now: {errs}")
        print(f"  flags: {json.dumps(r2.get('quality_flags'), ensure_ascii=False)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
