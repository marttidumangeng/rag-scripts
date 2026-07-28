"""Finish Ekso soft enrich after 1967 name PATCH 500."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from discover_ekso_robots import (
    PRODUCTS,
    force_en,
    map_keys,
    taxonomy_ids,
    US_ID,
)

# Skip NR already done; finish Indego without renaming if rename 500s
REMAINING_IDS = {1967, 437, 2481, 1968}


def main() -> int:
    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / "ekso-bionics"
    staging.mkdir(parents=True, exist_ok=True)

    for spec in PRODUCTS:
        if spec["id"] not in REMAINING_IDS:
            continue
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        notes = (
            f"[AI Research] Ekso enrich 2026-07-20: US; family {spec['family_key']}; "
            f"avail={spec['availability_status']}; soft fields filled when known."
        )
        info_urls = [s["url"] for s in spec["sources"]]
        # Keep existing display name if rename may 500 (Indego)
        name = existing.get("name") or spec["name"]
        if spec["id"] != 1967:
            name = spec["name"]
        row = {
            "id": spec["id"],
            "name": name,
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "company_slug": "ekso-bionics",
            "company_name": "Ekso Bionics",
            "manufacturer_country_code": "US",
            "manufacturer_country_codes": "US",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": spec["url"],
            "image": img,
            "images": [img] if img else [],
            "source_locale": "en",
            "availability_status": spec["availability_status"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "movement_type_keys": spec["movement_keys"],
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": info_urls,
        }
        if spec.get("weight_kg") is not None:
            row["weight_kg"] = spec["weight_kg"]
        path = staging / f"{spec['variant_code'].lower()}-b.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            "import",
            spec["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=False,
                status="pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            ),
        )
        body: dict[str, Any] = {
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": spec["availability_status"],
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "url": spec["url"],
            "information_source_urls": info_urls,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "notes": notes,
            "tags": spec["tags"],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
        }
        if spec.get("weight_kg") is not None:
            body["weight_kg"] = spec["weight_kg"]
        # Try rename only for non-Indego or after fields stick
        if spec["id"] != 1967:
            body["name"] = spec["name"]
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patch OK", spec["id"])
        except Exception as e:
            print("patch FAIL", spec["id"], e)
            # retry without tags/uses if needed
            slim = {
                k: body[k]
                for k in (
                    "manufacturer_countries",
                    "manufacturer_country_ref",
                    "availability_status",
                    "description",
                    "features",
                    "purpose",
                    "url",
                    "information_source_urls",
                    "family_key",
                    "family_name",
                    "family_url",
                    "notes",
                )
                if k in body
            }
            if spec.get("weight_kg") is not None:
                slim["weight_kg"] = spec["weight_kg"]
            try:
                client._patch(f"robots/robots/{spec['id']}/", slim)
                print("slim patch OK", spec["id"])
            except Exception as e2:
                print("slim FAIL", spec["id"], e2)
        force_en(client, spec["id"], {**row, "name": name})

    # Try clean Indego name via translation-sync only
    try:
        force_en(
            client,
            1967,
            {
                "name": "Ekso Indego Personal",
                "description": PRODUCTS[1]["description"],
                "features": PRODUCTS[1]["features"],
                "purpose": PRODUCTS[1]["purpose"],
            },
        )
        after = client._get("robots/robots/1967/")
        print("1967 name now", after.get("name"), "feats", len(after.get("features") or ""))
    except Exception as e:
        print("1967 name sync warn", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
