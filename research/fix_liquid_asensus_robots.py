"""Enrich Liquid Robotics Wave Glider (3869) + Asensus Senhance/ISU; reject CJK dupe.

Company 429 Liquid Robotics (Boeing) — robot 3869 Wave Glider
Company 328 Asensus Surgical — robots 4032 ISU, 1635 Senhance EN (keep),
  1654 Senhance CJK (reject as dupe of 1635)

OEM: https://www.liquid-robotics.com/wave-gliders/
      https://www.asensus.com/senhance , /isu
Leave status pending_review (do not publish).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

US_ID = 20
AVAILABLE = 11

WAVE_URL = "https://www.liquid-robotics.com/wave-gliders/"
SENHANCE_URL = "https://www.asensus.com/senhance"
ISU_URL = "https://www.asensus.com/isu"
SENHANCE_FACT = (
    "https://www.asensus.com/sites/default/files/2024-01/US_Senhance%20Fact%20Sheet.pdf"
)
ISU_BROCHURE = (
    "https://www.asensus.com/sites/default/files/2024-01/Asensus%20AI_Brochure.pdf"
)

CJK_REJECT_REASON = (
    "CJK duplicate of EN keeper Senhance® Surgical System (1635). "
    "Same Asensus Senhance digital laparoscopy platform; Chinese display name "
    "'Senhance 手术系统' with zh description — keep 1635, reject 1654."
)


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
    out: list[int] = []
    for k in keys.split("|"):
        kid = tax[group].get(k.strip().lower())
        if kid:
            out.append(kid)
        else:
            print(f"  warn missing {group}={k}")
    return out


PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 3869,
        "company_id": 429,
        "company_slug": "liquid-robotics",
        "company_name": "Liquid Robotics (Boeing)",
        "name": "Wave Glider",
        "model_name": "Wave Glider",
        "variant_code": "Wave-Glider",
        "variant_label": "SV3 / SV5 / SV6 family",
        "url": WAVE_URL,
        "family_key": "liquid-robotics:wave-glider",
        "family_name": "Wave Glider",
        "family_url": WAVE_URL,
        "product_url_scope": "family",
        "availability_status": AVAILABLE,
        "description": (
            "Wave Glider is Liquid Robotics' (Boeing) wave- and solar-powered "
            "uncrewed surface vehicle (USV) family — SV3, SV5, and SV6 — for "
            "long-endurance maritime sensing, communications, and mission payloads. "
            "The platform pairs a surface float with a submerged sub via umbilical, "
            "converting wave motion into forward propulsion while solar panels charge "
            "onboard batteries for sensors and radios."
        ),
        "purpose": (
            "Maritime domain awareness and persistent ocean sensing\n"
            "Meteorological and oceanographic data collection\n"
            "Defense and security maritime surveillance\n"
            "Offshore energy environmental monitoring\n"
            "At-sea communications gateway"
        ),
        "features": (
            "OEM liquid-robotics.com/wave-gliders comparison (SV3 / SV5 / SV6): "
            "max payload weight 70 kg / 215 kg / 450 kg; max energy storage "
            "6.8 kWh / 15.7 kWh / 30 kWh; max solar collection 225 W / 525 W / 900 W; "
            "float length overall 3.05 m / 5.15 m / 5.6 m. Wave-powered propulsion "
            "with solar energy harvest; configurable payload bays; satellite / cell / "
            "Wi-Fi / LOS radio options cited on OEM materials. SV5 released 2025; "
            "SV6 launched 2026 with native 48 V payload power. Soft: single typed "
            "length/payload left blank (multi-SKU family table); MSRP not public."
        ),
        "use_keys": "monitoring|inspection|research|security",
        "industry_keys": "defense|marine-science-academia|oil-gas|research",
        "category_slugs": "Marine|Surface",
        "movement_keys": "aquatic",
        "tags": [
            "Wave Glider",
            "USV",
            "Uncrewed Surface Vehicle",
            "Marine",
            "Boeing",
            "Liquid Robotics",
            "USA",
        ],
        "sources": [
            {"url": WAVE_URL, "type": "website", "title": "Wave Gliders OEM overview"},
            {
                "url": "https://www.liquid-robotics.com/",
                "type": "website",
                "title": "Liquid Robotics homepage",
            },
            {
                "url": "https://www.info.liquid-robotics.com/wave-glider-spec-sheet",
                "type": "datasheet",
                "title": "Wave Glider SV3 spec sheet gate",
            },
        ],
        # Family table — do not invent a single length/payload column.
        "typed": {},
    },
    {
        "id": 1635,
        "company_id": 328,
        "company_slug": "asensus-surgical",
        "company_name": "Asensus Surgical",
        "name": "Senhance® Surgical System",
        "model_name": "Senhance",
        "variant_code": "Senhance",
        "variant_label": "Surgical System",
        "url": SENHANCE_URL,
        "family_key": "asensus-surgical:senhance",
        "family_name": "Senhance",
        "family_url": SENHANCE_URL,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "description": (
            "The Senhance® Surgical System is Asensus Surgical's digital "
            "laparoscopy platform (now part of KARL STORZ) for robotic-assisted "
            "minimally invasive soft-tissue surgery. It combines familiar "
            "laparoscopic technique with haptic force sensing, eye-tracking camera "
            "control, seated ergonomics, and a reusable 3 mm / 5 mm instrument "
            "portfolio intended to keep per-procedure economics near traditional "
            "laparoscopy."
        ),
        "purpose": (
            "Robotic-assisted digital laparoscopic surgery\n"
            "Minimally invasive soft-tissue abdominal procedures\n"
            "Gynecologic and general surgery assistance"
        ),
        "features": (
            "OEM asensus.com/senhance + US Senhance Fact Sheet (BRO-001-00139.004): "
            "first-of-its-kind haptic sensing transmits instrument forces to the "
            "surgeon's hands; eye-tracking camera control (Tobii) for pan/zoom on "
            "the third robotic arm; seated open cockpit with clutch to pause and "
            "reposition hands; Senhance Microlaparoscopy — 3 mm instruments on a "
            "robotic platform; 3 mm and 5 mm reusable instruments (26 reusable "
            "standard instruments cited); Senhance Ultrasonic Advanced Energy; "
            "3DHD or HD fluorescence vision options; digital fulcrum to limit "
            "incision-site torque with force alerts. Soft: curb weight / DOF / "
            "list price not on public OEM fact sheet."
        ),
        "use_keys": "surgery",
        "industry_keys": "healthcare",
        "category_slugs": "medical-robots",
        "movement_keys": "stationary",
        "tags": [
            "Senhance",
            "Surgical Robot",
            "Laparoscopy",
            "Healthcare",
            "Medical Robot",
            "Asensus",
            "USA",
        ],
        "sources": [
            {"url": SENHANCE_URL, "type": "website", "title": "Senhance Surgical System"},
            {"url": SENHANCE_FACT, "type": "datasheet", "title": "US Senhance Fact Sheet"},
            {
                "url": "https://www.asensus.com/",
                "type": "website",
                "title": "Asensus Surgical",
            },
        ],
        "typed": {},
    },
    {
        "id": 4032,
        "company_id": 328,
        "company_slug": "asensus-surgical",
        "company_name": "Asensus Surgical",
        "name": "Intelligent Surgical Unit",
        "model_name": "ISU",
        "variant_code": "ISU",
        "variant_label": "Intelligent Surgical Unit™",
        "url": ISU_URL,
        "family_key": "asensus-surgical:intelligent-surgical-unit",
        "family_name": "Intelligent Surgical Unit",
        "family_url": ISU_URL,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "description": (
            "The Intelligent Surgical Unit™ (ISU™) is Asensus Surgical's digital "
            "augmentation / Augmented Intelligence engine for the Senhance® "
            "Surgical System. It is described by the OEM as the first augmented "
            "intelligence system FDA-cleared, CE-marked, and PMDA-approved for "
            "use in robotic surgery, adding real-time computer vision, machine "
            "learning, and clinical intelligence tools in the OR."
        ),
        "purpose": (
            "Intraoperative camera control for Senhance procedures\n"
            "Surgical field measurement and digital annotation\n"
            "Augmented intelligence assistance during soft-tissue surgery"
        ),
        "features": (
            "OEM asensus.com/isu + Asensus AI / ISU brochure: digital engine for "
            "Asensus Augmented Intelligence on Senhance only (order code "
            "X9007366; upgrade kit X0009201). AI Sight tools — Eye Tracking, "
            "Follow Us, Go To, Smart Zoom — for surgeon-directed camera FOV "
            "without a dedicated scope assistant. AI Precision — point-to-point "
            "and contour measurement (millimeter-accurate 2D/3D cited). AI "
            "Annotation — digital tagging for OR team communication. Software "
            "packages 2.5 (Go To, Follow Us, Smart Zoom) and 2.7 (+ Point to "
            "Point, Contour Measurement, Digital Tagging). Soft: standalone "
            "weight/dimensions/price not published on OEM ISU page."
        ),
        "use_keys": "surgery",
        "industry_keys": "healthcare",
        "category_slugs": "medical-robots",
        "movement_keys": "stationary",
        "tags": [
            "ISU",
            "Intelligent Surgical Unit",
            "Surgical Robot",
            "Augmented Intelligence",
            "Healthcare",
            "Medical Robot",
            "Asensus",
            "USA",
        ],
        "sources": [
            {"url": ISU_URL, "type": "website", "title": "Intelligent Surgical Unit"},
            {"url": ISU_BROCHURE, "type": "datasheet", "title": "Asensus AI / ISU brochure"},
            {"url": SENHANCE_URL, "type": "website", "title": "Senhance host platform"},
        ],
        "typed": {},
    },
]


def build_row(spec: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    img = existing.get("image") or existing.get("s3_image") or ""
    info_urls = [s["url"] for s in spec["sources"]]
    notes = (
        f"[AI Research] US overnight deep enrich 2026-07-20: OEM EN copy, "
        f"family={spec['family_key']}, avail=available, US country; "
        f"typed specs filled only when single-SKU cite exists."
    )
    row: dict[str, Any] = {
        "id": spec["id"],
        "name": spec["name"],
        "model_name": spec["model_name"],
        "variant_code": spec["variant_code"],
        "variant_label": spec["variant_label"],
        "company_slug": spec["company_slug"],
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
        "status": "pending_review",
    }
    row.update(spec.get("typed") or {})
    return row


def patch_soft(
    client: ResearchApiClient,
    tax: dict[str, dict[str, int]],
    spec: dict[str, Any],
    row: dict[str, Any],
) -> None:
    info_urls = row["information_source_urls"]
    body: dict[str, Any] = {
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
        "notes": row["notes"],
        "tags": spec["tags"],
        "uses": map_keys(tax, "uses", spec["use_keys"]),
        "industries": map_keys(tax, "industries", spec["industry_keys"]),
        "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
        "name": spec["name"],
        "status": "pending_review",
    }
    body.update(spec.get("typed") or {})
    try:
        client._patch(f"robots/robots/{spec['id']}/", body)
        print("patch OK", spec["id"])
    except Exception as e:
        print("patch FAIL", spec["id"], e)
        slim = {
            k: body[k]
            for k in (
                "manufacturer_countries",
                "manufacturer_country_ref",
                "availability_status",
                "description",
                "features",
                "purpose",
                "url",
                "information_source_urls",
                "family_key",
                "family_name",
                "family_url",
                "notes",
                "status",
            )
            if k in body
        }
        client._patch(f"robots/robots/{spec['id']}/", slim)
        print("patch slim OK", spec["id"])


def reject_cjk(client: ResearchApiClient) -> None:
    notes = f"[REJECTED 2026-07-20]\n{CJK_REJECT_REASON}\n---\n"
    client._patch(
        "robots/robots/1654/",
        {
            "status": "rejected",
            "rejection_reason": CJK_REJECT_REASON[:500],
            "notes": notes,
        },
    )
    after = client._get("robots/robots/1654/")
    print(
        "rejected 1654",
        after.get("status"),
        "reason_len",
        len(after.get("rejection_reason") or ""),
    )


def main() -> int:
    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging_root = _RESEARCH / "staging" / "robots"
    created_by = resolve_created_by_id(1)

    for spec in PRODUCTS:
        existing = client._get(f"robots/robots/{spec['id']}/")
        row = build_row(spec, existing)
        folder = staging_root / spec["company_slug"]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{spec['id']}-{spec['variant_code'].lower()}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path)
        result = import_staging(
            path,
            dry_run=False,
            patch=True,
            force_overwrite=True,
            replace_media=False,
            status="pending_review",
            created_by_id=created_by,
            skip_company_update=True,
        )
        print("import", spec["id"], result)
        patch_soft(client, tax, spec, row)

    reject_cjk(client)

    # Spot-check
    for rid in (3869, 1635, 4032, 1654):
        r = client._get(f"robots/robots/{rid}/")
        avail = r.get("availability_status") or {}
        print(
            "CHECK",
            rid,
            r.get("status"),
            "avail=",
            avail.get("key") if isinstance(avail, dict) else avail,
            "family=",
            r.get("family_key"),
            "feat_len=",
            len(r.get("features") or ""),
            "purpose_len=",
            len(r.get("purpose") or ""),
            "url=",
            (r.get("url") or "")[:60],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
