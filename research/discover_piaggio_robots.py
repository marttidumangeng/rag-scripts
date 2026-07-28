"""Curated Piaggio Fast Forward (236) soft enrich — gitamini + gita plus.

OEM (2026-07-20): piaggiofastforward.com shop + compare blog + knowledge.mygita.com

Usage:
  python discover_piaggio_robots.py --apply
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

COMPANY_SLUG = "piaggio-fast-forward"
COMPANY_NAME = "Piaggio Fast Forward"
US_ID = 20
AVAILABLE = 11

# Conversions: lb→kg, mph→km/h, in→mm where needed
PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 3767,
        "name": "gitamini",
        "model_name": "gitamini",
        "variant_code": "gitamini",
        "variant_label": "mini",
        "url": "https://piaggiofastforward.com/shop/gitamini",
        "family_key": "piaggio:gita",
        "family_name": "gita",
        "family_url": "https://piaggiofastforward.com/",
        "product_url_scope": "exact_variant",
        "payload_kg": 9.07,  # 20 lb
        "weight_kg": 12.7,  # 28 lb
        "speed": 9.66,  # 6 mph
        "runtime_minutes": 420,  # ~7 h continuous
        "length_mm": 455,
        "width_mm": 420,
        "height_mm": 465,
        "price_usd": 2875.0,
        "purpose": (
            "Hands-free personal cargo follow-me transport\n"
            "Pedestrian sidewalk and indoor gear carrying"
        ),
        "description": (
            "gitamini is Piaggio Fast Forward's compact two-wheeled cargo robot that "
            "pairs to a user and follows while carrying up to about 20 lb of gear, "
            "designed for sidewalks, shops, and light personal logistics."
        ),
        "features": (
            "OEM PFF shop/blog + knowledge.mygita: follow-me pairing via mygita app; "
            "up to ~20 lb (~9 kg) cargo / ~1000 in³ class bin; empty weight ~28 lb "
            "(~12.7 kg); dims ~455×420×465 mm; top speed ~6 mph (~9.7 km/h); up to "
            "~7 h / ~21 miles continuous travel; ~2 h recharge; USB charge port in "
            "bin; removable/open lid options; pedestrian etiquette navigation. Soft: "
            "Grogu™ special edition is a skin/variant of this SKU, not a separate row."
        ),
        "use_keys": "delivery|transport|helping|companion",
        "industry_keys": "retail|consumer|logistics",
        "category_slugs": "delivery-robots|service-robots|mobile-robots",
        "tags": [
            "AMR",
            "Piaggio",
            "gita",
            "gitamini",
            "Follow-me",
            "Cargo",
            "Consumer",
            "USA",
        ],
        "sources": [
            {
                "url": "https://piaggiofastforward.com/shop/gitamini",
                "type": "website",
                "title": "OEM shop gitamini",
            },
            {
                "url": "https://piaggiofastforward.com/blog/introducing-gitamini",
                "type": "website",
                "title": "Introducing gitamini",
            },
            {
                "url": "https://piaggiofastforward.com/blog/choose-your-robot-gitaplus-vs-gitamini",
                "type": "website",
                "title": "gitaplus vs gitamini",
            },
            {
                "url": "https://knowledge.mygita.com/introduction-to-gita",
                "type": "website",
                "title": "Meet gitaplus & gitamini",
            },
        ],
    },
    {
        "id": 3765,
        "name": "gita plus",
        "model_name": "gitaplus",
        "variant_code": "gitaplus",
        "variant_label": "plus",
        "url": "https://piaggiofastforward.com/shop/gitaplus",
        "family_key": "piaggio:gita",
        "family_name": "gita",
        "family_url": "https://piaggiofastforward.com/",
        "product_url_scope": "exact_variant",
        "payload_kg": 18.14,  # 40 lb
        "weight_kg": 22.68,  # 50 lb
        "speed": 9.66,  # 6 mph
        "runtime_minutes": 300,  # ~5 h continuous (knowledge base)
        "length_mm": 635,
        "width_mm": 560,
        "height_mm": 655,
        "price_usd": None,
        "purpose": (
            "Larger hands-free personal cargo follow-me transport\n"
            "Family and light commercial gear carrying"
        ),
        "description": (
            "gita plus (gitaplus) is Piaggio Fast Forward's larger two-wheeled cargo "
            "robot that follows its user while carrying up to about 40 lb, with longer "
            "range and a built-in Bluetooth speaker for personal and light business use."
        ),
        "features": (
            "OEM PFF shop/blog + knowledge.mygita: follow-me pairing via mygita app; "
            "up to ~40 lb (~18 kg) payload / ~4000 in³ cargo; empty weight ~50 lb "
            "(~22.7 kg); dims ~635×560×655 mm; top speed ~6 mph (~9.7 km/h); up to "
            "~5 h continuous / ~18 miles; ~2 h recharge; radar-aided tracking; "
            "built-in Bluetooth speaker; USB charge port; removable lid. Soft: MSRP "
            "not typed this pass."
        ),
        "use_keys": "delivery|transport|helping|companion",
        "industry_keys": "retail|consumer|logistics|hospitality",
        "category_slugs": "delivery-robots|service-robots|mobile-robots",
        "tags": [
            "AMR",
            "Piaggio",
            "gita",
            "gitaplus",
            "gita plus",
            "Follow-me",
            "Cargo",
            "Consumer",
            "USA",
        ],
        "sources": [
            {
                "url": "https://piaggiofastforward.com/shop/gitaplus",
                "type": "website",
                "title": "OEM shop gitaplus",
            },
            {
                "url": "https://piaggiofastforward.com/blog/meet-the-newest-robot-gitaplus",
                "type": "website",
                "title": "Meet gitaplus",
            },
            {
                "url": "https://knowledge.mygita.com/gitaplus-physical-overview",
                "type": "website",
                "title": "gitaplus physical overview",
            },
            {
                "url": "https://piaggiofastforward.com/blog/choose-your-robot-gitaplus-vs-gitamini",
                "type": "website",
                "title": "gitaplus vs gitamini",
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
                "source_hash": f"piaggio-en-force-{rid}-20260720-{loc}",
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
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        notes = (
            f"[AI Research] Piaggio enrich 2026-07-20: US; family {spec['family_key']}; "
            f"Available; OEM typed specs from shop/blog/knowledge base."
        )
        info_urls = [s["url"] for s in spec["sources"]]
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
            "movement_type_keys": "wheeled",
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "payload_kg": spec.get("payload_kg"),
            "weight_kg": spec.get("weight_kg"),
            "speed": spec.get("speed"),
            "runtime_minutes": spec.get("runtime_minutes"),
            "length_mm": spec.get("length_mm"),
            "width_mm": spec.get("width_mm"),
            "height_mm": spec.get("height_mm"),
            "price_usd": spec.get("price_usd"),
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": info_urls,
        }
        path = staging / f"{spec['variant_code']}.json"
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
            "movement_types": map_keys(tax, "movement", "wheeled"),
        }
        for k in (
            "payload_kg",
            "weight_kg",
            "speed",
            "runtime_minutes",
            "length_mm",
            "width_mm",
            "height_mm",
            "price_usd",
        ):
            if spec.get(k) is not None:
                body[k] = spec[k]
        client._patch(f"robots/robots/{spec['id']}/", body)
        force_en(client, spec["id"], row)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
