"""Curated soft enrich: Cobalt (213) + Blue River Technology (423).

Brightpick (375) skipped this pass — country_ref Czechia (not US drain).

Usage:
  python discover_cobalt_blueriver.py --apply
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

US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4

PRODUCTS: list[dict[str, Any]] = [
    {
        "company_slug": "cobalt-robotics",
        "company_name": "Cobalt Robotics",
        "id": 1659,
        "name": "Cobalt Security Robot",
        "model_name": "Cobalt Security Robot",
        "variant_code": "Cobalt-Security-Robot",
        "variant_label": "Security Robot",
        "url": "https://www.cobaltai.com/security-robots/",
        "family_key": "cobalt:security-robot",
        "family_name": "Cobalt Security Robot",
        "family_url": "https://www.cobaltai.com/security-robots/",
        "product_url_scope": "family",
        "availability_status": AVAILABLE,
        "payload_kg": None,
        "weight_kg": None,
        "speed": None,  # secondary R3 1.2 m/s not OEM-cited this pass
        "runtime_minutes": None,  # OEM FAQ ~8–10 h class — leave untyped if not hard number
        "height_mm": None,
        "purpose": (
            "Autonomous indoor security patrol and facility checks\n"
            "Human-in-the-loop event response via remote specialists"
        ),
        "description": (
            "The Cobalt Security Robot is Cobalt AI's autonomous indoor security AMR "
            "for enterprise campuses. It patrols with onboard sensing and AI, escalating "
            "events to Cobalt Monitoring Intelligence for human-in-the-loop response."
        ),
        "features": (
            "OEM cobaltai.com/security-robots: autonomous indoor patrol for offices/"
            "campuses; onboard AI + multi-sensor suite (cameras, environmental sensors); "
            "event-only uplink to Cobalt Monitoring Intelligence; two-way A/V with remote "
            "robot specialists; scheduled facility/safety checks; access-control and "
            "elevator integrations; RaaS deployment model. Soft: generation (R2/R3) and "
            "typed curb weight/speed not cited on primary OEM page this pass — prior CJK "
            "shell renamed to EN product name."
        ),
        "use_keys": "patrol|monitoring|inspection|security",
        "industry_keys": "security|healthcare|manufacturing|logistics",
        "category_slugs": "security-robots|mobile-robots",
        "movement_keys": "wheeled",
        "tags": [
            "Cobalt",
            "Security",
            "AMR",
            "Patrol",
            "Indoor",
            "RaaS",
            "USA",
        ],
        "sources": [
            {
                "url": "https://www.cobaltai.com/security-robots/",
                "type": "website",
                "title": "OEM Cobalt Security Robot",
            },
            {
                "url": "https://www.cobaltai.com/",
                "type": "website",
                "title": "Cobalt AI home",
            },
        ],
    },
    {
        "company_slug": "blue-river-technology",
        "company_name": "Blue River Technology",
        "id": 5042,
        "name": "See & Spray Ultimate",
        "model_name": "See & Spray Ultimate",
        "variant_code": "See-Spray-Ultimate",
        "variant_label": "Ultimate",
        "url": "https://www.bluerivertechnology.com/products/",
        "family_key": "blueriver:see-spray",
        "family_name": "See & Spray",
        "family_url": "https://www.bluerivertechnology.com/products/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "payload_kg": None,
        "weight_kg": None,
        "speed": 25.75,  # ~16 mph field speed cited in stored feats / Deere coverage
        "runtime_minutes": None,
        "height_mm": None,
        "purpose": (
            "Plant-level targeted herbicide spraying in row crops\n"
            "Real-time crop vs weed detection for precision agriculture"
        ),
        "description": (
            "See & Spray Ultimate is Blue River / John Deere's flagship precision "
            "spraying system that uses onboard cameras and deep learning to detect "
            "weeds in real time and apply herbicide only where needed in growing crops."
        ),
        "features": (
            "OEM bluerivertechnology.com/products + Deere coverage: deep learning + "
            "computer vision plant-level spray; ~36 boom cameras scanning thousands of "
            "sq ft/sec; targeted spray in corn/soy/cotton-class row crops; dual-tank/"
            "dual-nozzle Ultimate architecture for broadcast + targeted modes; field "
            "speeds cited up to ~12–16 mph (~19–26 km/h). Soft: Exact Deere SKU boom "
            "width/price not typed this pass."
        ),
        "use_keys": "agriculture|spraying",
        "industry_keys": "agriculture",
        "category_slugs": "agricultural-robots|mobile-robots",
        "movement_keys": "wheeled",
        "tags": [
            "Blue River",
            "John Deere",
            "See & Spray",
            "Ultimate",
            "Precision agriculture",
            "Herbicide",
            "USA",
        ],
        "sources": [
            {
                "url": "https://www.bluerivertechnology.com/products/",
                "type": "website",
                "title": "Blue River products",
            },
            {
                "url": "https://www.bluerivertechnology.com/",
                "type": "website",
                "title": "Blue River home",
            },
        ],
    },
    {
        "company_slug": "blue-river-technology",
        "company_name": "Blue River Technology",
        "id": 380,
        "name": "See & Spray",
        "model_name": "See & Spray",
        "variant_code": "See-Spray",
        "variant_label": "See & Spray",
        "url": "https://www.bluerivertechnology.com/products/",
        "family_key": "blueriver:see-spray",
        "family_name": "See & Spray",
        "family_url": "https://www.bluerivertechnology.com/products/",
        "product_url_scope": "family",
        "availability_status": AVAILABLE,
        "payload_kg": None,
        "weight_kg": None,
        "speed": None,
        "runtime_minutes": None,
        "height_mm": None,
        "purpose": (
            "AI plant-level weed detection and targeted spraying\n"
            "Precision herbicide application across field crops"
        ),
        "description": (
            "See & Spray is Blue River Technology's AI agriculture platform (now scaled "
            "on John Deere sprayers) that detects crops and weeds in real time and "
            "executes plant-level spray decisions instead of broadcast coverage."
        ),
        "features": (
            "OEM bluerivertechnology.com/products: deep learning at the edge; "
            "high-resolution vision; plant-level classification and actuation in "
            "milliseconds; deployed at scale on large row-crop sprayers; chemical "
            "reduction vs broadcast spraying. Family hub for Select/Ultimate variants. "
            "Soft: prior CJK purpose/desc rewritten to EN; typed boom specs live on "
            "Ultimate row."
        ),
        "use_keys": "agriculture|spraying",
        "industry_keys": "agriculture",
        "category_slugs": "agricultural-robots|mobile-robots",
        "movement_keys": "wheeled",
        "tags": [
            "Blue River",
            "John Deere",
            "See & Spray",
            "Precision agriculture",
            "Computer vision",
            "USA",
        ],
        "sources": [
            {
                "url": "https://www.bluerivertechnology.com/products/",
                "type": "website",
                "title": "Blue River products",
            }
        ],
    },
    {
        "company_slug": "blue-river-technology",
        "company_name": "Blue River Technology",
        "id": 381,
        "name": "LettuceBot",
        "model_name": "LettuceBot",
        "variant_code": "LettuceBot",
        "variant_label": "LettuceBot",
        "url": "https://www.bluerivertechnology.com/",
        "family_key": "blueriver:lettucebot",
        "family_name": "LettuceBot",
        "family_url": "https://www.bluerivertechnology.com/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "payload_kg": None,
        "weight_kg": None,
        "speed": None,
        "runtime_minutes": None,
        "height_mm": None,
        "purpose": (
            "Automated lettuce thinning and early weed control\n"
            "Plant-level vision decisions in specialty crop beds"
        ),
        "description": (
            "LettuceBot was Blue River Technology's early tractor-mounted agriculture "
            "robot that used computer vision to identify lettuce seedlings and "
            "selectively thin plants for optimal spacing — the precursor to See & Spray."
        ),
        "features": (
            "Historical Blue River / John Deere lineage: tractor-mounted lettuce "
            "thinner; computer vision plant ID; selective spray/remove for spacing; "
            "plant-level decisions at field speed; commercial use in Salinas/Yuma-class "
            "lettuce ops. Soft: Discontinued / superseded by See & Spray platform; "
            "throughput claims from secondary coverage not typed as hard OEM spec."
        ),
        "use_keys": "agriculture",
        "industry_keys": "agriculture",
        "category_slugs": "agricultural-robots|mobile-robots",
        "movement_keys": "wheeled",
        "tags": [
            "Blue River",
            "LettuceBot",
            "Agriculture",
            "Thinning",
            "Computer vision",
            "Discontinued",
            "USA",
        ],
        "sources": [
            {
                "url": "https://www.bluerivertechnology.com/",
                "type": "website",
                "title": "Blue River home",
            }
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
                "source_hash": f"us-en-force-{rid}-20260720b-{loc}",
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

    for spec in PRODUCTS:
        slug = spec["company_slug"]
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        notes = (
            f"[AI Research] Enrich 2026-07-20: US; family {spec['family_key']}; "
            f"availability {spec['availability_status']}; EN soft patch."
        )
        staging = _RESEARCH / "staging" / "robots" / slug
        staging.mkdir(parents=True, exist_ok=True)
        row: dict[str, Any] = {
            "id": spec["id"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "company_slug": slug,
            "company_name": spec["company_name"],
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

        path = staging / f"{spec['variant_code'].lower().replace(' ', '-')}.json"
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
        client._patch(f"robots/robots/{spec['id']}/", body)
        force_en(client, spec["id"], row)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
