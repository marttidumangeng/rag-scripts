"""Curated soft enrich: XRobotics (114) xPizza Cube + Foundation (851) Phantom.

Usage:
  python discover_xrobotics_foundation.py --apply
  python discover_xrobotics_foundation.py --apply --only xrobotics|foundation
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

PRODUCTS: list[dict[str, Any]] = [
    {
        "company_id": 114,
        "company_slug": "xrobotics",
        "company_name": "XRobotics",
        "id": 5289,
        "name": "xPizza Cube",
        "model_name": "xPizza Cube",
        "variant_code": "xPizza-Cube",
        "variant_label": "Cube",
        "url": "https://www.xrobotics.io/specification",
        "family_key": "xrobotics:xpizza-cube",
        "family_name": "xPizza Cube",
        "family_url": "https://www.xrobotics.io/",
        "product_url_scope": "exact_variant",
        "payload_kg": None,
        "weight_kg": 76.0,
        "speed": None,
        "runtime_minutes": None,
        "length_mm": 711,  # depth 28"
        "width_mm": 508,  # 20"
        "height_mm": 787,  # 31"
        "dof": None,
        "purpose": (
            "Automated pizza sauce, cheese, and pepperoni topping\n"
            "High-volume commercial kitchen pizza assembly"
        ),
        "description": (
            "xPizza Cube is XRobotics' compact countertop pizza-topping robot that "
            "automatically dispenses sauce, cheese, and pepperoni for commercial "
            "kitchens, supporting crusts from about 8\" to 16\"."
        ),
        "features": (
            "OEM xrobotics.io/specification: crusts 8–16\"; pans/screens with up to "
            "2\" rim; hoppers ~2.4 gal (9 L) sauce, ~25 lb (11.3 kg) cheese, 6 "
            "pepperoni sticks up to ~360 mm; footprint ~20×31×28 in "
            "(508×787×711 mm W×H×D); ~190 lb / 76 kg empty; 120 V single-phase / "
            "~1060 W; up to ~100 pizzas/hour on marketing pages (adjustable volume "
            "cited in prior copy). Soft: lease/MSRP not typed this pass."
        ),
        "use_keys": "cooking",
        "industry_keys": "restaurants|food-service",
        "category_slugs": "food-service-robots",
        "tags": [
            "XRobotics",
            "xPizza Cube",
            "Pizza",
            "Food service",
            "Countertop",
            "Commercial kitchen",
            "USA",
        ],
        "movement_keys": "stationary",
        "sources": [
            {
                "url": "https://www.xrobotics.io/specification",
                "type": "website",
                "title": "xPizza Cube specifications",
            },
            {
                "url": "https://www.xrobotics.io/",
                "type": "website",
                "title": "XRobotics home",
            },
        ],
    },
    {
        "company_id": 851,
        "company_slug": "foundation-robotics",
        "company_name": "Foundation Robotics",
        "id": 2883,
        "name": "Phantom",
        "model_name": "Phantom",
        "variant_code": "Phantom",
        "variant_label": "base",
        "url": "https://foundation.bot/phantom",
        "family_key": "foundation:phantom",
        "family_name": "Phantom",
        "family_url": "https://foundation.bot/phantom",
        "product_url_scope": "exact_variant",
        "payload_kg": 40.0,  # 88.2 lb OEM primary claim
        "weight_kg": 80.0,
        "speed": 6.12,  # 1.7 m/s
        "runtime_minutes": None,
        "length_mm": None,
        "width_mm": None,
        "height_mm": 1800,  # 5'11"
        "dof": 29,
        "purpose": (
            "General-purpose humanoid manipulation and locomotion\n"
            "Autonomous work in human-scale industrial environments"
        ),
        "description": (
            "Phantom is Foundation's first production humanoid robot, designed for "
            "strong, fluid motion in human environments with cycloid actuators and "
            "a modular architecture."
        ),
        "features": (
            "OEM foundation.bot/phantom: production humanoid; height ~5'11\" "
            "(~1.8 m); weight ~176 lb (~80 kg); payload capacity ~88.2 lb (~40 kg) "
            "cited on primary hero specs; 29 DoF; speed ~1.7 m/s (~6.12 km/h); "
            "cycloid actuators (high torque density, low backlash, quiet); modular "
            "architecture. Soft: alternate on-page payload line also shows ~20 kg — "
            "kept 40 kg from primary lb claim; runtime not typed."
        ),
        "use_keys": "material-handling|helping|research",
        "industry_keys": "logistics|manufacturing|warehousing",
        "category_slugs": "humanoid-robots",
        "tags": [
            "Foundation",
            "Phantom",
            "Humanoid",
            "Cycloid",
            "Industrial",
            "USA",
        ],
        "movement_keys": "legged",
        "sources": [
            {
                "url": "https://foundation.bot/phantom",
                "type": "website",
                "title": "OEM Phantom",
            },
            {
                "url": "https://foundation.bot/",
                "type": "website",
                "title": "Foundation home",
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
                "source_hash": f"us-en-force-{rid}-20260720-{loc}",
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
    ap.add_argument("--only", choices=("xrobotics", "foundation", "all"), default="all")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)

    for spec in PRODUCTS:
        slug = spec["company_slug"]
        if args.only == "xrobotics" and slug != "xrobotics":
            continue
        if args.only == "foundation" and slug != "foundation-robotics":
            continue

        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        notes = (
            f"[AI Research] Enrich 2026-07-20: US; family {spec['family_key']}; "
            f"Available; OEM typed specs soft-patched."
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
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": [s["url"] for s in spec["sources"]],
        }
        for k in (
            "payload_kg",
            "weight_kg",
            "speed",
            "runtime_minutes",
            "length_mm",
            "width_mm",
            "height_mm",
            "dof",
        ):
            if spec.get(k) is not None:
                row[k] = spec[k]

        path = staging / f"{spec['variant_code'].lower()}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path)

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
        for k in (
            "payload_kg",
            "weight_kg",
            "speed",
            "runtime_minutes",
            "length_mm",
            "width_mm",
            "height_mm",
            "dof",
        ):
            if spec.get(k) is not None:
                body[k] = spec[k]
        client._patch(f"robots/robots/{spec['id']}/", body)
        force_en(client, spec["id"], row)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
