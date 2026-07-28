"""Curated FarmBot Inc. (34) soft enrich — Genesis v1.8 + Express discontinued.

KEEP / ENRICH (pending_review):
  2760 FarmBot Genesis v1.8     — Available; US; family farmbot:genesis
  2761 FarmBot Genesis XL v1.8  — Available; US; same family
  3571 FarmBot Express v1.0    — Discontinued; US; family farmbot:express
  3572 FarmBot Express v1.1    — Discontinued; US; family farmbot:express

OEM (2026-07-20): farm.bot sells Genesis / Genesis XL v1.8; Express is docs-only
legacy (express.farm.bot). Soft: prices not typed (Shopify variants); bed size
from OEM PDP (Genesis 1.5×3 m, XL 3×6 m); weights already on records.

Leave published FarmBot (92) alone (zh shell — not requested).

Usage:
  python discover_farmbot_robots.py
  python discover_farmbot_robots.py --apply
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

COMPANY_ID = 34
COMPANY_SLUG = "farmbot-inc"
COMPANY_NAME = "FarmBot Inc."
US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 2760,
        "name": "FarmBot Genesis v1.8",
        "model_name": "Genesis v1.8",
        "variant_code": "Genesis-v1.8",
        "variant_label": "Genesis",
        "url": "https://farm.bot/products/farmbot-genesis-v1-8",
        "family_key": "farmbot:genesis",
        "family_name": "Genesis",
        "family_url": "https://farm.bot/products/farmbot-genesis-v1-8",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "weight_kg": 19.5,
        "length_mm": 3000,  # 3 m track / bed length (OEM PDP)
        "width_mm": 1500,  # 1.5 m
        "release_year": 2024,
        "purpose": (
            "Automated planting, watering, and weeding in a raised bed\n"
            "Open-source CNC farming for home, classroom, and research plots"
        ),
        "description": (
            "FarmBot Genesis v1.8 is an open-source CNC farming kit that automates "
            "planting, watering, weeding, and monitoring across a 1.5 m × 3 m "
            "raised garden bed."
        ),
        "features": (
            "OEM farm.bot/products/farmbot-genesis-v1-8: flagship Genesis kit for "
            "prosumers/enthusiasts; serviceable raised-bed footprint about 1.5×3 m "
            "(height support ~0.75–1.5 m); open-source hardware/software; Raspberry "
            "Pi 4B + Farmduino v1.6; 5× TMC2130 drivers; 4× NEMA 17 steppers; IP67 "
            "USB camera; 100 W supply; modular tools for plant/water/weed; ships as "
            "kit. Soft: kit weight ~19.5 kg retained from prior research; public "
            "MSRP not typed (Shopify variants)."
        ),
        "use_keys": "agriculture|farming|education|research",
        "industry_keys": "agriculture|education|research",
        "tags": [
            "FarmBot",
            "Genesis",
            "CNC",
            "Open-Source",
            "Agriculture",
            "Gardening",
            "USA",
        ],
    },
    {
        "id": 2761,
        "name": "FarmBot Genesis XL v1.8",
        "model_name": "Genesis XL v1.8",
        "variant_code": "Genesis-XL-v1.8",
        "variant_label": "Genesis XL",
        "url": "https://farm.bot/products/farmbot-genesis-xl-v1-8",
        "family_key": "farmbot:genesis",
        "family_name": "Genesis",
        "family_url": "https://farm.bot/products/farmbot-genesis-v1-8",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "weight_kg": 24.0,
        "length_mm": 6000,  # 6 m
        "width_mm": 3000,  # 3 m
        "release_year": 2024,
        "purpose": (
            "Large-bed automated planting, watering, and weeding\n"
            "Family-scale open-source CNC farming (about 4× Genesis area)"
        ),
        "description": (
            "FarmBot Genesis XL v1.8 expands the Genesis CNC farming kit to about "
            "3 m × 6 m — roughly 400% the area of Genesis — for family-scale "
            "automated vegetable production."
        ),
        "features": (
            "OEM farm.bot/products/farmbot-genesis-xl-v1-8: Genesis XL covers ~400% "
            "the area of Genesis (~3×6 m bed); same open-source stack (Pi 4B, "
            "Farmduino v1.6, TMC2130/NEMA 17, IP67 camera, 100 W); modular "
            "plant/water/weed tooling; kit assembly. Soft: kit weight ~24 kg "
            "retained from prior research; MSRP not typed."
        ),
        "use_keys": "agriculture|farming|education|research",
        "industry_keys": "agriculture|education|research",
        "tags": [
            "FarmBot",
            "Genesis",
            "Genesis XL",
            "CNC",
            "Open-Source",
            "Agriculture",
            "USA",
        ],
    },
    {
        "id": 3571,
        "name": "FarmBot Express v1.0",
        "model_name": "Express v1.0",
        "variant_code": "Express-v1.0",
        "variant_label": "v1.0",
        "url": "https://express.farm.bot/docs/v1.0",
        "family_key": "farmbot:express",
        "family_name": "Express",
        "family_url": "https://express.farm.bot/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "weight_kg": None,
        "length_mm": None,
        "width_mm": None,
        "release_year": 2019,
        "purpose": (
            "Entry-level automated planting, watering, and weeding\n"
            "Legacy affordable open-source home farming kit"
        ),
        "description": (
            "FarmBot Express v1.0 was the lower-cost open-source CNC farming kit "
            "for home gardens. Current shop leads with Genesis / Genesis XL v1.8; "
            "Express remains as hardware documentation."
        ),
        "features": (
            "Legacy Express docs (express.farm.bot/docs/v1.0): simplified "
            "open-source FarmBot for automated planting, watering, and weeding. "
            "Soft: Discontinued — not sold on farm.bot shop (Genesis v1.8 current); "
            "typed curb dims not on Express docs scrape."
        ),
        "use_keys": "agriculture|farming|education",
        "industry_keys": "agriculture|education",
        "tags": ["FarmBot", "Express", "CNC", "Open-Source", "Discontinued", "USA"],
    },
    {
        "id": 3572,
        "name": "FarmBot Express v1.1",
        "model_name": "Express v1.1",
        "variant_code": "Express-v1.1",
        "variant_label": "v1.1",
        "url": "https://express.farm.bot/docs/v1.1",
        "family_key": "farmbot:express",
        "family_name": "Express",
        "family_url": "https://express.farm.bot/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "weight_kg": None,
        "length_mm": None,
        "width_mm": None,
        "release_year": None,
        "purpose": (
            "Entry-level automated planting, watering, and weeding\n"
            "Legacy Express kit revision after v1.0"
        ),
        "description": (
            "FarmBot Express v1.1 updated the affordable Express CNC farming kit "
            "with minor hardware/docs improvements over v1.0. Superseded in the "
            "shop by Genesis / Genesis XL v1.8."
        ),
        "features": (
            "Legacy Express docs (express.farm.bot/docs/v1.1): Express v1.1 "
            "improvements over v1.0 for automated planting, watering, weeding. "
            "Soft: Discontinued relative to current Genesis catalog; no typed "
            "curb dims on docs scrape."
        ),
        "use_keys": "agriculture|farming|education",
        "industry_keys": "agriculture|education",
        "tags": ["FarmBot", "Express", "CNC", "Open-Source", "Discontinued", "USA"],
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
                "source_hash": f"farmbot-en-force-{rid}-20260720-{loc}",
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    for spec in PRODUCTS:
        notes = (
            f"[AI Research] FarmBot enrich 2026-07-20: US; family {spec['family_key']}; "
            f"avail={spec['availability_status']}; Genesis bed dims from OEM PDP."
        )
        # Keep existing CDN image — soft patch only
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""

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
            "image": img,
            "images": [img] if img else [],
            "source_locale": "en",
            "availability_status": spec["availability_status"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "movement_type_keys": "stationary",
            "category_slugs": "agricultural-robots|service-robots",
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "weight_kg": spec.get("weight_kg"),
            "length_mm": spec.get("length_mm"),
            "width_mm": spec.get("width_mm"),
            "release_year": spec.get("release_year"),
            "notes": notes,
            "research_notes": notes,
            "sources": [
                {"url": spec["url"], "type": "website", "title": f"OEM {spec['name']}"},
                {"url": "https://farm.bot/", "type": "website", "title": "FarmBot home"},
            ],
            "information_source_urls": [spec["url"], "https://farm.bot/"],
        }
        path = staging / f"{spec['variant_code'].lower()}.json"
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
            "availability_status": spec["availability_status"],
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "name": spec["name"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "notes": notes,
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", "stationary"),
        }
        for k in ("weight_kg", "length_mm", "width_mm", "release_year"):
            if spec.get(k) is not None:
                body[k] = spec[k]
        client._patch(f"robots/robots/{spec['id']}/", body)
        force_en(client, spec["id"], row)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
