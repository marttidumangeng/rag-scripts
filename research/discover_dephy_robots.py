"""Curated Dephy (814) soft enrich — Sidekick Starter Pack kit SKU.

Published sibling: Sidekick (354). Starter Pack is the retail kit
(pair + batteries/charger/shoes/case) at shop.dephy.com — keep as variant,
not a reject-dupe.

Usage:
  python discover_dephy_robots.py --apply
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

COMPANY_SLUG = "dephy"
COMPANY_NAME = "Dephy"
US_ID = 20
AVAILABLE = 11

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 5088,
        "name": "Sidekick Starter Pack",
        "model_name": "Sidekick",
        "variant_code": "Sidekick-Starter-Pack",
        "variant_label": "Starter Pack",
        "url": "https://shop.dephy.com/products/sidekick-starter-pack",
        "family_key": "dephy:sidekick",
        "family_name": "Sidekick",
        "family_url": "https://dephy.com/",
        "product_url_scope": "exact_variant",
        "weight_kg": 1.4,
        "price_usd": 4500.0,  # DEPRECATED — API field is price_min/price_max/price_currency
        "price_min": 4500.0,
        "price_max": 4500.0,
        "price_currency": "USD",
        "purpose": (
            "Powered ankle boost for everyday walking\n"
            "Retail starter kit with paired Sidekicks and accessories"
        ),
        "description": (
            "The Sidekick Starter Pack is Dephy's retail kit for the Sidekick powered "
            "ankle footwear system — a wearable that adds a propulsive heel boost each "
            "step to make everyday walking easier (wellness product, not a medical device)."
        ),
        "features": (
            "OEM shop.dephy.com Sidekick Starter Pack (~$4,500): wearable powered-at-"
            "the-ankle Sidekick pair; dual batteries + dual-bay charger; compatible "
            "shoes; carrying case; ~1.4 kg class cited on prior research; custom fit; "
            "intuitive everyday use; 30-day return policy on shop. Soft: runtime/DoF "
            "not typed on PDP scrape; OEM states not a medical device."
        ),
        "use_keys": "rehabilitation|helping",
        "industry_keys": "healthcare|consumer",
        "category_slugs": "exoskeleton-robots|wearable-robots",
        "movement_keys": "legged",
        "tags": [
            "Dephy",
            "Sidekick",
            "Exoskeleton",
            "Ankle",
            "Wearable",
            "Starter Pack",
            "USA",
        ],
        "sources": [
            {
                "url": "https://shop.dephy.com/products/sidekick-starter-pack",
                "type": "website",
                "title": "OEM shop Starter Pack",
            },
            {
                "url": "https://dephy.com/",
                "type": "website",
                "title": "Dephy home",
            },
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
                "source_hash": f"dephy-en-{rid}-20260720-{loc}",
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


def patch_published_sidekick(client: ResearchApiClient, tax: dict) -> None:
    """Align published Sidekick (354) into same family if gaps remain."""
    rid = 354
    try:
        existing = client._get(f"robots/robots/{rid}/")
    except Exception as e:
        print("skip 354", e)
        return
    body: dict[str, Any] = {
        "family_key": "dephy:sidekick",
        "family_name": "Sidekick",
        "family_url": "https://dephy.com/",
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": AVAILABLE,
        "notes": "[AI Research] Family align with Starter Pack 5088 2026-07-20",
    }
    if not (existing.get("features") or "") or len(existing.get("features") or "") < 40:
        body["features"] = (
            "OEM dephy.com: powered ankle footwear; propulsive heel boost each step; "
            "everyday walking assist; wellness (not medical device); wearable lightweight "
            "design. Soft: kit contents live on Starter Pack SKU."
        )
    if not existing.get("family_key"):
        client._patch(f"robots/robots/{rid}/", body)
        print("patched published Sidekick 354 family")
    else:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "family_key": "dephy:sidekick",
                "family_name": "Sidekick",
                "family_url": "https://dephy.com/",
                "manufacturer_countries": [US_ID],
            },
        )
        print("reasserted Sidekick 354 family/US")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    for spec in PRODUCTS:
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        notes = (
            f"[AI Research] Dephy enrich 2026-07-20: US; family {spec['family_key']}; "
            f"Available; Starter Pack kit variant of Sidekick."
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
            "image": img,
            "images": [img] if img else [],
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
            "weight_kg": spec.get("weight_kg"),
            "price_min": spec.get("price_min"),
            "price_max": spec.get("price_max"),
            "price_currency": spec.get("price_currency"),
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": [s["url"] for s in spec["sources"]],
        }
        path = staging / "sidekick-starter-pack.json"
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
        if spec.get("price_min") is not None:
            body["price_min"] = spec["price_min"]
            body["price_max"] = spec.get("price_max") or spec["price_min"]
            body["price_currency"] = spec.get("price_currency") or "USD"
        body["information_source_urls"] = [s["url"] for s in spec["sources"]]
        body["url"] = spec["url"]
        client._patch(f"robots/robots/{spec['id']}/", body)
        force_en(client, spec["id"], row)

    if args.apply:
        patch_published_sidekick(client, tax)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
