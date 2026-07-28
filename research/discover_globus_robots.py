"""Globus Medical (432): enrich ExcelsiusFlex™ TKA robotic navigation.

Pending:
  4959 ExcelsiusFlex™ — FDA 510(k) Jul 2024 TKA application (K240721)

OEM: https://www.globusmedical.com/musculoskeletal-solutions/excelsiustechnology/excelsiusflex/
Soft: no public typed mass/reach/MSRP on OEM PDP — leave blank.

Usage:
  python discover_globus_robots.py --apply
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

COMPANY_SLUG = "globus-medical"
COMPANY_NAME = "Globus Medical"
US_ID = 20
AVAILABLE = 11

PDP = (
    "https://www.globusmedical.com/musculoskeletal-solutions/"
    "excelsiustechnology/excelsiusflex/"
)
HUB = (
    "https://www.globusmedical.com/musculoskeletal-solutions/excelsiustechnology/"
)
FDA_PR = (
    "https://www.globenewswire.com/news-release/2024/07/17/2914528/0/en/"
    "Globus-Medical-Receives-FDA-510-k-Clearance-for-ExcelsiusFlex-and-ACTIFY-"
    "3D-Total-Knee-System.html"
)

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4959,
        "name": "ExcelsiusFlex",
        "model_name": "ExcelsiusFlex",
        "variant_code": "ExcelsiusFlex",
        "variant_label": "TKA",
        "url": PDP,
        "family_key": "globus:excelsiusflex",
        "family_name": "ExcelsiusFlex",
        "family_url": PDP,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "purpose": (
            "Robotically guided total knee arthroplasty resections\n"
            "Imageless and CT-based TKA navigation"
        ),
        "description": (
            "ExcelsiusFlex is Globus Medical's robotic navigation platform for primary "
            "total knee arthroplasty. A compact floor-mounted base and robotic arm work "
            "with ExcelsiusHub to deliver imageless or CT-based registration, active "
            "patient tracking, and navigated sawblade guidance while keeping tactile "
            "control with the surgeon."
        ),
        "features": (
            "OEM Globus ExcelsiusFlex (PDP + FDA 510(k) Jul 2024 / K240721): TKA "
            "robotic navigation + positioning; imageless and CT-based registration; "
            "low-profile planar end effector with familiar cutting feel; active robotic "
            "arm adjustments for limb movement; ipsilateral/contralateral docking; "
            "navigated sawblade via Robot Reference Array; LED resection-plane cue; "
            "pairs with ExcelsiusHub; compatible implant systems GENflex2 and ACTIFY "
            "3D Total Knee (OEM/PR). Soft: typed system mass/reach/MSRP not on public PDP."
        ),
        "use_keys": "surgery|medical-assistance",
        "industry_keys": "healthcare",
        "category_slugs": "healthcare",
        "movement_keys": "stationary",
        "tags": [
            "Globus Medical",
            "ExcelsiusFlex",
            "Excelsius",
            "TKA",
            "Orthopedics",
            "Surgical Robot",
            "Healthcare",
            "USA",
        ],
        "sources": [
            {"url": PDP, "type": "website", "title": "OEM ExcelsiusFlex"},
            {"url": HUB, "type": "website", "title": "Excelsius Technology hub"},
            {"url": FDA_PR, "type": "website", "title": "FDA 510(k) clearance PR"},
            {
                "url": "https://www.accessdata.fda.gov/cdrh_docs/pdf24/K240721.pdf",
                "type": "datasheet",
                "title": "FDA 510(k) summary K240721",
            },
        ],
        "hero_url": (
            "https://www.globusmedical.com/wp-content/themes/globus/images/"
            "slideshows/eflex/GM5936_ExcelsiusFlex_Still005.webp"
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
                "source_hash": f"globus-en-{rid}-20260720-{loc}",
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
            print(f"  PEND {p['id']} {p['name']} fam={p['family_key']}")
        return 0

    for spec in PRODUCTS:
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = (
            spec.get("hero_url")
            or existing.get("image")
            or existing.get("s3_image")
            or ""
        )
        notes = (
            f"[AI Research] Globus enrich 2026-07-20: US; family {spec['family_key']}; "
            "Available; OEM ExcelsiusFlex + FDA K240721; soft typed mass/MSRP absent."
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
                replace_media=bool(spec.get("hero_url")),
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
        }
        if img:
            body["image"] = img
        client._patch(f"robots/robots/{spec['id']}/", body)
        client._patch(f"robots/robots/{spec['id']}/", {"tags": []})
        client._patch(f"robots/robots/{spec['id']}/", {"tags": spec["tags"]})
        force_en(client, spec["id"], row)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
