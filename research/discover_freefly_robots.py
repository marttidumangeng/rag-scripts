"""Curated Freefly Systems (1452) soft enrich — Alta / Astro drones.

OEM: freeflysystems.com + docs.freeflysystems.com + store.freeflysystems.com
US manufacturer country=20. Leave pending_review.

CREATE: none
ENRICH pending:
  Alta X Gen2 (2875) — Available; 35 lb payload; store hero
  Alta X (5169) — Available; OEM specs; replace chart CDN with product render
  Astro Max (2876) — Available; OEM specs; replace wrong Alta-with-gimbal CDN
  Alta 8 Pro (5170) — Discontinued/EOS; docs specs; OEM flight hero

Usage:
  python discover_freefly_robots.py
  python discover_freefly_robots.py --apply --copy-media
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

COMPANY_ID = 1452
COMPANY_SLUG = "freefly-systems"
COMPANY_NAME = "Freefly Systems"
COMPANY_WEBSITE = "https://freeflysystems.com/"
US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 2875,
        "name": "Alta X Gen2",
        "model_name": "Alta X Gen2",
        "variant_code": "alta-x-gen2",
        "variant_label": "Gen2",
        "url": "https://store.freeflysystems.com/products/alta-x-gen2",
        "family_key": "freefly:alta-x",
        "family_name": "Alta X",
        "family_url": "https://freeflysystems.com/alta-x",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "payload_kg": 15.88,  # 35 lb store claim
        "weight_kg": 10.86,  # same Alta X empty class (OEM Alta X specs)
        "length_mm": 1415,  # unfolded diameter w/o props (Alta X airframe)
        "width_mm": 1415,
        "height_mm": 387,
        "hero_url": (
            "https://store.freeflysystems.com/cdn/shop/files/altaX-gen2-01-f5f5f5.png"
            "?v=1755648684"
        ),
        "purpose": (
            "Heavy-lift cinema and industrial sensor flights\n"
            "NDAA enterprise mapping, LiDAR, and inspection"
        ),
        "description": (
            "Alta X Gen2 is Freefly's current heavy-lift quadcopter: the Alta X "
            "airframe with Astro Max-class Skynode autonomy, Smart Dovetail, and up "
            "to 35 lb payload for cinema, LiDAR, and industrial sensors."
        ),
        "features": (
            "OEM Freefly store Alta X Gen2: up to 35 lb (~15.9 kg) payload on 12 mm "
            "rails; Smart Dovetail for Freefly payloads up to ~3.3 lb / 1.5 kg; custom "
            "Skynode (shared with Astro Max); Pilot Pro; AS150 smart flight packs "
            "(two per flight); skid landing gear; 12 V / 24 V regulated payload power; "
            "internal bay Ethernet. Soft: Gen2-specific empty weight / MTOW not on "
            "store page — empty/dims cited from live Alta X specs page for shared "
            "airframe class; MSRP not public."
        ),
        "use_keys": "inspection|mapping|monitoring|filming|research",
        "industry_keys": "media-entertainment|construction|energy|government|research",
        "category_slugs": "aerial|drone",
        "movement_keys": "aerial",
        "tags": ["Freefly", "Alta X", "UAV", "Heavy Lift", "NDAA", "Cinema", "USA"],
        "sources": [
            {
                "url": "https://store.freeflysystems.com/products/alta-x-gen2",
                "type": "website",
                "title": "Freefly Store Alta X Gen2",
            },
            {
                "url": "https://docs.freeflysystems.com/alta-x-gen2",
                "type": "website",
                "title": "Alta X Gen2 docs hub",
            },
            {
                "url": "https://freeflysystems.com/alta-x/specs",
                "type": "website",
                "title": "Alta X specs (shared airframe)",
            },
        ],
    },
    {
        "id": 5169,
        "name": "Alta X",
        "model_name": "Alta X",
        "variant_code": "alta-x",
        "variant_label": "Alta X",
        "url": "https://freeflysystems.com/alta-x",
        "family_key": "freefly:alta-x",
        "family_name": "Alta X",
        "family_url": "https://freeflysystems.com/alta-x",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "payload_kg": 15.06,
        "weight_kg": 10.86,
        "length_mm": 1415,
        "width_mm": 1415,
        "height_mm": 387,
        "runtime_minutes": 25,  # MōVI Carbon ~25 min (OEM features docs)
        "hero_url": (
            "https://freeflysystems.com/wp-content/themes/freefly/dist/images/"
            "alta-x/alta-x-ecosystem-render.png"
        ),
        "purpose": (
            "Heavy-lift cinema camera and industrial sensor flights\n"
            "Enterprise mapping, LiDAR, and inspection missions"
        ),
        "description": (
            "Alta X is Freefly's USA-made heavy-lift quadcopter for cinema and "
            "industrial payloads, with folding arms, ActiveBlade vibration control, "
            "and NDAA/Blue UAS positioning."
        ),
        "features": (
            "OEM freeflysystems.com/alta-x/specs: max payload 15.06 kg / 33.20 lb; "
            "typical empty 10.86 kg / 23.94 lb; MTOW 34.86 kg / 76.85 lb; unfolded "
            "diameter 1415 mm (w/o props) / 2273 mm (with props); folded 877 mm; "
            "height 387 mm (Skyview 434 mm); 4 motors; 33×9 in folding props; "
            "IP43-class; −20°C to +50°C; custom PX4; RTK-capable GNSS. Soft: "
            "flight time varies heavily with payload (OEM cites ~25 min with MōVI "
            "Carbon / ~8 min at max payload)."
        ),
        "use_keys": "inspection|mapping|monitoring|filming|research",
        "industry_keys": "media-entertainment|construction|energy|government|research",
        "category_slugs": "aerial|drone",
        "movement_keys": "aerial",
        "tags": ["Freefly", "Alta X", "UAV", "Heavy Lift", "NDAA", "Cinema", "USA"],
        "sources": [
            {
                "url": "https://freeflysystems.com/alta-x",
                "type": "website",
                "title": "Alta X product",
            },
            {
                "url": "https://freeflysystems.com/alta-x/specs",
                "type": "website",
                "title": "Alta X specs",
            },
        ],
    },
    {
        "id": 2876,
        "name": "Astro Max",
        "model_name": "Astro Max",
        "variant_code": "astro-max",
        "variant_label": "Max",
        "url": "https://freeflysystems.com/astro",
        "family_key": "freefly:astro",
        "family_name": "Astro",
        "family_url": "https://freeflysystems.com/astro",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "payload_kg": 3.0,
        "weight_kg": 3.523,
        "length_mm": 930,
        "width_mm": 930,
        "height_mm": 359,
        "runtime_minutes": 39,
        "hero_url": "https://freeflysystems.com/wp-content/uploads/2020/09/fb-astro.png",
        "purpose": (
            "Commercial mapping, inspection, and sensor data collection\n"
            "Enterprise LiDAR, RGB, thermal, and OGI flights"
        ),
        "description": (
            "Astro Max is Freefly's USA-made commercial quadcopter with Skynode "
            "autonomy, Smart Dovetail payloads (including LR1 61 MP), LTE fleet "
            "links, and up to 3 kg payload / 39 min unloaded flight."
        ),
        "features": (
            "OEM freeflysystems.com/astro/specs: max payload 3,000 g; typical empty "
            "3,523 g; MTOW 8,700 g; unfolded diameter 930 mm (w/o props) / 1407 mm "
            "(with); unfolded height 359 mm; folded 508×178 mm; flight time no "
            "payload 39 min; Freefly 7010 motors; SL8-Air batteries; IP43; −20 to "
            "50 C; Auterion PX4 / Mission Control / Suite. Soft: MSRP not public."
        ),
        "use_keys": "inspection|mapping|monitoring|surveillance|research",
        "industry_keys": "energy|construction|government|security|research",
        "category_slugs": "aerial|drone",
        "movement_keys": "aerial",
        "tags": ["Freefly", "Astro", "UAV", "Mapping", "NDAA", "Inspection", "USA"],
        "sources": [
            {
                "url": "https://freeflysystems.com/astro",
                "type": "website",
                "title": "Astro product",
            },
            {
                "url": "https://freeflysystems.com/astro/specs",
                "type": "website",
                "title": "Astro Max specs",
            },
            {
                "url": "https://docs.freeflysystems.com/astro/other-user-manuals/specs-and-interfaces/performance",
                "type": "website",
                "title": "Astro performance docs",
            },
        ],
    },
    {
        "id": 5170,
        "name": "Alta 8 Pro",
        "model_name": "Alta 8 Pro",
        "variant_code": "alta-8-pro",
        "variant_label": "8 Pro",
        "url": "https://docs.freeflysystems.com/products/products/alta-8-pro/overview/specifications",
        "family_key": "freefly:alta-8-pro",
        "family_name": "Alta 8 Pro",
        "family_url": "https://freeflysystems.com/support/alta-pro-support",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "payload_kg": 9.1,
        "weight_kg": 6.2,
        "length_mm": 1325,
        "width_mm": 1325,
        "height_mm": None,
        "hero_url": (
            "https://lh4.googleusercontent.com/LKJnBPmLHprdQGH73LLNkxK9YhfaFWJEMFzL3XBG9imU5X-Q"
            "Hc2PT2H19YMQP4rdqjPKbEob_diN7cTMpvHzZE4rwq26Uugg743b0jypWkPb2G9yuo9x4p87MJudlnakPtHZCwq1"
        ),
        "purpose": (
            "Legacy heavy-lift cinema and industrial octocopter flights\n"
            "Waypoint PX4 missions for cameras and sensors"
        ),
        "description": (
            "Alta 8 Pro is Freefly's discontinued eight-rotor cinema/industrial "
            "drone (EOS after March 2022) with PX4 waypoint autonomy and up to "
            "9.1 kg payload."
        ),
        "features": (
            "OEM Freefly docs Alta 8 Pro: MTOW 18.1 kg; max useful load 12.0 kg; "
            "max payload 9.1 kg; typical empty 6.2 kg; unfolded diameter 1325 mm "
            "(w/o props); folded 660 mm; Silent-Drive ESC; PX4. Soft: height not "
            "typed on specs table; MSRP not public; product page redirects to "
            "Alta X — docs + support EOS pages remain."
        ),
        "use_keys": "filming|inspection|mapping|research",
        "industry_keys": "media-entertainment|research",
        "category_slugs": "aerial|drone",
        "movement_keys": "aerial",
        "tags": ["Freefly", "Alta 8 Pro", "UAV", "Octocopter", "Discontinued", "USA"],
        "sources": [
            {
                "url": "https://docs.freeflysystems.com/products/products/alta-8-pro/overview/specifications",
                "type": "website",
                "title": "Alta 8 Pro specifications",
            },
            {
                "url": "https://freeflysystems.com/support/alta-pro-support",
                "type": "website",
                "title": "Alta Pro support / EOS",
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
                "source_hash": f"freefly-en-{rid}-20260720-{loc}",
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
            "[AI Research] 2026-07-20 overnight: website → freeflysystems.com; "
            "country US."
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
                p["url"],
            )
        return 0

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    patch_company(client)

    for spec in PRODUCTS:
        notes = (
            f"[AI Research] Freefly enrich 2026-07-20: US; family {spec['family_key']}; "
            f"availability={spec['availability_status']}; OEM freeflysystems.com specs."
        )
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
            "image": hero,
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
            "speed",
            "runtime_minutes",
            "length_mm",
            "width_mm",
            "height_mm",
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
                for k in list(body)
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
