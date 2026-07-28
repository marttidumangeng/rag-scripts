"""Curated Dusty Robotics (1510) soft enrich — FieldPrinter 2.

OEM: dustyrobotics.com (dustrobotics.com is a parked Porkbun domain — do not use).
US manufacturer country=20. Leave pending_review.

ENRICH:
  FieldPrinter 2 (5107) — Available; BIM-to-slab layout robot; OEM weight 23 lb

Usage:
  python discover_dusty_robots.py
  python discover_dusty_robots.py --apply --copy-media
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

COMPANY_ID = 1510
COMPANY_SLUG = "dusty-robotics"
COMPANY_NAME = "Dusty Robotics"
COMPANY_WEBSITE = "https://www.dustyrobotics.com/"
US_ID = 20
AVAILABLE = 11
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 5107,
        "name": "FieldPrinter 2",
        "model_name": "FieldPrinter 2",
        "variant_code": "fieldprinter-2",
        "variant_label": "2",
        "url": "https://www.dustyrobotics.com/fieldprint-platform",
        "family_key": "dusty:fieldprinter",
        "family_name": "FieldPrinter",
        "family_url": "https://www.dustyrobotics.com/fieldprint-platform",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "weight_kg": 10.4,  # 23 lb incl. battery (OEM PR 2024-01)
        "hero_url": (
            "https://cdn.prod.website-files.com/64d2bbdae796ca9291a4c909/"
            "6973d0d9e823934c767074c3_FieldPrinter-2-Full-Multi-Trade-Layout-Top-Down.webp"
        ),
        "purpose": (
            "BIM/CAD multi-trade floor layout printing on slabs\n"
            "Construction layout for walls, MEP, embeds, and finishes"
        ),
        "description": (
            "FieldPrinter 2 is Dusty Robotics' second-generation autonomous layout "
            "robot that prints coordinated BIM/CAD models onto concrete slabs at "
            "1/16 in accuracy for multi-trade construction layout."
        ),
        "features": (
            "OEM dustyrobotics.com FieldPrint Platform + Jan 2024 PR: FieldPrinter 2 "
            "at 23 lb (~10.4 kg) including battery; 1/16 in (~1.6 mm) layout accuracy; "
            "up to 600 DPI / extra-wide 1 in printhead (PR also cites 300 dpi); Edge "
            "Print + Shadow Print; curve printing; obstacle/edge sensing; hot-swappable "
            "batteries with Power Hold; iPad operator UI; Dusty Portal cloud; native "
            "Revit/AutoCAD plugins. Soft: footprint dims / runtime / speed not on "
            "public OEM pages; MSRP not public."
        ),
        "use_keys": "construction|mapping|inspection",
        "industry_keys": "construction|real-estate",
        "category_slugs": "mobile-robots|service-robots",
        "movement_keys": "wheeled",
        "tags": [
            "Dusty",
            "FieldPrinter",
            "Construction",
            "BIM",
            "Layout",
            "AMR",
            "USA",
        ],
        "sources": [
            {
                "url": "https://www.dustyrobotics.com/fieldprint-platform",
                "type": "website",
                "title": "FieldPrint Platform",
            },
            {
                "url": "https://www.dustyrobotics.com/discover/construction-robot",
                "type": "website",
                "title": "Construction robot overview",
            },
            {
                "url": (
                    "https://www.prnewswire.com/news-releases/"
                    "dusty-robotics-unveils-second-generation-robot-and-comprehensive-"
                    "bim-to-field-automated-workflow-302041417.html"
                ),
                "type": "press",
                "title": "FieldPrinter 2 launch PR (23 lb)",
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
                "source_hash": f"dusty-en-{rid}-20260720-{loc}",
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
            "[AI Research] 2026-07-20 overnight: website → dustyrobotics.com "
            "(not dustrobotics.com parked domain); country US."
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
            print(p["id"], p["name"], p["family_key"], p["url"])
        return 0

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    patch_company(client)

    for spec in PRODUCTS:
        notes = (
            f"[AI Research] Dusty enrich 2026-07-20: US; family {spec['family_key']}; "
            f"Available; OEM dustyrobotics.com + FieldPrinter 2 PR (23 lb)."
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
            "weight_kg": spec["weight_kg"],
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": info_urls,
        }
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
            "availability_status": AVAILABLE,
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
            "weight_kg": spec["weight_kg"],
        }
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
