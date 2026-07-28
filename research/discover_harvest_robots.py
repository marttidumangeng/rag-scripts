"""Curated Harvest Automation (1502) enrich — HV-100 Plant Handling Robot.

OEM: https://harvestai.com/ (alias harvestautomation.com). Datasheet:
https://harvestautomation.com/hv-100-product-data-sheet/
Specs: 24\"W × 21\"H, 100 lb curb, ≤25 lb container, 4–6 h battery.

Usage:
  python discover_harvest_robots.py
  python discover_harvest_robots.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_ID = 1502
COMPANY_SLUG = "harvest-automation"
COMPANY_NAME = "Harvest Automation"
US_ID = 20
AVAILABLE = 11

OEM_HOME = "https://harvestai.com/"
DATASHEET = "https://harvestautomation.com/hv-100-product-data-sheet/"
# Existing CDN hero visually verified as HV-100 product photo (OEM SSL expired locally).
CDN_HERO = (
    "https://cdn.robotaigeek.com/robots/original/"
    "robot-4979-hv-100-plant-handling-robot-v1783901314.png"
)
OEM_HERO = "https://harvestautomation.com/wp-content/uploads/2025/06/HV100.png"

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4979,
        "name": "HV-100 Plant Handling Robot",
        "model_name": "HV-100",
        "variant_code": "HV-100",
        "variant_label": "Plant Handling",
        "url": DATASHEET,
        "family_key": "harvest-automation:hv-100",
        "family_name": "HV-100",
        "family_url": OEM_HOME,
        "product_url_scope": "exact_variant",
        "weight_kg": 45.36,  # 100 lb datasheet
        "payload_kg": 11.34,  # up to 25 lb containers
        "width_mm": 610,  # 24 in
        "height_mm": 533,  # 21 in
        "runtime_minutes": 240,  # 4–6 h; cite low end
        "year": 2013,
        "purpose": (
            "Pot spacing in nursery and greenhouse beds\n"
            "Plant collection and consolidation\n"
            "Follow-me material handling alongside crews"
        ),
        "description": (
            "The HV-100 is Harvest Automation's autonomous plant-handling robot for "
            "nurseries and greenhouses. It spaces, collects, and consolidates potted "
            "plants on dirt, gravel, and paved floors without infrastructure changes, "
            "working safely alongside people since its 2013 US introduction."
        ),
        "features": (
            "OEM datasheet (harvestautomation.com / harvestai.com): spacing, collection, "
            "consolidation, Follow-Me; peak ~240 pots/hour ideal; indoor/outdoor nursery "
            "and greenhouse (dirt/dust/rain/sprinklers, 32–105°F); 24\" W × 21\" H, "
            "~100 lb curb; quick-swap battery 4–6 h; containers up to 25 lb, "
            "5–12.5\" diameter, 5.75\" to 15\"+ height; Wi-Fi/Ethernet dashboard; "
            "FCC Class A / CE; no programming; all-weather 24h ops. Soft: length not "
            "on datasheet; MSRP not public on OEM pages scraped."
        ),
        "use_keys": "agriculture|material-handling",
        "industry_keys": "agriculture",
        "category_slugs": "agricultural-robots|autonomous-mobile-robots",
        "movement_keys": "wheeled",
        "tags": [
            "Harvest Automation",
            "HV-100",
            "Nursery",
            "Greenhouse",
            "AMR",
            "Plant handling",
            "USA",
        ],
        "sources": [
            {"url": DATASHEET, "type": "website", "title": "HV-100 product data sheet"},
            {"url": OEM_HOME, "type": "website", "title": "Harvest Automation home"},
        ],
    },
]


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    def idx(path: str) -> dict[str, int]:
        rows = client._get(path)
        return {
            (r.get("key") or "").lower(): int(r["id"])
            for r in rows
            if r.get("key") and r.get("id")
        }

    return {
        "uses": idx("robots/uses/"),
        "industries": idx("robots/industries/"),
        "movement": idx("robots/movement-types/"),
    }


def map_keys(tax: dict[str, dict[str, int]], group: str, keys: str) -> list[int]:
    out = []
    for k in keys.split("|"):
        kid = tax[group].get(k.strip().lower())
        if kid:
            out.append(kid)
        else:
            print(f"  warn missing {group}={k}")
    return out


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"harvest-en-{rid}-20260720-{loc}",
                "translated_fields": {
                    "description": row.get("description") or "",
                    "features": row.get("features") or "",
                    "purpose": row.get("purpose") or "",
                    "name": row.get("name") or "",
                },
            }
            for loc in ("zh-CN", "zh-TW")
        ]
    }
    try:
        resp = client._session.post(
            client._url("robots/robots/translation-sync/?force=1"),
            json=sync,
            timeout=60,
        )
        print(f"  translation-sync {rid}: {resp.status_code}")
    except requests.RequestException as e:
        print(f"  translation-sync warn {rid}: {e}")


def patch_company(client: ResearchApiClient) -> None:
    body = {
        "website": OEM_HOME,
        "country_id": US_ID,
        "founded_year": 2008,
        "hq_address": "85 Rangeway Rd, Building 1, Billerica, MA 01862, USA",
        "short_description": (
            "US nursery/greenhouse AMR maker (Billerica, MA); HV-100 plant handling."
        ),
        "description": (
            "Harvest Automation Inc. (Billerica, Massachusetts) builds autonomous "
            "plant-handling robots for nurseries and greenhouses. Founded 2008; "
            "flagship HV-100 spaces, collects, and consolidates pots without mapping "
            "infrastructure. OEM: harvestai.com / harvestautomation.com."
        ),
        "notes": (
            "[AI Research] 2026-07-20 overnight: website set to harvestai.com "
            "(was empty); US HQ confirmed."
        ),
    }
    client._patch(f"companies/{COMPANY_ID}/", body)
    print("company patched website/country")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    if args.apply:
        patch_company(client)

    for spec in PRODUCTS:
        notes = (
            f"[AI Research] Harvest Automation enrich 2026-07-20: US; Available; "
            f"family {spec['family_key']}; datasheet dims/weight/payload/runtime; "
            f"OEM {OEM_HOME}."
        )
        row: dict[str, Any] = {
            "id": spec["id"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "US",
            "manufacturer_country_codes": "US",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": spec["url"],
            "image": CDN_HERO,
            "images": [CDN_HERO],
            "source_locale": "en",
            "availability_status": AVAILABLE,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "movement_type_keys": spec["movement_keys"],
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "weight_kg": spec["weight_kg"],
            "payload_kg": spec["payload_kg"],
            "width_mm": spec["width_mm"],
            "height_mm": spec["height_mm"],
            "runtime_minutes": spec["runtime_minutes"],
            "year": spec["year"],
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": [s["url"] for s in spec["sources"]],
        }
        path = staging / "hv-100.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name)

        if not args.apply:
            continue

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
            "availability_status": AVAILABLE,
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "url": spec["url"],
            "notes": notes,
            "tags": spec["tags"],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
            "weight_kg": spec["weight_kg"],
            "payload_kg": spec["payload_kg"],
            "width_mm": spec["width_mm"],
            "height_mm": spec["height_mm"],
            "runtime_minutes": spec["runtime_minutes"],
            "year": spec["year"],
            "information_source_urls": [s["url"] for s in spec["sources"]],
        }
        client._patch(f"robots/robots/{spec['id']}/", body)
        # Re-PATCH typed specs (bulk-import may pack payload into notes)
        client._patch(
            f"robots/robots/{spec['id']}/",
            {
                "payload_kg": spec["payload_kg"],
                "weight_kg": spec["weight_kg"],
                "width_mm": spec["width_mm"],
                "height_mm": spec["height_mm"],
                "runtime_minutes": spec["runtime_minutes"],
                "availability_status": AVAILABLE,
                "family_key": spec["family_key"],
                "family_name": spec["family_name"],
                "family_url": spec["family_url"],
            },
        )
        force_en(client, spec["id"], row)
        after = client._get(f"robots/robots/{spec['id']}/")
        print(
            "verify",
            after.get("id"),
            "country=",
            bool(after.get("manufacturer_countries")),
            "fam=",
            after.get("family_key"),
            "w=",
            after.get("weight_kg"),
            "payload=",
            after.get("payload_kg"),
            "avail=",
            after.get("availability_status"),
        )

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
