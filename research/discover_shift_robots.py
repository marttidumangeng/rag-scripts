"""Shift Robotics (856): EN rename + enrich Moonwalkers / Moonwalkers Aero.

Pending CJK twins both named 人工智能驱动的机器人鞋:
  4027 → Moonwalkers (8-wheel trail / gen-1) — already on /products/moonwalkers
  577  → Moonwalkers Aero (4-wheel urban) — family_url already Aero PDP

OEM: https://shiftrobotics.io
Specs cited from PDPs (mph→km/h; lbs→kg). Retail $1,399 / $999 (Sold out on PDP
but product line still listed → Available).

Usage:
  python discover_shift_robots.py --apply
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

COMPANY_SLUG = "shift-robotics"
COMPANY_NAME = "Shift Robotics"
US_ID = 20
AVAILABLE = 11
MPH = 1.60934  # mph → km/h
LB = 0.453592

MW_URL = "https://shiftrobotics.io/products/moonwalkers"
AERO_URL = "https://shiftrobotics.io/products/moonwalkers-aero"
COMPARE = "https://shiftrobotics.io"

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4027,
        "name": "Moonwalkers",
        "model_name": "Moonwalkers",
        "variant_code": "Moonwalkers",
        "variant_label": "Gen1",
        "url": MW_URL,
        "family_key": "shift:moonwalkers",
        "family_name": "Moonwalkers",
        "family_url": MW_URL,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "speed": round(7.0 * MPH, 2),  # 7 mph
        "weight_kg": round(5.2 * LB, 2),  # 5.2 lb each (PDP); compare table ~5.3
        "payload_kg": 100.0,  # user weight limit 220 lb / 100 kg
        "price_min": 1399.0,
        "price_max": 1399.0,
        "price_currency": "USD",
        "purpose": (
            "Hands-free gait-controlled walking speed assist\n"
            "All-terrain personal micro-mobility footwear"
        ),
        "description": (
            "Moonwalkers are Shift Robotics' AI gait-controlled robotic shoes. An "
            "eight-wheel powered drivetrain boosts natural walking up to about 2.5× "
            "speed while keeping hands free — named one of TIME's Best Inventions of 2023."
        ),
        "features": (
            "OEM shiftrobotics.io Moonwalkers PDP: top speed 7 mph; range ~6–7 mi "
            "(test note: 165 lb / 75 kg, 5.4 mph avg); product weight 5.2 lb each; "
            "user weight limit 220 lb (100 kg); rated power 400 W; max torque 10 Nm; "
            "max slope 10°; FOC motor control; brake distance 3 ft dry; IPX4; battery "
            "3.0 Ah; USB-C PD charge ≤65 W; charge ~1.5 h (60% in ~30 min); 8-powered "
            "wheels; flexing toeplate ≤30°; ShiftAI / ShiftOS gait controller; sizing "
            "W8–M12; retail $1,399 USD. Soft: shop showed Sold out this pass — still "
            "listed as current product line."
        ),
        "use_keys": "transport|helping|entertainment",
        "industry_keys": "consumer|home|commercial",
        "category_slugs": "personal-mobility",
        "movement_keys": "wearable|wheeled",
        "tags": [
            "Shift Robotics",
            "Moonwalkers",
            "Robotic shoes",
            "Wearable",
            "Gait AI",
            "Micro-mobility",
            "USA",
        ],
        "sources": [
            {"url": MW_URL, "type": "website", "title": "OEM Moonwalkers"},
            {"url": COMPARE, "type": "website", "title": "Shift Robotics"},
        ],
        "hero_url": (
            "https://shiftrobotics.io/cdn/shop/files/"
            "shift-moonwalkers-turntable-0000.png?v=1726772733&width=1000"
        ),
    },
    {
        "id": 577,
        "name": "Moonwalkers Aero",
        "model_name": "Moonwalkers Aero",
        "variant_code": "Moonwalkers-Aero",
        "variant_label": "Aero",
        "url": AERO_URL,
        "family_key": "shift:moonwalkers",
        "family_name": "Moonwalkers",
        "family_url": MW_URL,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "speed": round(7.0 * MPH, 2),
        "weight_kg": round(4.2 * LB, 2),  # 4.2 lb each
        "payload_kg": 100.0,
        "price_min": 999.0,
        "price_max": 999.0,
        "price_currency": "USD",
        "purpose": (
            "Quiet urban walking speed assist\n"
            "Lightweight gait-controlled personal mobility footwear"
        ),
        "description": (
            "Moonwalkers Aero is Shift Robotics' lighter, quieter successor to "
            "Moonwalkers. A four-wheel powertrain and magnesium-alloy pack cut about "
            "1 lb per shoe while keeping the same 7 mph top speed and ShiftAI gait control."
        ),
        "features": (
            "OEM shiftrobotics.io Moonwalkers Aero PDP: top speed 7 mph; range ~6–7 mi; "
            "product weight 4.2 lb each; user weight limit 220 lb (100 kg); rated power "
            "350 W; max torque 8 Nm; max slope 10°; FOC; brake 3 ft dry; IPX4; battery "
            "3.0 Ah; USB-C PD ≤65 W; charge ~1.5 h; 4-wheel powertrain; ~50 dB class "
            "(vs ~70 dB gen-1); sizing W6–M12 with spacers; retail $999 USD. Soft: shop "
            "showed Sold out this pass — still listed as current product line."
        ),
        "use_keys": "transport|helping|entertainment",
        "industry_keys": "consumer|home|commercial",
        "category_slugs": "personal-mobility",
        "movement_keys": "wearable|wheeled",
        "tags": [
            "Shift Robotics",
            "Moonwalkers Aero",
            "Robotic shoes",
            "Wearable",
            "Gait AI",
            "Micro-mobility",
            "USA",
        ],
        "sources": [
            {"url": AERO_URL, "type": "website", "title": "OEM Moonwalkers Aero"},
            {"url": MW_URL, "type": "website", "title": "Moonwalkers family"},
            {"url": COMPARE, "type": "website", "title": "Shift Robotics"},
        ],
        "hero_url": (
            "https://shiftrobotics.io/cdn/shop/files/"
            "Moonwalkers_Turntable_V005_AERO0000.png?v=1727727293&width=1000"
        ),
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
                "source_hash": f"shift-en-{rid}-20260720-{loc}",
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
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    if not args.apply:
        print("dry-run: pass --apply to write")
        for p in PRODUCTS:
            print(
                f"  PEND {p['id']} {p['name']} fam={p['family_key']} "
                f"speed={p['speed']} wt={p['weight_kg']} ${p['price_min']}"
            )
        return 0

    for spec in PRODUCTS:
        notes = (
            f"[AI Research] Shift enrich 2026-07-20: US EN rename from CJK shell; "
            f"family {spec['family_key']}; OEM PDP specs (mph→km/h, lb→kg); "
            f"retail ${int(spec['price_min'])}; Available."
        )
        info_urls = [s["url"] for s in spec["sources"]]
        img = spec.get("hero_url") or ""
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
            "movement_type_keys": spec["movement_keys"],
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": info_urls,
            "speed": spec["speed"],
            "weight_kg": spec["weight_kg"],
            "payload_kg": spec["payload_kg"],
            "price_min": spec["price_min"],
            "price_max": spec["price_max"],
            "price_currency": spec["price_currency"],
        }
        path = staging / f"{spec['variant_code'].lower()}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name)
        print(
            "import",
            spec["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=True,
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
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "url": spec["url"],
            "information_source_urls": info_urls,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "notes": notes,
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
            "speed": spec["speed"],
            "weight_kg": spec["weight_kg"],
            "payload_kg": spec["payload_kg"],
            "price_min": spec["price_min"],
            "price_max": spec["price_max"],
            "price_currency": spec["price_currency"],
            "image": img,
        }
        client._patch(f"robots/robots/{spec['id']}/", body)
        client._patch(f"robots/robots/{spec['id']}/", {"tags": []})
        client._patch(f"robots/robots/{spec['id']}/", {"tags": spec["tags"]})
        force_en(client, spec["id"], row)

    # Clean company website tracking junk
    try:
        client._patch(
            "companies/856/",
            {"website": "https://shiftrobotics.io"},
        )
        print("company website cleaned → https://shiftrobotics.io")
    except Exception as e:
        print("company patch warn", e)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
