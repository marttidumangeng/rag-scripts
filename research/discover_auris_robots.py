"""Auris Health / J&J MedTech (383): MONARCH Platform + QUEST; reject CJK dupe.

Reject:
  1653 Monarch 平台 → CJK shell of EN keeper MONARCH Platform (1648)

Enrich pending:
  1648 MONARCH Platform — robotic-assisted bronchoscopy (RAB)
  1649 MONARCH QUEST — FDA-cleared AI navigation / imaging upgrade (Mar 2025)

OEM: https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/
Soft: no public typed mass/dims/price on OEM PDP — leave blank.

Usage:
  python discover_auris_robots.py --apply
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

COMPANY_SLUG = "auris-health"
COMPANY_NAME = "Auris Health (Johnson & Johnson)"
US_ID = 20
AVAILABLE = 11

BRONCH = (
    "https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/"
)
QUEST_PR = (
    "https://www.jnjmedtech.com/en-US/news/press-releases/"
    "johnson-johnson-medtech-announces-clearance-of-monarch-quest-for-enhanced-"
    "robotic-assisted-bronchoscopy/"
)

REJECTS = [
    (
        1653,
        "duplicate: keep EN MONARCH Platform (1648); pending 1653 is CJK Monarch 平台 shell "
        "with junk Care/Wheeled tags and homepage URL",
    ),
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 1648,
        # Keep ™ in name — plain "MONARCH Platform" 500s on prod (slug/name collision).
        "name": "MONARCH™ Platform",
        "model_name": "MONARCH",
        "variant_code": "MONARCH-Platform",
        "variant_label": "Platform",
        "url": BRONCH,
        "family_key": "auris:monarch",
        "family_name": "MONARCH",
        "family_url": BRONCH,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "purpose": (
            "Robotic-assisted peripheral lung nodule biopsy\n"
            "Bronchoscopic airway visualization and access"
        ),
        "description": (
            "The MONARCH Platform from Johnson & Johnson MedTech (Auris Health) is a "
            "flexible robotic-assisted bronchoscopy system. A telescoping scope-in-sheath "
            "design with continuous visualization helps clinicians navigate peripheral "
            "airways and biopsy suspicious lung nodules."
        ),
        "features": (
            "OEM J&J MedTech MONARCH Platform (bronchoscopy PDP): first flexible "
            "robotic-assisted bronchoscopy platform; AI-powered navigation/image "
            "processing; telescoping scope + sheath with independent articulation; "
            "access all 18 lung segments; continuous vision during procedure; "
            "ergonomic controller for sit/stand OR positioning; indicated for "
            "bronchoscopic visualization and airway access for diagnostic/therapeutic "
            "procedures (FDA 510(k) lineage K152819). Soft: typed system mass/dims/MSRP "
            "not published on OEM PDP."
        ),
        "use_keys": "surgery|medical-assistance",
        "industry_keys": "healthcare",
        "category_slugs": "healthcare",
        "movement_keys": "stationary",
        "tags": [
            "Auris",
            "J&J MedTech",
            "MONARCH",
            "Bronchoscopy",
            "RAB",
            "Lung biopsy",
            "Healthcare",
            "USA",
        ],
        "sources": [
            {"url": BRONCH, "type": "website", "title": "OEM MONARCH Platform"},
            {
                "url": "https://www.aurishealth.com/en-US/products/robotics/monarch-platform/bronchoscopy/",
                "type": "website",
                "title": "Auris Health MONARCH bronchoscopy",
            },
        ],
        "hero_url": (
            "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
            "blt0391701dfbc69dce/693c6a101c829546b6529dd9/US_SRG_RADS_389015.1.jpg"
        ),
    },
    {
        "id": 1649,
        "name": "MONARCH™ QUEST",
        "model_name": "MONARCH QUEST",
        "variant_code": "MONARCH-QUEST",
        "variant_label": "QUEST",
        "url": f"{BRONCH}#monarch-quest",
        "family_key": "auris:monarch",
        "family_name": "MONARCH",
        "family_url": BRONCH,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "purpose": (
            "AI-enhanced robotic bronchoscopy navigation\n"
            "Intraprocedural 3D imaging–guided nodule targeting"
        ),
        "description": (
            "MONARCH QUEST is Johnson & Johnson MedTech's FDA-cleared (March 2025) "
            "navigation advancement for the MONARCH Platform. It adds more powerful "
            "AI navigation algorithms and verified interfaces to GE HealthCare OEC 3D "
            "and Siemens Cios Spin imaging for tool-in-lesion confirmation workflows."
        ),
        "features": (
            "OEM J&J MedTech MONARCH QUEST (PDP + 2025-03-12 clearance PR): latest "
            "MONARCH navigation technology; AI-powered algorithms; verified OEC Open "
            "interface with GE HealthCare OEC 3D mobile CBCT; Siemens Cios Spin "
            "integration cited on PDP; fused navigation / tool-in-lesion confirmation "
            "workflow; airway mapping deeper into periphery. Soft: software/capability "
            "upgrade on MONARCH hardware — typed kinematics/MSRP not applicable on PDP."
        ),
        "use_keys": "surgery|medical-assistance",
        "industry_keys": "healthcare",
        "category_slugs": "healthcare",
        "movement_keys": "stationary",
        "tags": [
            "Auris",
            "J&J MedTech",
            "MONARCH",
            "QUEST",
            "Bronchoscopy",
            "AI navigation",
            "Healthcare",
            "USA",
        ],
        "sources": [
            {
                "url": f"{BRONCH}#monarch-quest",
                "type": "website",
                "title": "OEM MONARCH QUEST",
            },
            {"url": QUEST_PR, "type": "website", "title": "QUEST FDA clearance PR"},
            {"url": BRONCH, "type": "website", "title": "MONARCH Platform hub"},
        ],
        "hero_url": (
            "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
            "blt56332663aa4dd6f5/693c6a4931ed5e7752af6178/"
            "US_SRG_RADS_389015.1_Introducing_MONARCH%E2%84%A2_QUEST_Hero.jpg"
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
                "source_hash": f"auris-en-{rid}-20260720-{loc}",
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
            print("rejected", rid, reason[:70])
        except Exception as e:
            print("reject FAIL", rid, e)


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
        for rid, reason in REJECTS:
            print(f"  REJECT {rid} {reason[:70]}")
        return 0

    reject_dupes(client)

    for spec in PRODUCTS:
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = (
            spec.get("hero_url")
            or existing.get("image")
            or existing.get("s3_image")
            or ""
        )
        notes = (
            f"[AI Research] Auris/J&J enrich 2026-07-20: US; family {spec['family_key']}; "
            f"avail={spec['availability_status']}; OEM J&J MedTech bronchoscopy + QUEST PR; "
            "soft typed mass/dims/MSRP absent on PDP."
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
        # Clear tags first — merge onto mangled legacy names double-encodes.
        client._patch(f"robots/robots/{spec['id']}/", {"tags": []})
        client._patch(f"robots/robots/{spec['id']}/", {"tags": spec["tags"]})
        force_en(client, spec["id"], row)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
