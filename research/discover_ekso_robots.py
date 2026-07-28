"""Ekso Bionics (147) soft enrich — live Indego/NR/EVO + past GT/Vest.

Reject:
  436 Ekso Indego Personal → dupe of 1967 (better PDP URL)
  179 EksoNR / EksoGT (family) → phantom family shell

Enrich:
  1966 EksoNR Available
  1967 Ekso Indego Personal Available
  437 Ekso EVO Available
  2481 EksoGT Discontinued (past-products)
  1968 EksoVest Discontinued (past-products)

Usage:
  python discover_ekso_robots.py --apply
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

COMPANY_SLUG = "ekso-bionics"
COMPANY_NAME = "Ekso Bionics"
US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4

REJECTS = [
    (
        436,
        "duplicate: keep Ekso Indego Personal (1967) with OEM PDP; 436 is CJK shell + news URL",
    ),
    (
        179,
        "phantom_sku: EksoNR / EksoGT family shell — keep separate EksoNR (1966) and EksoGT (2481)",
    ),
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 1966,
        "name": "EksoNR",
        "model_name": "EksoNR",
        "variant_code": "EksoNR",
        "variant_label": "NR",
        "url": "https://eksobionics.com/eksonr/",
        "family_key": "ekso:eksonr",
        "family_name": "EksoNR",
        "family_url": "https://eksobionics.com/eksonr/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "weight_kg": 24.95,
        "purpose": (
            "Clinical neurorehabilitation gait training\n"
            "Stand-and-walk therapy for stroke, ABI, MS, and SCI"
        ),
        "description": (
            "EksoNR is Ekso Bionics' clinical robotic exoskeleton for rehabilitation "
            "centers. It helps high-acuity patients stand and walk early in recovery "
            "with GaitCoach software and clinician-controlled assistance."
        ),
        "features": (
            "OEM eksobionics.com/eksonr: rehab-setting powered exoskeleton; FDA-cleared "
            "indications include stroke, acquired brain injury, MS, and SCI; GaitCoach "
            "real-time gait feedback; clinician control of swing/stance assistance; "
            "posture support; session data capture; ~24.95 kg cited prior research. "
            "Soft: clinic-only (not personal home device)."
        ),
        "use_keys": "rehabilitation|medical-assistance|helping",
        "industry_keys": "healthcare",
        "category_slugs": "exoskeleton-robots|medical-robots",
        "movement_keys": "legged",
        "tags": [
            "Ekso",
            "EksoNR",
            "Exoskeleton",
            "Rehab",
            "Neurorehab",
            "Clinical",
            "USA",
        ],
        "sources": [
            {"url": "https://eksobionics.com/eksonr/", "type": "website", "title": "OEM EksoNR"},
            {"url": "https://eksobionics.com/", "type": "website", "title": "Ekso home"},
        ],
    },
    {
        "id": 1967,
        "name": "Ekso Indego Personal",
        "model_name": "Ekso Indego Personal",
        "variant_code": "Indego-Personal",
        "variant_label": "Personal",
        "url": "https://eksobionics.com/ekso-indego-personal/",
        "family_key": "ekso:indego",
        "family_name": "Ekso Indego",
        "family_url": "https://eksobionics.com/ekso-indego-personal/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "weight_kg": 14.0,  # ~31 lb OEM
        "purpose": (
            "Personal powered walking for spinal cord injury\n"
            "Home and community mobility (T3–L5 class)"
        ),
        "description": (
            "Ekso Indego Personal is a modular powered exoskeleton for individuals with "
            "mobility impairment (SCI levels about T3–L5) to stand and walk at home and "
            "in the community, with app-based settings and Medicare access pathways."
        ),
        "features": (
            "OEM eksobionics.com/ekso-indego-personal: modular quick-connect design; "
            "~31 lb (~14 kg) class; one-handed adjustable strapping; wireless iOS/"
            "Android app (speed/step height, session reports); pre-gait ADL support; "
            "home/community use (not sports/stairs). Soft: Therapy clinical sibling "
            "not a separate pending row this pass."
        ),
        "use_keys": "rehabilitation|helping|medical-assistance",
        "industry_keys": "healthcare|consumer",
        "category_slugs": "exoskeleton-robots|medical-robots",
        "movement_keys": "legged",
        "tags": [
            "Ekso",
            "Indego",
            "Personal",
            "Exoskeleton",
            "SCI",
            "Mobility",
            "USA",
        ],
        "sources": [
            {
                "url": "https://eksobionics.com/ekso-indego-personal/",
                "type": "website",
                "title": "OEM Indego Personal",
            },
            {"url": "https://eksobionics.com/", "type": "website", "title": "Ekso home"},
        ],
    },
    {
        "id": 437,
        "name": "Ekso EVO",
        "model_name": "Ekso EVO",
        "variant_code": "Ekso-EVO",
        "variant_label": "EVO",
        "url": "https://eksobionics.com/ekso-evo/",
        "family_key": "ekso:evo",
        "family_name": "Ekso EVO",
        "family_url": "https://eksobionics.com/ekso-evo/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "weight_kg": None,
        "payload_kg": None,  # assist force not payload_kg semantics
        "purpose": (
            "Upper-body industrial assist for chest-height and overhead work\n"
            "Reduce shoulder/back fatigue in manufacturing"
        ),
        "description": (
            "Ekso EVO is Ekso Bionics' wearable industrial exoskeleton that assists "
            "shoulder and back muscles during chest-level and overhead work to reduce "
            "fatigue and repetitive-strain risk while keeping range of motion."
        ),
        "features": (
            "OEM eksobionics.com/ekso-evo: wearable upper-body assist; chest-level and "
            "overhead tasks; about 5–15 lb assist per arm cited in prior OEM copy; "
            "flexible ergonomic design; successor to EksoVest industrial line. Soft: "
            "curb weight not typed this pass; assist force left out of payload_kg."
        ),
        "use_keys": "helping|material-handling",
        "industry_keys": "manufacturing|logistics",
        "category_slugs": "exoskeleton-robots",
        "movement_keys": "legged",
        "tags": [
            "Ekso",
            "EVO",
            "Exoskeleton",
            "Industrial",
            "Overhead",
            "Ergonomics",
            "USA",
        ],
        "sources": [
            {"url": "https://eksobionics.com/ekso-evo/", "type": "website", "title": "OEM Ekso EVO"},
            {
                "url": "https://eksobionics.com/ekso-evo-documents",
                "type": "website",
                "title": "EVO documents",
            },
            {"url": "https://eksobionics.com/", "type": "website", "title": "Ekso home"},
        ],
    },
    {
        "id": 2481,
        "name": "EksoGT",
        "model_name": "EksoGT",
        "variant_code": "EksoGT",
        "variant_label": "GT",
        "url": "https://eksobionics.com/past-products/",
        "family_key": "ekso:eksogt",
        "family_name": "EksoGT",
        "family_url": "https://eksobionics.com/past-products/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "weight_kg": None,
        "purpose": (
            "Clinical gait rehabilitation exoskeleton\n"
            "First-generation Ekso rehab platform (superseded by EksoNR)"
        ),
        "description": (
            "EksoGT was Ekso Bionics' first-generation clinical rehabilitation "
            "exoskeleton for gait training. It is listed among past products and "
            "superseded by EksoNR."
        ),
        "features": (
            "OEM past-products: first-generation clinical rehab exoskeleton; gait "
            "training predecessor to EksoNR; adjustable assistance / therapist control "
            "in clinical settings. Soft: Discontinued; prior DB copy wrongly framed as "
            "factory industrial — corrected to rehab lineage."
        ),
        "use_keys": "rehabilitation|medical-assistance|helping",
        "industry_keys": "healthcare",
        "category_slugs": "exoskeleton-robots|medical-robots",
        "movement_keys": "legged",
        "tags": [
            "Ekso",
            "EksoGT",
            "Exoskeleton",
            "Rehab",
            "Discontinued",
            "USA",
        ],
        "sources": [
            {
                "url": "https://eksobionics.com/past-products/",
                "type": "website",
                "title": "OEM past products",
            },
            {"url": "https://eksobionics.com/eksonr/", "type": "website", "title": "Successor EksoNR"},
        ],
    },
    {
        "id": 1968,
        "name": "EksoVest",
        "model_name": "EksoVest",
        "variant_code": "EksoVest",
        "variant_label": "Vest",
        "url": "https://eksobionics.com/past-products/",
        "family_key": "ekso:eksovest",
        "family_name": "EksoVest",
        "family_url": "https://eksobionics.com/past-products/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "weight_kg": None,
        "purpose": (
            "Upper-body industrial arm/shoulder support\n"
            "Spring-powered overhead work assist (superseded by Ekso EVO)"
        ),
        "description": (
            "EksoVest was Ekso Bionics' spring-powered upper-body industrial "
            "exoskeleton for reducing arm and shoulder strain during overhead and "
            "chest-height work. Listed as a past product; succeeded by Ekso EVO."
        ),
        "features": (
            "OEM past-products / prior specs: industrial upper-body exoskeleton; "
            "supports arms and shoulders; spring-powered (no batteries/charging); "
            "overhead/chest-height tasks. Soft: Discontinued; soft shared hero with "
            "EksoGT possible."
        ),
        "use_keys": "helping|material-handling",
        "industry_keys": "manufacturing",
        "category_slugs": "exoskeleton-robots",
        "movement_keys": "legged",
        "tags": [
            "Ekso",
            "EksoVest",
            "Exoskeleton",
            "Industrial",
            "Discontinued",
            "USA",
        ],
        "sources": [
            {
                "url": "https://eksobionics.com/past-products/",
                "type": "website",
                "title": "OEM past products",
            },
            {"url": "https://eksobionics.com/ekso-evo/", "type": "website", "title": "Successor EVO"},
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
                "source_hash": f"ekso-en-{rid}-20260720-{loc}",
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


def reject_dupes(client: ResearchApiClient) -> None:
    for rid, reason in REJECTS:
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "status": "rejected",
                    "rejection_reason": reason[:500],
                    "notes": f"[AI Research] Rejected 2026-07-20: {reason}",
                },
            )
            print("rejected", rid)
        except Exception as e:
            print("reject FAIL", rid, e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    if args.apply:
        reject_dupes(client)

    for spec in PRODUCTS:
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        notes = (
            f"[AI Research] Ekso enrich 2026-07-20: US; family {spec['family_key']}; "
            f"avail={spec['availability_status']}; soft fields filled when known."
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
        if spec.get("weight_kg") is not None:
            row["weight_kg"] = spec["weight_kg"]
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
            "availability_status": spec["availability_status"],
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "name": spec["name"],
            "url": spec["url"],
            "information_source_urls": info_urls,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "notes": notes,
            "tags": spec["tags"],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
        }
        if spec.get("weight_kg") is not None:
            body["weight_kg"] = spec["weight_kg"]
        client._patch(f"robots/robots/{spec['id']}/", body)
        force_en(client, spec["id"], row)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
