"""Curated Flytrex (1448) soft enrich — Sky / Sky2 delivery drones.

OEM: flytrex.com (JS shell — specs from Flytrex BusinessWire + FAA FTX-M600P).
US manufacturer country=20. Leave pending_review.

ENRICH:
  Sky2 (3646) — Available; 8.8 lb payload; partnership press hero
  Sky (2866) — Discontinued predecessor; 6.6 lb / FTX-M600P class; clear junk CDN

Usage:
  python discover_flytrex_robots.py
  python discover_flytrex_robots.py --apply --copy-media
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH = Path(__file__).resolve().parent
SERVER = _RESEARCH.parent.parent / "robotaigeek-server"
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_ID = 1448
COMPANY_SLUG = "flytrex"
COMPANY_NAME = "Flytrex"
COMPANY_WEBSITE = "https://www.flytrex.com/"
US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4

KT = 1.852  # knots → km/h
IN = 25.4  # inch → mm
LB = 0.453592

SKY2_PRESS = (
    "https://www.businesswire.com/news/home/20260423234109/en/"
    "In-a-First-for-Drone-Delivery-Flytrex-and-Little-Caesars-Can-Now-Deliver-"
    "Two-Large-Pizzas-to-Your-Door"
)
SKY2_HERO = (
    "https://s3.divcom.com/www.commercialuavnews.com/images/"
    "little-caesars-flytrex-drone-delivery.jpg.medium.800x800.jpg"
)

IMAGE_TODO_SKY = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "Prior CDN hero was an FPV landscape still (prop tips over countryside), "
    "not a Flytrex Sky airframe product shot. flytrex.com is a JS marketing shell "
    "with no server-rendered product gallery this pass; BusinessWire multimedia "
    "blocked (403). Do NOT reuse the Sky2 Little Caesars partnership graphic "
    "as a Sky sibling substitute.\n"
    "ACTION FOR TEAM: source a licensed Sky / FTX-M600P product still from "
    "Flytrex press kit or OEM.\n"
    "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
    "---\n"
)

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 3646,
        "name": "Flytrex Sky2 Delivery Drone",
        "model_name": "Sky2",
        "variant_code": "sky2",
        "variant_label": "Sky2",
        "url": "https://www.flytrex.com/",
        "family_key": "flytrex:sky",
        "family_name": "Sky",
        "family_url": "https://www.flytrex.com/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "payload_kg": round(8.8 * LB, 2),  # 8.8 lb
        "hero_url": SKY2_HERO,
        "clear_image": False,
        "purpose": (
            "Suburban restaurant meal delivery by air\n"
            "Family-size food orders with tethered backyard drop"
        ),
        "description": (
            "Sky2 is Flytrex's current autonomous delivery octocopter for suburban "
            "food delivery, carrying up to 8.8 lb (family-size pizza orders) across "
            "about a 4-mile radius with dual-battery redundancy and RTK GNSS."
        ),
        "features": (
            "OEM Flytrex BusinessWire (2026-04-23 Little Caesars): Sky2 octocopter "
            "with eight motors for in-flight redundancy; dual-battery architecture; "
            "GNSS + RTK centimeter-class nav; AI flight logic; up to 8.8 lb (~4.0 kg) "
            "payload; up to 4-mile delivery radius; average ~4.5 min takeoff-to-drop; "
            "remote curbside restaurant pickup; tethered winch drop. Soft: curb "
            "weight, airframe dims, cruise speed, and MSRP not disclosed on public "
            "OEM pages (flytrex.com is JS shell)."
        ),
        "use_keys": "delivery|transport",
        "industry_keys": "logistics|food-beverage|retail",
        "category_slugs": "aerial|drone|delivery-robots",
        "movement_keys": "aerial",
        "tags": ["Flytrex", "Sky2", "Delivery", "UAV", "Octocopter", "Food", "USA"],
        "sources": [
            {"url": SKY2_PRESS, "type": "press", "title": "Flytrex Sky2 BusinessWire"},
            {
                "url": "https://www.flytrex.com/",
                "type": "website",
                "title": "Flytrex home",
            },
            {
                "url": "https://uavcoach.com/flytrex-us-factory/",
                "type": "press",
                "title": "UAV Coach Sky2 vs prior model",
            },
        ],
    },
    {
        "id": 2866,
        "name": "Flytrex Sky Delivery Drone",
        "model_name": "Sky",
        "variant_code": "sky",
        "variant_label": "Sky",
        "url": "https://www.flytrex.com/",
        "family_key": "flytrex:sky",
        "family_name": "Sky",
        "family_url": "https://www.flytrex.com/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "payload_kg": round(6.6 * LB, 2),  # 6.6 lb prior delivery class
        "weight_kg": round(34 * LB, 2),  # FAA FTX-M600P MTOW 34 lb
        "length_mm": round(53 * IN),
        "width_mm": round(53 * IN),
        "height_mm": round(31 * IN),
        "speed": round(30 * KT, 2),  # FAA CONOPS max cruise 30 kt
        "hero_url": None,
        "clear_image": True,
        "image_todo": IMAGE_TODO_SKY,
        "purpose": (
            "Prior-gen suburban package and food delivery\n"
            "Backyard tethered drop for restaurant orders"
        ),
        "description": (
            "Flytrex Sky is the prior delivery airframe class (superseded by Sky2), "
            "aligned with Flytrex's ~6.6 lb payload commercial operations and the "
            "FAA FTX-M600P hexacopter type criteria."
        ),
        "features": (
            "Prior delivery platform vs Sky2 (UAV Coach / Flytrex launch coverage): "
            "~6.6 lb (~3.0 kg) payload; ~2.5 mile class radius before Sky2's 4-mile "
            "stretch. FAA special class criteria for Flytrex FTX-M600P: MTOW 34 lb "
            "(~15.4 kg); approx 53×53×31 in (~1346×1346×787 mm); max cruise 30 kt "
            "(~55.6 km/h); ops ≤230 ft AGL. Soft: public flytrex.com does not publish "
            "a Sky datasheet; consumer-era 3 lb hobby Sky is a different SKU — this "
            "row is the delivery predecessor to Sky2."
        ),
        "use_keys": "delivery|transport",
        "industry_keys": "logistics|food-beverage|retail",
        "category_slugs": "aerial|drone|delivery-robots",
        "movement_keys": "aerial",
        "tags": [
            "Flytrex",
            "Sky",
            "Delivery",
            "UAV",
            "Hexacopter",
            "Discontinued",
            "USA",
        ],
        "sources": [
            {
                "url": "https://www.flytrex.com/",
                "type": "website",
                "title": "Flytrex home",
            },
            {
                "url": "https://uavcoach.com/flytrex-us-factory/",
                "type": "press",
                "title": "Prior model 6.6 lb vs Sky2",
            },
            {
                "url": (
                    "https://www.federalregister.gov/documents/2022/03/28/2022-06379/"
                    "airworthiness-criteria-special-class-airworthiness-criteria-for-"
                    "the-flytrex-inc-ftx-m600p-unmanned"
                ),
                "type": "regulation",
                "title": "FAA FTX-M600P airworthiness criteria",
            },
            {"url": SKY2_PRESS, "type": "press", "title": "Sky2 superseding context"},
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
                "source_hash": f"flytrex-en-{rid}-20260720-{loc}",
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


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    last = ""
    for attempt in range(4):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return f"ok {resp.text[:120]}"
            if resp.status_code not in (500, 502, 503, 504):
                return f"HTTP {resp.status_code} {(resp.text or '')[:80]}"
            last = f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2**attempt)
    return f"fail {last}"


def patch_company(client: ResearchApiClient) -> None:
    body = {
        "website": COMPANY_WEBSITE,
        "country_id": US_ID,
        "notes": (
            "[AI Research] 2026-07-20 overnight: website → flytrex.com; country US."
        ),
    }
    for path in (f"companies/{COMPANY_ID}/", f"companies/companies/{COMPANY_ID}/"):
        try:
            client._patch(path, body)
            print("company patched", path)
            return
        except Exception as e:
            print("company patch warn", path, e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    args = ap.parse_args()

    if not args.apply:
        for p in PRODUCTS:
            print(
                p["id"],
                p["name"],
                p["family_key"],
                p["availability_status"],
                "hero" if p.get("hero_url") else "IMAGE-TODO",
            )
        return 0

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    patch_company(client)

    for spec in PRODUCTS:
        notes = (
            f"[AI Research] Flytrex enrich 2026-07-20: US; family {spec['family_key']}; "
            f"availability={spec['availability_status']}; flytrex.com + BusinessWire/"
            f"FAA cites."
        )
        if spec.get("image_todo"):
            notes = spec["image_todo"] + notes
        info_urls = [s["url"] for s in spec["sources"]]
        hero = spec.get("hero_url")
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
            "image": hero or "",
            "images": [hero] if hero else [],
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
        for k in (
            "payload_kg",
            "weight_kg",
            "speed",
            "runtime_minutes",
            "length_mm",
            "width_mm",
            "height_mm",
        ):
            if spec.get(k) is not None:
                row[k] = spec[k]
        path = staging / f"{spec['variant_code']}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name)
        replace_media = bool(hero) or bool(spec.get("clear_image"))
        print(
            "import",
            spec["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=replace_media,
                status="pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            ),
        )
        body: dict[str, Any] = {
            "name": spec["name"],
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
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "product_url_scope": spec["product_url_scope"],
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
        ):
            if spec.get(k) is not None:
                body[k] = spec[k]
        if spec.get("clear_image") and not hero:
            body["image"] = None
            body["s3_image"] = None
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patch OK", spec["id"])
        except Exception as e:
            print("patch FAIL", spec["id"], e)
            slim = {
                k: body[k]
                for k in list(body)
                if k not in ("tags", "uses", "industries", "movement_types")
            }
            client._patch(f"robots/robots/{spec['id']}/", slim)
            print("slim patch OK", spec["id"])
        force_en(client, spec["id"], row)
        if args.copy_media and hero:
            print("  copy-media", copy_media(spec["id"]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
