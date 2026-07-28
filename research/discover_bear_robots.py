"""Curated Bear Robotics (198) soft enrich — Servi + Carti fleet.

OEM nav (bearrobotics.ai 2026-07-20):
  Servi, Servi Plus, Servi Q, Carti 100, Carti Low-Profile, Servi Clean

ENRICH all 10 pending — US; Available; families; features ≥40; purpose task lines;
payload from model designation / OEM claims where citeable.

Usage:
  python discover_bear_robots.py --apply
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

COMPANY_SLUG = "bear-robotics"
COMPANY_NAME = "Bear Robotics"
US_ID = 20
AVAILABLE = 11

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 2686,
        "name": "Servi Plus",
        "model_name": "Servi Plus",
        "variant_code": "Servi-Plus",
        "variant_label": "Plus",
        "url": "https://www.bearrobotics.ai/servi-plus",
        "family_key": "bear:servi",
        "family_name": "Servi",
        "family_url": "https://www.bearrobotics.ai/servi",
        "product_url_scope": "exact_variant",
        "payload_kg": 39.9,  # 88 lb OEM claim in stored desc
        "weight_kg": None,
        "speed": 4.32,
        "runtime_minutes": 600,
        "purpose": (
            "Food and drink delivery in restaurants and hospitality\n"
            "Multi-robot table service and bussing support"
        ),
        "description": (
            "Servi Plus is Bear Robotics' higher-capacity hospitality delivery AMR "
            "for restaurant food and drink runs, with multi-robot orchestration."
        ),
        "features": (
            "OEM bearrobotics.ai/servi-plus: hospitality delivery AMR; expanded "
            "tray capacity vs base Servi; carries up to ~88 lb (40 kg) cited in "
            "prior OEM copy; all-floor navigation; multi-robot orchestration via "
            "Bear Universe; ~4.32 km/h / long runtime retained from prior research. "
            "Soft: curb weight not re-cited this pass."
        ),
        "use_keys": "delivery|food-delivery|room-service",
        "industry_keys": "restaurants|hospitality|hotels|healthcare",
        "category_slugs": "delivery-robots|service-robots",
        "tags": ["AMR", "Bear", "Servi", "Servi Plus", "Hospitality", "Delivery", "USA"],
    },
    {
        "id": 3708,
        "name": "Servi mini",
        "model_name": "Servi mini",
        "variant_code": "Servi-mini",
        "variant_label": "mini",
        "url": "https://www.bearrobotics.ai/servi",
        "family_key": "bear:servi",
        "family_name": "Servi",
        "family_url": "https://www.bearrobotics.ai/servi",
        "product_url_scope": "family",
        "payload_kg": None,
        "weight_kg": None,
        "speed": None,
        "runtime_minutes": None,
        "purpose": (
            "Compact hospitality dish delivery and table clearing\n"
            "Staff-assist food service in restaurants and senior living"
        ),
        "description": (
            "Servi mini is Bear Robotics' compact hospitality AMR for delivering "
            "and clearing dishes so staff can focus on guest experience."
        ),
        "features": (
            "OEM bearrobotics.ai/servi: compact Servi-family hospitality AMR for "
            "delivery and bussing; LiDAR/smart navigation in crowded floors; part "
            "of Bear Universe multi-robot platform. Soft: typed payload/curb weight "
            "not on page scrape this pass; features expanded from empty stub."
        ),
        "use_keys": "delivery|food-delivery|helping",
        "industry_keys": "restaurants|hospitality|healthcare|hotels",
        "category_slugs": "delivery-robots|service-robots",
        "tags": ["AMR", "Bear", "Servi", "Servi mini", "Hospitality", "Delivery", "USA"],
    },
    {
        "id": 2691,
        "name": "Servi Q",
        "model_name": "Servi Q",
        "variant_code": "Servi-Q",
        "variant_label": "Q",
        "url": "https://www.bearrobotics.ai/servi-q",
        "family_key": "bear:servi",
        "family_name": "Servi",
        "family_url": "https://www.bearrobotics.ai/servi",
        "product_url_scope": "exact_variant",
        "payload_kg": None,
        "weight_kg": 45.0,
        "speed": 2.52,
        "runtime_minutes": None,
        "purpose": (
            "Spill-safe food and drink delivery in narrow restaurant layouts\n"
            "Coordinated multi-robot table service"
        ),
        "description": (
            "Servi Q is Bear's compact hospitality delivery AMR tuned for narrow "
            "restaurant floors with spill-free tray handling and multi-robot coordination."
        ),
        "features": (
            "OEM bearrobotics.ai/servi-q: compact design; spill-free navigation; "
            "backward movement + bump detection; wheel cleaning; adjustable trays; "
            "built-in promo display; coordinated multi-robot runs. Soft: ~45 kg / "
            "~2.52 km/h retained from prior research."
        ),
        "use_keys": "delivery|food-delivery",
        "industry_keys": "restaurants|hospitality|hotels|healthcare",
        "category_slugs": "delivery-robots|service-robots",
        "tags": ["AMR", "Bear", "Servi", "Servi Q", "Hospitality", "Delivery", "USA"],
    },
    {
        "id": 2692,
        "name": "Servi Clean",
        "model_name": "Servi Clean",
        "variant_code": "Servi-Clean",
        "variant_label": "Clean",
        "url": "https://www.bearrobotics.ai/servi-clean",
        "family_key": "bear:servi-clean",
        "family_name": "Servi Clean",
        "family_url": "https://www.bearrobotics.ai/servi-clean",
        "product_url_scope": "exact_variant",
        "payload_kg": None,
        "weight_kg": 45.8,
        "speed": 4.32,  # 1.2 m/s
        "runtime_minutes": 240,
        "purpose": (
            "Autonomous commercial floor sweeping, mopping, and vacuuming\n"
            "Hard-floor and carpet cleaning in hospitality and healthcare"
        ),
        "description": (
            "Servi Clean is Bear Robotics' commercial floor-cleaning AMR for "
            "sweeping, mopping, vacuuming, and scrubbing across hospitality and "
            "healthcare spaces."
        ),
        "features": (
            "OEM bearrobotics.ai/servi-clean: vacuuming + dust mopping; cleans hard "
            "floors and carpets; ~1.2 m/s max (~4.32 km/h); ~1.5 h charge cited in "
            "prior copy; ~45.8 kg / ~4 h runtime retained. Soft: Servi Clean Max "
            "mentioned on OEM page — not a separate DB row this pass."
        ),
        "use_keys": "cleaning",
        "industry_keys": "cleaning|hospitality|hotels|restaurants|healthcare",
        "category_slugs": "cleaning-robots|service-robots",
        "tags": ["AMR", "Bear", "Servi Clean", "Cleaning", "Hospitality", "USA"],
    },
    {
        "id": 2687,
        "name": "Carti 100",
        "model_name": "Carti 100",
        "variant_code": "Carti-100",
        "variant_label": "100",
        "url": "https://www.bearrobotics.ai/carti100",
        "family_key": "bear:carti",
        "family_name": "Carti",
        "family_url": "https://www.bearrobotics.ai/carti100",
        "product_url_scope": "exact_variant",
        "payload_kg": 100.0,
        "weight_kg": 55.0,
        "speed": None,
        "runtime_minutes": 540,
        "purpose": (
            "Material handling and transport in warehouses and factories\n"
            "Infrastructure-light AMR logistics"
        ),
        "description": (
            "Carti 100 is Bear Robotics' entry Carti AMR for warehouse and factory "
            "material handling without major infrastructure changes."
        ),
        "features": (
            "OEM bearrobotics.ai/carti100: scalable AMR for material handling/"
            "transport; works without infrastructure changes; ~100 kg class payload "
            "from model designation; ~55 kg / ~9 h runtime retained from prior "
            "research. Soft: peak speed not typed this pass."
        ),
        "use_keys": "material-handling|delivery|transport",
        "industry_keys": "logistics|warehousing|manufacturing|healthcare",
        "category_slugs": "mobile-robots|amr",
        "tags": ["AMR", "Bear", "Carti", "Carti 100", "Warehouse", "Logistics", "USA"],
    },
    {
        "id": 3707,
        "name": "Carti Low-Profile",
        "model_name": "Carti Low-Profile",
        "variant_code": "Carti-LP",
        "variant_label": "Low-Profile",
        "url": "https://www.bearrobotics.ai/carti-low-profile",
        "family_key": "bear:carti-lp",
        "family_name": "Carti Low-Profile",
        "family_url": "https://www.bearrobotics.ai/carti-low-profile",
        "product_url_scope": "family",
        "payload_kg": None,
        "weight_kg": None,
        "speed": None,
        "runtime_minutes": None,
        "purpose": (
            "Low-profile heavy-duty AMR cart transport in warehouses\n"
            "Family hub for Carti LP payload variants"
        ),
        "description": (
            "Carti Low-Profile is Bear's low-profile industrial AMR family for "
            "warehouse and factory logistics; payload variants include Carti 400/"
            "600/1000/1500."
        ),
        "features": (
            "OEM bearrobotics.ai/carti-low-profile: low-profile industrial AMR line "
            "with dynamic lift, SLAM navigation, obstacle avoidance, QR docking, "
            "multi-robot orchestration. Soft: family landing — typed payload lives "
            "on Carti 400/600/1000/1500 variant rows."
        ),
        "use_keys": "material-handling|delivery|transport",
        "industry_keys": "logistics|warehousing|manufacturing",
        "category_slugs": "mobile-robots|amr",
        "tags": ["AMR", "Bear", "Carti", "Carti Low-Profile", "Warehouse", "USA"],
    },
    {
        "id": 2688,
        "name": "Carti 400",
        "model_name": "Carti 400",
        "variant_code": "Carti-400",
        "variant_label": "400",
        "url": "https://www.bearrobotics.ai/carti-low-profile",
        "family_key": "bear:carti-lp",
        "family_name": "Carti Low-Profile",
        "family_url": "https://www.bearrobotics.ai/carti-low-profile",
        "product_url_scope": "exact_variant",
        "payload_kg": 400.0,
        "weight_kg": 90.0,
        "speed": 7.2,
        "runtime_minutes": 480,
        "purpose": (
            "400 kg-class low-profile warehouse material transport\n"
            "Dynamic-lift AMR logistics"
        ),
        "description": (
            "Carti 400 is a low-profile Bear Carti AMR variant for warehouse and "
            "industrial transport in the ~400 kg payload class."
        ),
        "features": (
            "OEM Carti Low-Profile family (bearrobotics.ai/carti-low-profile): "
            "precision AMR; obstacle avoidance; dynamic lift; SLAM; QR docking. "
            "Payload ~400 kg from model designation; ~90 kg / ~7.2 km/h / ~8 h "
            "runtime retained from prior research."
        ),
        "use_keys": "material-handling|delivery|transport",
        "industry_keys": "logistics|warehousing|manufacturing",
        "category_slugs": "mobile-robots|amr",
        "tags": ["AMR", "Bear", "Carti", "Carti 400", "Warehouse", "USA"],
    },
    {
        "id": 3706,
        "name": "Carti 600",
        "model_name": "Carti 600",
        "variant_code": "Carti-600",
        "variant_label": "600",
        "url": "https://www.bearrobotics.ai/carti-low-profile",
        "family_key": "bear:carti-lp",
        "family_name": "Carti Low-Profile",
        "family_url": "https://www.bearrobotics.ai/carti-low-profile",
        "product_url_scope": "exact_variant",
        "payload_kg": 600.0,
        "weight_kg": None,
        "speed": None,
        "runtime_minutes": None,
        "purpose": (
            "600 kg-class low-profile warehouse material transport\n"
            "Factory-floor AMR logistics"
        ),
        "description": (
            "Carti 600 is Bear's low-profile Carti AMR for factory and warehouse "
            "logistics with about 600 kg payload capacity."
        ),
        "features": (
            "OEM Carti Low-Profile family: low-profile industrial AMR; SLAM; "
            "dynamic lift; obstacle avoidance; QR docking. Payload ~600 kg from "
            "model designation / prior OEM copy. Soft: curb weight/speed not on "
            "variant scrape; features expanded from empty stub."
        ),
        "use_keys": "material-handling|delivery|transport",
        "industry_keys": "logistics|warehousing|manufacturing",
        "category_slugs": "mobile-robots|amr",
        "tags": ["AMR", "Bear", "Carti", "Carti 600", "Warehouse", "USA"],
    },
    {
        "id": 2689,
        "name": "Carti 1000",
        "model_name": "Carti 1000",
        "variant_code": "Carti-1000",
        "variant_label": "1000",
        "url": "https://www.bearrobotics.ai/carti-low-profile#carti-1000",
        "family_key": "bear:carti-lp",
        "family_name": "Carti Low-Profile",
        "family_url": "https://www.bearrobotics.ai/carti-low-profile",
        "product_url_scope": "exact_variant",
        "payload_kg": 1000.0,
        "weight_kg": 190.0,
        "speed": 7.2,
        "runtime_minutes": 480,
        "purpose": (
            "1000 kg-class low-profile warehouse material transport\n"
            "Heavy-duty industrial AMR logistics"
        ),
        "description": (
            "Carti 1000 is a heavy-duty low-profile Bear Carti AMR for warehouse "
            "and industrial transport in the ~1000 kg payload class."
        ),
        "features": (
            "OEM Carti Low-Profile family: precision AMR; obstacle avoidance; "
            "dynamic lift; SLAM; QR docking. Payload ~1000 kg from model "
            "designation; ~190 kg / ~7.2 km/h / ~8 h runtime retained."
        ),
        "use_keys": "material-handling|delivery|transport",
        "industry_keys": "logistics|warehousing|manufacturing",
        "category_slugs": "mobile-robots|amr",
        "tags": ["AMR", "Bear", "Carti", "Carti 1000", "Warehouse", "USA"],
    },
    {
        "id": 2690,
        "name": "Carti 1500",
        "model_name": "Carti 1500",
        "variant_code": "Carti-1500",
        "variant_label": "1500",
        "url": "https://www.bearrobotics.ai/carti-low-profile#carti-1500",
        "family_key": "bear:carti-lp",
        "family_name": "Carti Low-Profile",
        "family_url": "https://www.bearrobotics.ai/carti-low-profile",
        "product_url_scope": "exact_variant",
        "payload_kg": 1500.0,
        "weight_kg": 200.0,
        "speed": 7.2,
        "runtime_minutes": 480,
        "purpose": (
            "1500 kg-class low-profile warehouse material transport\n"
            "Highest Carti LP payload for industrial automation"
        ),
        "description": (
            "Carti 1500 is Bear's highest low-profile Carti AMR variant for "
            "demanding warehouse and industrial transport (~1500 kg class)."
        ),
        "features": (
            "OEM Carti Low-Profile family: precision AMR; obstacle avoidance; "
            "dynamic lift; SLAM; QR docking. Payload ~1500 kg from model "
            "designation; ~200 kg / ~7.2 km/h / ~8 h runtime retained."
        ),
        "use_keys": "material-handling|delivery|transport",
        "industry_keys": "logistics|warehousing|manufacturing",
        "category_slugs": "mobile-robots|amr",
        "tags": ["AMR", "Bear", "Carti", "Carti 1500", "Warehouse", "USA"],
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
                "source_hash": f"bear-en-force-{rid}-20260720-{loc}",
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
            f"[AI Research] Bear enrich 2026-07-20: US; family {spec['family_key']}; "
            f"Available; soft specs from OEM/model designation."
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
            "movement_type_keys": "wheeled",
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "payload_kg": spec.get("payload_kg"),
            "weight_kg": spec.get("weight_kg"),
            "speed": spec.get("speed"),
            "runtime_minutes": spec.get("runtime_minutes"),
            "notes": notes,
            "research_notes": notes,
            "sources": [
                {"url": spec["url"], "type": "website", "title": f"OEM {spec['name']}"},
                {
                    "url": "https://www.bearrobotics.ai/",
                    "type": "website",
                    "title": "Bear Robotics home",
                },
            ],
            "information_source_urls": [spec["url"], "https://www.bearrobotics.ai/"],
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
            "availability_status": AVAILABLE,
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
            "movement_types": map_keys(tax, "movement", "wheeled"),
        }
        for k in ("payload_kg", "weight_kg", "speed", "runtime_minutes"):
            if spec.get(k) is not None:
                body[k] = spec[k]
        client._patch(f"robots/robots/{spec['id']}/", body)
        force_en(client, spec["id"], row)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
