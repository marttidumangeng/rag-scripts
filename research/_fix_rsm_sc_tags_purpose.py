"""Clear remaining soft gaps on RSM SC cobots (tags CharField + restamp)."""
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
CN = 3
TAGS = "6-Axis, Collaborative, Industrial, Material Handling, Welding"
PURPOSE = "Collaborative arc welding"


def main() -> int:
    client = ResearchApiClient()
    for rid in IDS:
        r = client._get(f"robots/robots/{rid}/")
        # purpose: short task phrase (not multi-line list)
        client._patch(
            f"robots/robots/{rid}/",
            {
                "purpose": PURPOSE,
                "tags": [t.strip() for t in TAGS.split(",")],
                "manufacturer_countries": [CN],
                "manufacturer_country_ref": CN,
                "availability_status": 11,
                "status": "pending_review",
                "payload_kg": r.get("payload_kg"),
                "reach_mm": r.get("reach_mm"),
                "dof": r.get("dof") or 6,
                "repeatability_mm": r.get("repeatability_mm"),
                "weight_kg": r.get("weight_kg"),
                "product_url_scope": "family",
                "family_key": "rsm-machinery:sc-cobot-welding",
                "family_name": "SC Cobot Welding",
                "family_url": r.get("url"),
            },
        )
        row = {
            "company_slug": "rsm-machinery",
            "company_name": "RSM Machinery",
            "source_locale": "en",
            "name": r.get("name"),
            "model_name": r.get("model_name") or r.get("name"),
            "url": r.get("url"),
            "description": r.get("description") or "ERSM SC cobot.",
            "purpose": PURPOSE,
            "features": r.get("features") or "ERSM SC-series collaborative welding robot.",
            "information_source_urls": [r.get("url")],
            "notes": r.get("notes") or "[AI Research] Family PDP restamp.",
            "manufacturer_country_code": "CN",
            "availability_status_key": "available",
            "payload_kg": r.get("payload_kg"),
            "reach_mm": r.get("reach_mm"),
            "dof": r.get("dof") or 6,
            "repeatability_mm": r.get("repeatability_mm"),
            "weight_kg": r.get("weight_kg"),
            "family_key": "rsm-machinery:sc-cobot-welding",
            "family_name": "SC Cobot Welding",
            "family_url": r.get("url"),
            "product_url_scope": "family",
            "category_slugs": "industrial-robots",
            "sub_category_slug": "manufacturing-industrial",
            "movement_type_keys": "stationary|fixed",
            "industry_keys": "manufacturing|industrial|metalworking",
            "use_keys": "welding|material-handling|machine-tending",
            "tags": TAGS.replace(", ", "|"),
        }
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
        client._patch(
            f"robots/robots/{rid}/",
            {
                "purpose": PURPOSE,
                "tags": [t.strip() for t in TAGS.split(",")],
                "manufacturer_countries": [CN],
                "manufacturer_country_ref": CN,
                "availability_status": 11,
                "status": "pending_review",
                "payload_kg": r.get("payload_kg"),
                "reach_mm": r.get("reach_mm"),
                "dof": r.get("dof") or 6,
                "repeatability_mm": r.get("repeatability_mm"),
                "weight_kg": r.get("weight_kg"),
            },
        )
        # second restamp so quality_flags see tags + country
        result2 = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=False,
            replace_media=False,
            replace_videos=False,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(1),
        )
        client._patch(
            f"robots/robots/{rid}/",
            {
                "purpose": PURPOSE,
                "tags": [t.strip() for t in TAGS.split(",")],
                "manufacturer_countries": [CN],
                "manufacturer_country_ref": CN,
                "availability_status": 11,
                "status": "pending_review",
            },
        )
        r2 = client._get(f"robots/robots/{rid}/")
        errs = [
            f.get("flag")
            for f in (r2.get("quality_flags") or [])
            if isinstance(f, dict) and f.get("severity") == "error"
        ]
        warns = [
            f.get("flag")
            for f in (r2.get("quality_flags") or [])
            if isinstance(f, dict) and f.get("severity") == "warn"
        ]
        print(
            json.dumps(
                {
                    "id": rid,
                    "name": r2.get("name"),
                    "purpose": r2.get("purpose"),
                    "tags": r2.get("tags"),
                    "errors": errs,
                    "warns": warns,
                    "features_len": len((r2.get("features") or "").strip()),
                    "specs": {
                        k: r2.get(k)
                        for k in (
                            "payload_kg",
                            "reach_mm",
                            "dof",
                            "repeatability_mm",
                            "weight_kg",
                        )
                    },
                    "import": {
                        "u1": result.get("updated_count"),
                        "u2": result2.get("updated_count"),
                    },
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
