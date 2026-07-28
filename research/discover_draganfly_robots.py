"""Curated soft enrich — Draganfly Innovations Inc. (1444) UAVs.

OEM: https://draganfly.com
Manufacturer country: US (stakeholder overnight US drain; OEM Blue UAS / USA-made Cube).

Pending:
  Apex (5102), Commander 3XL (5101), Heavy Lift (3616) — Available
  Tango2 (2819) — Discontinued (legacy products page)

Usage:
  python discover_draganfly_robots.py
  python discover_draganfly_robots.py --apply --copy-media
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
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_ID = 1444
COMPANY_SLUG = "draganfly-innovations"
COMPANY_NAME = "Draganfly Innovations Inc."
COMPANY_WEBSITE = "https://draganfly.com"
US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
IN_LB = 0.45359237
IN_MM = 25.4

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 5102,
        "name": "Draganfly Apex",
        "model_name": "Apex",
        "variant_code": "apex",
        "variant_label": "Apex",
        "url": "https://draganfly.com/draganfly-apex/",
        "family_key": "draganfly:apex",
        "family_name": "Apex",
        "family_url": "https://draganfly.com/draganfly-apex/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "hero_url": "https://draganfly.com/wp-content/uploads/2024/10/Apex-Hero-Update-1-scaled.webp",
        "gallery": [
            "https://draganfly.com/wp-content/uploads/2024/10/Apex-Hero-Update-1-scaled.webp",
            "https://draganfly.com/wp-content/uploads/2024/10/Apex-Gremsy.webp",
            "https://draganfly.com/wp-content/uploads/2024/10/Apex-Size-New-Image-2-scaled.webp",
        ],
        "payload_kg": round(6.6 * IN_LB, 2),  # 6.6 lb OEM
        "length_mm": round(47 * IN_MM),  # 47" L
        "width_mm": round(44 * IN_MM),  # 44" W
        "height_mm": round(12 * IN_MM),  # 12" H
        "runtime_minutes": 45,
        "price_min": 16495,
        "price_max": 16495,
        "price_currency": "USD",
        "dof": None,
        "purpose": (
            "Rapid-response aerial inspection and public-safety ISR\n"
            "Multispectral / EO-IR payload missions"
        ),
        "description": (
            "Draganfly Apex is a portable, Blue UAS–certified multirotor sUAS for "
            "rapid-response commercial and government missions. Folding arms, Cube H7 "
            "triple-IMU autopilot, and a ~6.6 lb payload bay support EO/IR, RGB, and "
            "multispectral sensors. Designed and manufactured in North America."
        ),
        "features": (
            "OEM draganfly.com/draganfly-apex: payload 6.6 lb / ~3.0 kg; flight time "
            "45 min (varies with payload); dimensions 47×44×12 in "
            f"({round(47*IN_MM)}×{round(44*IN_MM)}×{round(12*IN_MM)} mm); starting "
            "price $16,495 USD. Blue UAS certified; USA-made Cube H7 with triple "
            "redundant IMU; folding arms/props; HD FPV; Apex Ultra / Apex Core "
            "edge-compute and long-range radio configs; Gremsy VIO EO/IR, MicaSense "
            "RedEdge-P, Sony A5100 gimbal payload options. Soft: empty weight not on PDP."
        ),
        "use_keys": "inspection|surveillance|monitoring|patrol|scanning|search-and-rescue",
        "industry_keys": "security|defence|government|agriculture|energy",
        "category_slugs": "aerial|drone",
        "movement_keys": "aerial|flying",
        "tags": [
            "Draganfly", "Apex", "UAV", "Drone", "Blue UAS", "NDAA", "Multirotor", "USA"
        ],
        "sources": [
            {"url": "https://draganfly.com/draganfly-apex/", "type": "website", "title": "OEM Apex"},
            {"url": "https://draganfly.com/", "type": "website", "title": "Draganfly"},
        ],
    },
    {
        "id": 5101,
        "name": "Draganfly Commander 3XL",
        "model_name": "Commander 3XL",
        "variant_code": "commander-3xl",
        "variant_label": "3XL",
        "url": "https://draganfly.com/commander-3-xl/",
        "family_key": "draganfly:commander-3xl",
        "family_name": "Commander 3XL",
        "family_url": "https://draganfly.com/commander-3-xl/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "hero_url": "https://draganfly.com/wp-content/uploads/2024/11/3-XL-Hero-Update-1.webp",
        "gallery": [
            "https://draganfly.com/wp-content/uploads/2024/11/3-XL-Hero-Update-1.webp",
            "https://draganfly.com/wp-content/uploads/2024/11/3-XL-Hero-Update-scaled.webp",
            "https://draganfly.com/wp-content/uploads/2024/11/3-XL-Herelink-scaled.webp",
        ],
        "payload_kg": 10.0,  # 22 lb OEM
        "length_mm": round(64 * IN_MM),
        "width_mm": round(63 * IN_MM),
        "height_mm": round(12 * IN_MM),
        "runtime_minutes": 50,
        "price_min": 23495,
        "price_max": 23495,
        "price_currency": "USD",
        "purpose": (
            "Multi-payload commercial aerial delivery and ISR\n"
            "Survey, inspection, and public-safety lift missions"
        ),
        "description": (
            "Draganfly Commander 3XL is a modular multirotor platform marketed as the "
            "\"Swiss Army knife\" of drones: ~22 lb / 10 kg payload, retractable landing "
            "gear for 360° sensor FOV, quick-detach arms, and Blue UAS–certified Cube "
            "autopilot. Designed and manufactured in North America."
        ),
        "features": (
            "OEM draganfly.com/commander-3-xl: payload 22 lb / 10 kg; flight time 50 min; "
            "dimensions 64×63×12 in "
            f"({round(64*IN_MM)}×{round(63*IN_MM)}×{round(12*IN_MM)} mm); starting "
            "price $23,495 USD. Blue UAS / USA-made Cube triple IMU; retractable landing "
            "gear; quick-detach modular arms; radio options Microhard PDDL, Herelink Blue, "
            "Doodle Labs Helix, DTC BluSDR; delivery box (~7 kg), Gremsy VIO, drop-down "
            "winch payload options. Soft: empty weight not on PDP."
        ),
        "use_keys": "delivery|inspection|surveillance|monitoring|search-and-rescue",
        "industry_keys": "security|defence|government|agriculture|logistics",
        "category_slugs": "aerial|drone",
        "movement_keys": "aerial|flying",
        "tags": [
            "Draganfly", "Commander", "UAV", "Drone", "Blue UAS", "Heavy Lift", "USA"
        ],
        "sources": [
            {
                "url": "https://draganfly.com/commander-3-xl/",
                "type": "website",
                "title": "OEM Commander 3XL",
            },
        ],
    },
    {
        "id": 3616,
        "name": "Draganfly Heavy Lift Drone",
        "model_name": "Heavy Lift",
        "variant_code": "heavy-lift",
        "variant_label": "Heavy Lift",
        "url": "https://draganfly.com/products/heavy-lift/",
        "family_key": "draganfly:heavy-lift",
        "family_name": "Heavy Lift",
        "family_url": "https://draganfly.com/products/heavy-lift/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "hero_url": "https://draganfly.com/wp-content/uploads/2024/10/8013a2776c094fdb00696dbee0b2b0e9.webp",
        "gallery": [
            "https://draganfly.com/wp-content/uploads/2024/10/8013a2776c094fdb00696dbee0b2b0e9.webp",
            "https://draganfly.com/wp-content/uploads/2024/10/Drone-Cube-1.webp",
            "https://draganfly.com/wp-content/uploads/2024/10/bf0c2daa4097d8502fe0b2c04572b0ce.jfif_.webp",
        ],
        "payload_kg": 30.0,  # 66 lb OEM hero figure
        "length_mm": round(125 * IN_MM),
        "width_mm": round(125 * IN_MM),
        "height_mm": round(30 * IN_MM),
        "runtime_minutes": 55,
        "price_min": 55495,
        "price_max": 55495,
        "price_currency": "USD",
        "purpose": (
            "Heavy cargo aerial delivery and logistics\n"
            "Large-sensor ISR and industrial lift"
        ),
        "description": (
            "Draganfly Heavy Lift is a Blue UAS–certified industrial multirotor with a "
            "~66 lb / 30 kg universal payload mount, configurable 4/6/8 battery packs, "
            "and Cube H7 triple-IMU autopilot for logistics and large-sensor missions. "
            "Designed and manufactured in North America."
        ),
        "features": (
            "OEM draganfly.com/products/heavy-lift: payload 66 lb / 30 kg (comparison "
            "table also lists 60 lb); flight time 55 min; dimensions 125×125×30 in "
            f"({round(125*IN_MM)}×{round(125*IN_MM)}×{round(30*IN_MM)} mm); starting "
            "price $55,495 USD. Intelligent BMS with 4/6/8 battery configs; universal "
            "mount clamps payloads up to 66 lb with XT30 payload power; Blue UAS Cube "
            "H7; radio options Microhard/Herelink/Doodle Labs/DTC; modular parcel box "
            "up to 15×17×34 in. Soft: empty weight not on PDP."
        ),
        "use_keys": "delivery|heavy-load-transportation|logistics|surveillance",
        "industry_keys": "logistics|defence|government|security",
        "category_slugs": "aerial|drone",
        "movement_keys": "aerial|flying",
        "tags": [
            "Draganfly", "Heavy Lift", "UAV", "Drone", "Blue UAS", "Cargo", "USA"
        ],
        "sources": [
            {
                "url": "https://draganfly.com/products/heavy-lift/",
                "type": "website",
                "title": "OEM Heavy Lift",
            },
        ],
    },
    {
        "id": 2819,
        "name": "Draganflyer Tango2",
        "model_name": "Tango2",
        "variant_code": "tango2",
        "variant_label": "Tango2",
        "url": "https://draganfly.com/tango-2/",
        "family_key": "draganfly:tango2",
        "family_name": "Tango2",
        "family_url": "https://draganfly.com/legacy-products/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "hero_url": "https://draganfly.com/wp-content/uploads/2022/07/Tango-proto2.webp",
        "gallery": [
            "https://draganfly.com/wp-content/uploads/2022/07/Tango-proto2.webp",
            "https://draganfly.com/wp-content/uploads/2022/07/tango-2-flying.webp",
            "https://draganfly.com/wp-content/uploads/2022/07/Tango-Fly-4.webp",
        ],
        "payload_kg": 1.5,
        "weight_kg": 3.5,
        "length_mm": 1055,
        "width_mm": 2000,
        "height_mm": 310,
        "runtime_minutes": 120,  # 2 h standard packs
        "speed": round(12 * 3.6, 2),  # 12 m/s → km/h
        "purpose": (
            "Fixed-wing aerial mapping and agricultural monitoring\n"
            "Survey, environmental sensing, and search-and-rescue"
        ),
        "description": (
            "Draganflyer Tango2 is a legacy high-endurance fixed-wing sUAS with dual "
            "battery power management, catapult launch, and interchangeable EO/thermal/"
            "multispectral/LiDAR payloads. Listed under Draganfly Legacy Products — no "
            "longer in active production."
        ),
        "features": (
            "OEM Tango2 PDF + draganfly.com/tango-2 (legacy): aircraft without payload "
            "3.5 kg; payload capacity 1.5 kg; payload bay 335×125×160 mm; MTOW 5 kg; "
            "cruise 12 m/s (~43.2 km/h); dimensions W 2000 / L 1055 / H 310 mm; "
            "endurance 2 h standard packs / 4 h additional / 14+ h with solar; GS range "
            "5 km; dual 99 Wh Li-ion + optional wing solar; active nacelle pusher. Soft: "
            "MSRP not public; Discontinued per legacy-products page."
        ),
        "use_keys": "inspection|monitoring|research|agriculture|search-and-rescue|scanning",
        "industry_keys": "agriculture|research|security|government",
        "category_slugs": "aerial|drone",
        "movement_keys": "aerial|flying",
        "tags": [
            "Draganfly", "Tango2", "UAV", "Fixed Wing", "Legacy", "Mapping", "USA"
        ],
        "sources": [
            {"url": "https://draganfly.com/tango-2/", "type": "website", "title": "OEM Tango2"},
            {
                "url": "https://draganfly.com/wp-content/uploads/2022/07/Draganfly-Tango2-PDF.pdf",
                "type": "datasheet",
                "title": "Tango2 specifications PDF",
            },
            {
                "url": "https://draganfly.com/legacy-products/",
                "type": "website",
                "title": "Legacy products (discontinued)",
            },
        ],
    },
]


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    def idx(path: str) -> dict[str, int]:
        rows = client._get(path)
        if isinstance(rows, dict):
            rows = rows.get("results") or []
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
                "source_hash": f"draganfly-en-{rid}-20260720-{loc}",
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
    for attempt in range(4):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return f"ok {resp.text[:120]}"
            if resp.status_code not in (500, 502, 503, 504):
                return f"fail {resp.status_code} {resp.text[:120]}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2 + attempt)
    return f"fail after retries {last if 'last' in dir() else ''}"


def patch_company(client: ResearchApiClient) -> None:
    body = {"website": COMPANY_WEBSITE, "country_id": US_ID}
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
            print(p["id"], p["name"], p["family_key"], p["availability_status"], p["url"])
        return 0

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / "draganfly"
    staging.mkdir(parents=True, exist_ok=True)
    patch_company(client)

    for spec in PRODUCTS:
        notes = (
            f"[AI Research] Draganfly enrich 2026-07-20: US; family {spec['family_key']}; "
            f"avail={spec['availability_status']}; OEM soft fills."
        )
        info_urls = [s["url"] for s in spec["sources"]]
        hero = spec.get("hero_url") or ""
        gallery = spec.get("gallery") or ([hero] if hero else [])
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
            "image": hero,
            "images": gallery,
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
            "payload_kg": spec.get("payload_kg"),
            "weight_kg": spec.get("weight_kg"),
            "length_mm": spec.get("length_mm"),
            "width_mm": spec.get("width_mm"),
            "height_mm": spec.get("height_mm"),
            "runtime_minutes": spec.get("runtime_minutes"),
            "speed": spec.get("speed"),
            "price_min": spec.get("price_min"),
            "price_max": spec.get("price_max"),
            "price_currency": spec.get("price_currency"),
        }
        path = staging / f"{spec['variant_code']}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            "import",
            spec["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=bool(hero),
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
            "length_mm",
            "width_mm",
            "height_mm",
            "runtime_minutes",
            "speed",
            "price_min",
            "price_max",
            "price_currency",
        ):
            if spec.get(k) is not None:
                body[k] = spec[k]
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patch OK", spec["id"])
        except Exception as e:
            print("patch FAIL", spec["id"], e)
            slim = {
                k: body[k]
                for k in body
                if k not in ("tags", "uses", "industries", "movement_types")
            }
            try:
                client._patch(f"robots/robots/{spec['id']}/", slim)
                print("slim patch OK", spec["id"])
            except Exception as e2:
                print("slim FAIL", spec["id"], e2)
        force_en(client, spec["id"], row)
        if args.copy_media and hero:
            print("  copy-media", copy_media(spec["id"]))

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
