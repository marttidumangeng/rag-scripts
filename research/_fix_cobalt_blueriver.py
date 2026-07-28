"""Fix Cobalt: enrich published 399; reject pending dupe 1659. Apply Blue River soft enrich."""
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
from discover_cobalt_blueriver import PRODUCTS, force_en, map_keys, taxonomy_ids

US_ID = 20
AVAILABLE = 11


def enrich_399(client: ResearchApiClient, tax: dict) -> None:
    for name in (
        "Cobalt Security Robot",
        "Cobalt Robot",
        "Cobalt Indoor Security Robot",
    ):
        try:
            client._patch("robots/robots/399/", {"name": name})
            print("399 rename OK", name)
            break
        except Exception as e:
            print("399 rename FAIL", name, e)

    desc = (
        "The Cobalt Security Robot is Cobalt AI's autonomous indoor security AMR "
        "for enterprise campuses. It patrols with onboard sensing and AI, escalating "
        "events to Cobalt Monitoring Intelligence for human-in-the-loop response."
    )
    purpose = (
        "Autonomous indoor security patrol and facility checks\n"
        "Human-in-the-loop event response via remote specialists"
    )
    features = (
        "OEM cobaltai.com/security-robots: autonomous indoor patrol for offices/"
        "campuses; onboard AI + multi-sensor suite (cameras, environmental sensors); "
        "event-only uplink to Cobalt Monitoring Intelligence; two-way A/V with remote "
        "robot specialists; scheduled facility/safety checks; access-control and "
        "elevator integrations; RaaS deployment model. Soft: generation (R2/R3) typed "
        "curb weight/speed not on primary OEM page this pass."
    )
    body: dict[str, Any] = {
        "url": "https://www.cobaltai.com/security-robots/",
        "family_key": "cobalt:security-robot",
        "family_name": "Cobalt Security Robot",
        "family_url": "https://www.cobaltai.com/security-robots/",
        "availability_status": AVAILABLE,
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "description": desc,
        "purpose": purpose,
        "features": features,
        "tags": ["Cobalt", "Security", "AMR", "Patrol", "Indoor", "RaaS", "USA"],
        "notes": "[AI Research] Soft-patched published CJK shell 399; reject pending dupe 1659",
        "uses": map_keys(tax, "uses", "patrol|monitoring|inspection"),
        "industries": map_keys(tax, "industries", "security|healthcare|manufacturing|logistics"),
        "movement_types": map_keys(tax, "movement", "wheeled"),
    }
    client._patch("robots/robots/399/", body)
    after = client._get("robots/robots/399/")
    force_en(
        client,
        399,
        {
            "name": after.get("name") or "Cobalt Robot",
            "description": desc,
            "features": features,
            "purpose": purpose,
        },
    )
    print(
        "399 now",
        after.get("name"),
        after.get("family_key"),
        len(after.get("features") or ""),
    )


def apply_blueriver(client: ResearchApiClient, tax: dict) -> None:
    for spec in PRODUCTS:
        if spec["company_slug"] != "blue-river-technology":
            continue
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        notes = (
            f"[AI Research] Enrich 2026-07-20: US; family {spec['family_key']}; "
            f"availability {spec['availability_status']}; EN soft patch."
        )
        staging = _RESEARCH / "staging" / "robots" / "blue-river-technology"
        staging.mkdir(parents=True, exist_ok=True)
        row = {
            "id": spec["id"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "company_slug": "blue-river-technology",
            "company_name": "Blue River Technology",
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
            "information_source_urls": [s["url"] for s in spec["sources"]],
        }
        for k in ("payload_kg", "weight_kg", "speed", "runtime_minutes", "height_mm"):
            if spec.get(k) is not None:
                row[k] = spec[k]
        path = staging / f"{spec['variant_code'].lower()}.json"
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
            "name": spec["name"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "url": spec["url"],
            "notes": notes,
            "tags": spec["tags"],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
        }
        for k in ("payload_kg", "weight_kg", "speed", "runtime_minutes", "height_mm"):
            if spec.get(k) is not None:
                body[k] = spec[k]
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patch OK", spec["id"])
        except Exception as e:
            print("patch FAIL", spec["id"], e)
        force_en(client, spec["id"], row)


def main() -> int:
    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    enrich_399(client, tax)
    apply_blueriver(client, tax)
    print(
        "NEXT: reject 1659 as duplicate of 399 via "
        "moderate_robots.py --company-id 213 --apply --reject-ids 1659 "
        '--reason "duplicate: keep published Cobalt Robot 399"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
