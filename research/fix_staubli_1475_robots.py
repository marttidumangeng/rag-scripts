"""Curate Stäubli Robotics (company 1475) pending_review fleet.

Dedupes triple/duplicate TS2+TX2 imports, enriches keepers from official
Product-range / TS2 / TX2 leaflets + hygienic-humid + PF3 PDPs, marks TP80
Discontinued (Food Flash: TS2 replaces FAST picker), and holds all heroes:
Stäubli imprint forbids website image republication without written authorization
(same rights pattern as MiR / Yamaha). Leaves status=pending_review.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env
from tag_suggest import TagCatalog

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 1475
COMPANY_SLUG = "staubli-robotics"
COMPANY_NAME = "Stäubli Robotics"
COMPANY_WEBSITE = "https://www.staubli.com/global/en/robotics.html"
SWITZERLAND = 17
AVAILABLE = 11
DISCONTINUED = 4
REPORT = _HERE / "staging" / "reports" / "staubli-1475-curated-report.json"

PDF_RANGE = (
    "https://www.staubli.com/content/dam/robotics/products/Product-range-EN.pdf"
)
PDF_TX2 = (
    "https://www.staubli.com/content/dam/robotics/products/robots/tx2/"
    "TX2-robot-range-product-leaflet-EN.pdf"
)
PDF_TS2 = (
    "https://www.staubli.com/content/dam/robotics/products/robots/ts2/"
    "TS2-range-robot-product-leaflet-EN.pdf"
)
PDF_FOOD = (
    "https://www.staubli.com/content/dam/robotics/industries/food/Food-Flash-EN.pdf"
)
HUB_INDUSTRIAL = (
    "https://www.staubli.com/global/en/robotics/products/industrial-robots.html"
)
HUB_SCARA = (
    "https://www.staubli.com/global/en/robotics/products/industrial-robots/scara.html"
)
HUB_6AXIS = (
    "https://www.staubli.com/global/en/robotics/products/industrial-robots/6-axis.html"
)
HUB_HE = (
    "https://www.staubli.com/global/en/robotics/products/industrial-robots/"
    "hygienic-humid.html"
)
URL_PF3 = (
    "https://www.staubli.com/global/en/robotics/products/mobile-robotics/"
    "mobile-robot-platform/PF3.html"
)
IMPRINT = "https://www.staubli.com/global/en/imprint.html"

IMAGE_TODO = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "Exact official product imagery exists on staubli.com PDPs and leaflets, but "
    "the Stäubli imprint states website materials (including images/photographs) "
    "may not be copied, reproduced, published, downloaded, distributed, or "
    "transmitted without prior written authorization. Public accessibility is "
    "not a commercial republication license.\n"
    f"Citation: {IMPRINT}\n"
    "ACTION FOR TEAM: obtain written permission from Stäubli (robot.mkg@staubli.com) "
    "or source an independently licensed exact-model image.\n"
    "Do NOT substitute a sibling render, a family banner, or design/spec sheet.\n"
    "---"
)

# Taxonomy: reuse IDs already present on this company's exemplars.
USES_SCARA = [21, 46, 30, 37, 25, 48, 47, 49, 31, 11]
USES_TX2 = [21, 25, 22, 19]
USES_MEDX = [22, 19, 23, 6]
USES_TP80 = [21, 22]
USES_PF3 = [4]
INDUSTRIES_MFG = [12]
INDUSTRIES_TX2 = [18, 12]
INDUSTRIES_MEDX = [18, 8]
INDUSTRIES_MOBILE = [11, 12]
MOV_STATIONARY = [10]
MOV_WHEELED = [4]

TAGS_TS2 = [
    "SCARA",
    "4-axis",
    "Industrial",
    "Industrial Arm",
    "Factory Automation",
    "Manufacturing",
    "Automation",
    "Pick-and-Place",
]
TAGS_TX2 = [
    "6-Axis",
    "Industrial",
    "Industrial Arm",
    "Factory Automation",
    "Manufacturing",
    "Automation",
    "Collaborative",
    "Cobot",
]
TAGS_HE = [
    "6-Axis",
    "Industrial",
    "Industrial Arm",
    "Food Handling",
    "Cleanroom",
    "Factory Automation",
    "Manufacturing",
    "Automation",
]
TAGS_MEDX = [
    "6-Axis",
    "Industrial",
    "Industrial Arm",
    "Medical",
    "Cleanroom",
    "Precision",
    "Factory Automation",
    "Automation",
]
TAGS_TP80 = [
    "SCARA",
    "4-axis",
    "Industrial",
    "Industrial Arm",
    "Pick-and-Place",
    "Food Handling",
    "Factory Automation",
    "Manufacturing",
]
TAGS_PF3 = [
    "AMR",
    "AGV",
    "Mobile Robot",
    "Material Handling",
    "Intralogistics",
    "Pallet Handling",
    "Warehouse Automation",
    "Industrial",
]


def _p(
    *,
    name: str,
    model: str,
    url: str,
    family_key: str,
    family_name: str,
    family_url: str,
    description: str,
    features: str,
    purpose: str,
    typed: dict[str, Any],
    tags: list[str],
    sources: list[str],
    categories: list[str],
    uses: list[int],
    industries: list[int],
    movement: list[int],
    availability: int = AVAILABLE,
    product_url_scope: str = "exact_variant",
    variant_label: str = "",
    extra_notes: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "model_name": model,
        "variant_code": model,
        "variant_label": variant_label or model,
        "url": url,
        "family_key": family_key,
        "family_name": family_name,
        "family_url": family_url,
        "product_url_scope": product_url_scope,
        "description": description,
        "features": features,
        "purpose": purpose,
        "typed": typed,
        "tags": tags,
        "sources": sources,
        "categories": categories,
        "uses": uses,
        "industries": industries,
        "movement_types": movement,
        "availability_status": availability,
        "extra_notes": extra_notes,
    }


def _ts2(model: str, payload_kg: float, reach_mm: float, rep: float, weight: float, ppm: int) -> dict[str, Any]:
    url = (
        "https://www.staubli.com/global/en/robotics/products/industrial-robots/"
        f"scara/{model.lower()}.html"
    )
    return _p(
        name=model,
        model=model,
        url=url,
        family_key=f"{COMPANY_SLUG}:ts2",
        family_name="TS2",
        family_url=HUB_SCARA,
        description=(
            f"{model} is Stäubli's modular 4-axis SCARA robot with encapsulated "
            "JCS drive technology, ultra-short cycle times, and CS9 controller "
            "compatibility shared with the TX2 6-axis line."
        ),
        features=(
            f"{payload_kg:g} kg load capacity; {reach_mm:g} mm reach (axis 1–4); "
            f"±{rep:g} mm X-Y repeatability (ISO 9283); {weight:g} kg arm mass; "
            f"up to {ppm} cycles/min (25-300-25 mm / 2 kg); 200 or 400 mm stroke option; "
            "protection up to IP65; floor/ceiling mounting; CS9 SE or LP controller; "
            "optional SIL3-PLe safety functions."
        ),
        purpose=(
            "High-speed pick-and-place\n"
            "Assembly and packaging\n"
            "Machine tending"
        ),
        typed={
            "payload_kg": payload_kg,
            "reach_mm": reach_mm,
            "repeatability_mm": rep,
            "weight_kg": weight,
            "dof": 4,
        },
        tags=TAGS_TS2,
        sources=[url, PDF_TS2, PDF_RANGE],
        categories=["Scara-Robot"],
        uses=USES_SCARA,
        industries=INDUSTRIES_MFG,
        movement=MOV_STATIONARY,
    )


def _tx2(
    model: str,
    payload_kg: float,
    reach_mm: float,
    rep: float,
    weight: float,
    *,
    url_slug: str | None = None,
) -> dict[str, Any]:
    slug = url_slug or model.lower()
    url = (
        "https://www.staubli.com/global/en/robotics/products/industrial-robots/"
        f"6-axis/{slug}.html"
    )
    return _p(
        name=model,
        model=model,
        url=url,
        family_key=f"{COMPANY_SLUG}:tx2",
        family_name="TX2",
        family_url=HUB_6AXIS,
        description=(
            f"{model} is a Stäubli TX2 6-axis industrial robot with a hygienic "
            "encapsulated arm, hollow-shaft gearboxes, and modular SIL3-PLe "
            "safety options on the CS9 controller for collaborative-capable cells."
        ),
        features=(
            f"{payload_kg:g} kg load capacity; {reach_mm:g} mm reach at wrist; "
            f"±{rep:g} mm repeatability (ISO 9283); {weight:g} kg arm mass; "
            "IP65 arm (IP67 with pressurization kit); NSF H1 food-oil option; "
            "CS9 controller family; optional modular SIL3-PLe safety functions."
        ),
        purpose=(
            "Machine tending\n"
            "Assembly and handling\n"
            "Packaging and process automation"
        ),
        typed={
            "payload_kg": payload_kg,
            "reach_mm": reach_mm,
            "repeatability_mm": rep,
            "weight_kg": weight,
            "dof": 6,
        },
        tags=TAGS_TX2,
        sources=[url, PDF_TX2, PDF_RANGE],
        categories=["Industrial-Robot"],
        uses=USES_TX2,
        industries=INDUSTRIES_TX2,
        movement=MOV_STATIONARY,
    )


def _he(
    model: str,
    payload_kg: float,
    reach_mm: float,
    rep: float,
) -> dict[str, Any]:
    return _p(
        name=model,
        model=model,
        url=HUB_HE,
        family_key=f"{COMPANY_SLUG}:tx2-he",
        family_name="TX2 HE",
        family_url=HUB_HE,
        product_url_scope="family",
        description=(
            f"{model} is the hygienic/humid-environment (HE) variant of Stäubli's "
            "TX2 6-axis line, built for wash-down, food, and harsh wet processes "
            "with an encapsulated, contamination-resistant arm design."
        ),
        features=(
            f"{payload_kg:g} kg load capacity; {reach_mm:g} mm reach at wrist; "
            f"±{rep:g} mm repeatability (ISO 9283); 6 axes; IP65 "
            "(IP67 pressurized); designed for hygienic, humid, or harsh wash-down "
            "cells; CS9 controller family."
        ),
        purpose=(
            "Food handling and wash-down automation\n"
            "Hygienic packaging\n"
            "Humid or harsh-environment machine tending"
        ),
        typed={
            "payload_kg": payload_kg,
            "reach_mm": reach_mm,
            "repeatability_mm": rep,
            "dof": 6,
        },
        tags=TAGS_HE,
        sources=[HUB_HE, PDF_RANGE, PDF_TX2],
        categories=["Industrial-Robot"],
        uses=USES_TX2,
        industries=INDUSTRIES_TX2,
        movement=MOV_STATIONARY,
        extra_notes=(
            "weight_kg not separately cited for HE coating vs standard TX2 in "
            "the hygienic-humid overview table; left blank."
        ),
    )


# ---------------------------------------------------------------------------
# Keepers — one canonical record per current (or discontinued) SKU
# Specs: Product-range-EN.pdf V17 (payload/reach/repeatability) + TS2/TX2
# leaflets (arm mass). HE loads/reach from hygienic-humid overview (= base SKU).
# ---------------------------------------------------------------------------
PRODUCTS: dict[int, dict[str, Any]] = {
    # TS2 SCARA
    4631: _ts2("TS2-40", 8.4, 460, 0.01, 38, 240),
    4632: _ts2("TS2-60", 8.4, 620, 0.01, 39, 220),
    4633: _ts2("TS2-80", 8.4, 800, 0.015, 40, 200),
    4634: _ts2("TS2-100", 8.4, 1000, 0.02, 41, 170),
    # TX2 6-axis (standard)
    4625: _tx2("TX2-40", 2, 515, 0.02, 29),
    4626: _tx2("TX2-60", 4.5, 670, 0.02, 52),
    4627: _tx2("TX2-90", 14, 1000, 0.02, 114),
    4628: _tx2("TX2-140", 40, 1510, 0.015, 250),
    4629: _tx2("TX2-160", 40, 1710, 0.02, 260),
    4630: _tx2("TX2-200", 170, 2209, 0.02, 980),
    4300: _tx2("TX2-200L", 110, 2609, 0.02, 1000, url_slug="tx2-200l"),
    # MedX
    4835: _p(
        name="TX2-60L MedX Ready",
        model="TX2-60L MedX Ready",
        url=HUB_6AXIS,
        family_key=f"{COMPANY_SLUG}:tx2-medx",
        family_name="TX2 MedX Ready",
        family_url=HUB_6AXIS,
        product_url_scope="family",
        description=(
            "TX2-60L MedX Ready is Stäubli's medical-ready long-reach TX2-60L "
            "variant for patient-care and medical-device automation aligned with "
            "ISO 13485:2016 MedX Ready offerings."
        ),
        features=(
            "3.7 kg load capacity; 920 mm reach at wrist; ±0.02 mm repeatability "
            "(ISO 9283); 53 kg arm mass; 6 axes; MedX Ready configuration for "
            "medical robotics; CS9 LP controller family."
        ),
        purpose=(
            "Medical device automation\n"
            "Orthopedic and surgical assist cells\n"
            "Precision patient-care handling"
        ),
        typed={
            "payload_kg": 3.7,
            "reach_mm": 920,
            "repeatability_mm": 0.02,
            "weight_kg": 53,
            "dof": 6,
        },
        tags=TAGS_MEDX,
        sources=[HUB_6AXIS, PDF_RANGE, PDF_TX2],
        categories=["Collaborative-Robot", "Industrial-Robot"],
        uses=USES_MEDX,
        industries=INDUSTRIES_MEDX,
        movement=MOV_STATIONARY,
        extra_notes=(
            "Typed specs inherited from TX2-60L columns in Product-range / TX2 "
            "leaflet; MedX Ready is the medical-environment option of that SKU."
        ),
    ),
    # HE hygienic/humid
    4836: _he("TX2-60L HE", 3.7, 920, 0.02),
    4837: _he("TX2-90L HE", 12, 1200, 0.02),
    4838: _he("TX2-90XL HE", 7, 1450, 0.02),
    4839: _he("TX2-160L HE", 25, 2010, 0.03),
    4840: _he("TX2-200L HE", 110, 2609, 0.02),
    # TP80 discontinued
    3286: _p(
        name="TP80 FAST Picker",
        model="TP80",
        url=HUB_INDUSTRIAL,
        family_key=f"{COMPANY_SLUG}:tp80",
        family_name="TP80 FAST Picker",
        family_url=HUB_INDUSTRIAL,
        product_url_scope="family",
        description=(
            "TP80 FAST Picker was Stäubli's high-speed 4-axis picker for small-part "
            "handling and packaging. Stäubli's Food Flash states the TS2 SCARA "
            "series replaces FAST picker kinematics for food handling/packaging."
        ),
        features=(
            "Historical 4-axis FAST picker; arm mass cited 71 kg on prior OEM "
            "datasheet imports; CS8-era controller generation; superseded in "
            "current catalog by TS2 SCARA for pick-and-place / packaging cells."
        ),
        purpose=(
            "High-speed pick-and-place (legacy)\n"
            "Packaging and sorting (legacy)"
        ),
        typed={"weight_kg": 71.0, "dof": 4},
        tags=TAGS_TP80,
        sources=[PDF_FOOD, HUB_INDUSTRIAL, PDF_RANGE],
        categories=["Scara-Robot"],
        uses=USES_TP80,
        industries=INDUSTRIES_MFG,
        movement=MOV_STATIONARY,
        availability=DISCONTINUED,
        extra_notes=(
            "Discontinued/superseded per Food Flash (TS2 replaces FAST picker). "
            "payload_kg/reach_mm left blank in this pass — only third-party "
            "reprints of historical TP80 leaflets were located; weight_kg 71 and "
            "dof 4 retained from the existing curated import."
        ),
    ),
    # PF3 mobile platform
    4841: _p(
        name="PF3",
        model="PF3",
        url=URL_PF3,
        family_key=f"{COMPANY_SLUG}:pf3",
        family_name="PF3",
        family_url=URL_PF3,
        description=(
            "PF3 is Stäubli's ultra-compact 3-ton mobile robot platform for "
            "industrial intralogistics, assembly-line material flow, and pallet "
            "transport with sub-centimeter positioning."
        ),
        features=(
            "Up to 3-ton payload; 1750 × 970 mm footprint; height 350 mm without "
            "lift unit / 400 mm with lift (+100 mm stroke); positioning precision "
            "±5 mm; human safety scanner; 5 emergency stops; LED status strip; "
            "collision avoidance; up to 7,000 recharge cycles; fast charge up to 80 A."
        ),
        purpose=(
            "Heavy-load intralogistics\n"
            "Pallet transport\n"
            "Assembly-line material flow"
        ),
        typed={
            "payload_kg": 3000,
            "length_mm": 1750,
            "width_mm": 970,
            "height_mm": 350,
        },
        tags=TAGS_PF3,
        sources=[URL_PF3],
        categories=["Mobile-Robots"],
        uses=USES_PF3,
        industries=INDUSTRIES_MOBILE,
        movement=MOV_WHEELED,
        extra_notes=(
            "height_mm uses the without-lift-unit figure (350 mm); with lift unit "
            "OEM cites 400 mm."
        ),
    ),
}

REJECTS: dict[int, str] = {
    # TS2 duplicates
    3285: "duplicate: Stäubli TS2-40 duplicates keeper TS2-40 4631",
    4409: "duplicate: TS2-40 SCARA Robot duplicates keeper TS2-40 4631",
    4292: "duplicate: Stäubli TS2-60 duplicates keeper TS2-60 4632",
    4410: "duplicate: TS2-60 SCARA Robot duplicates keeper TS2-60 4632",
    4293: "duplicate: Stäubli TS2-80 duplicates keeper TS2-80 4633",
    4411: "duplicate: TS2-80 SCARA Robot duplicates keeper TS2-80 4633",
    4294: "duplicate: Stäubli TS2-100 duplicates keeper TS2-100 4634",
    4412: "duplicate: TS2-100 SCARA Robot duplicates keeper TS2-100 4634",
    # TX2 duplicates
    4295: "duplicate: Stäubli TX2-40 duplicates keeper TX2-40 4625",
    4413: "duplicate: TX2-40 6-Axis Robot duplicates keeper TX2-40 4625",
    4296: "duplicate: Stäubli TX2-60 duplicates keeper TX2-60 4626",
    4414: "duplicate: TX2-60 6-Axis Robot duplicates keeper TX2-60 4626",
    4297: "duplicate: Stäubli TX2-90 duplicates keeper TX2-90 4627",
    4415: "duplicate: TX2-90 6-Axis Robot duplicates keeper TX2-90 4627",
    4302: "duplicate: Stäubli TX2-140 duplicates keeper TX2-140 4628",
    4416: "duplicate: TX2-140 6-Axis Robot duplicates keeper TX2-140 4628",
    4298: "duplicate: Stäubli TX2-160 duplicates keeper TX2-160 4629",
    4417: "duplicate: TX2-160 6-Axis Robot duplicates keeper TX2-160 4629",
    4299: "duplicate: Stäubli TX2-200 duplicates keeper TX2-200 4630",
    4418: "duplicate: TX2-200 6-Axis Robot duplicates keeper TX2-200 4630",
    4303: "duplicate: Stäubli TX200 legacy name duplicates keeper TX2-200 4630",
    4304: "duplicate: Stäubli TX200L duplicates keeper TX2-200L 4300",
    # Legacy RX superseded by TX2; no current OEM PDP
    3287: (
        "superseded_legacy: RX260L superseded by TX2 line; third-party PDF only, "
        "no current staubli.com PDP"
    ),
    4305: (
        "superseded_legacy: RX160 superseded by TX2-160; robotforum leaflet only, "
        "no current staubli.com PDP"
    ),
    4306: (
        "superseded_legacy: RX160L superseded by TX2-160L; robotforum leaflet only, "
        "no current staubli.com PDP"
    ),
    4307: (
        "superseded_legacy: RX260 superseded by TX2 line; third-party PDF only, "
        "no current staubli.com PDP"
    ),
}


def resolve_tags(catalog: TagCatalog, names: list[str]) -> list[str]:
    by_name = catalog._by_name
    out: list[str] = []
    missing: list[str] = []
    for name in names:
        hit = by_name.get(name.casefold())
        if not hit:
            missing.append(name)
            continue
        out.append(str(hit["name"]))
    if missing:
        raise RuntimeError("unresolved TagCatalog name(s): " + ", ".join(missing))
    return out


def payload(rid: int, tag_map: dict[int, list[str]]) -> dict[str, Any]:
    data = PRODUCTS[rid]
    notes = (
        f"{IMAGE_TODO}\n"
        f"[AI Research — Stäubli curated enrichment 2026-07-22] "
        f"OEM sources: {', '.join(data['sources'])}."
    )
    if data.get("extra_notes"):
        notes += f" Notes: {data['extra_notes']}"
    body: dict[str, Any] = {
        "name": data["name"],
        "model_name": data["model_name"],
        "variant_code": data["variant_code"],
        "variant_label": data["variant_label"],
        "description": data["description"],
        "features": data["features"],
        "purpose": data["purpose"],
        "url": data["url"],
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": data["family_url"],
        "product_url_scope": data["product_url_scope"],
        "availability_status": data["availability_status"],
        "manufacturer_country_ref": SWITZERLAND,
        "manufacturer_countries": [SWITZERLAND],
        "uses": data["uses"],
        "industries": data["industries"],
        "movement_types": data["movement_types"],
        "tags": tag_map[rid],
        "information_source_urls": data["sources"],
        "notes": notes,
        "status": "pending_review",
        "categories": data["categories"],
        "image": None,
        "images": [],
        "s3_image": None,
    }
    body.update(data.get("typed") or {})
    return body


def scalar_payload(rid: int, tag_map: dict[int, list[str]]) -> dict[str, Any]:
    body = payload(rid, tag_map)
    for key in ("image", "images", "s3_image"):
        body.pop(key, None)
    return body


def patch_company(client: ResearchApiClient) -> dict[str, Any]:
    return client._patch(
        f"companies/{COMPANY_ID}/",
        {
            "website": COMPANY_WEBSITE,
            "country_id": SWITZERLAND,
        },
    )


def reject_invalid_rows(client: ResearchApiClient) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rid, reason in REJECTS.items():
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": reason[:500],
                "notes": f"[CURATED FULL 2026-07-22] {reason}",
            },
        )
        results.append({"id": rid, "rejection_reason": reason})
    return results


def apply_keepers(
    client: ResearchApiClient, tag_map: dict[int, list[str]]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rid in sorted(PRODUCTS):
        body = scalar_payload(rid, tag_map)
        patched = client._patch(f"robots/robots/{rid}/", body)
        results.append(
            {
                "id": rid,
                "name": body["name"],
                "family_key": body["family_key"],
                "availability_status": body["availability_status"],
                "typed": PRODUCTS[rid].get("typed") or {},
                "patch_ok": bool(patched),
            }
        )
    return results


def verify_company(client: ResearchApiClient) -> dict[str, Any]:
    robots = list(client.list_robots_for_company(COMPANY_ID))
    by_id = {int(r["id"]): r for r in robots}
    pending = [r for r in robots if r.get("status") == "pending_review"]
    rejected = [r for r in robots if r.get("status") == "rejected"]
    issues: list[str] = []
    for rid, data in PRODUCTS.items():
        robot = by_id.get(rid)
        if not robot:
            issues.append(f"missing keeper {rid}")
            continue
        if robot.get("status") != "pending_review":
            issues.append(f"{rid} status={robot.get('status')}")
        if robot.get("family_key") != data["family_key"]:
            issues.append(f"{rid} family_key mismatch")
        if not (robot.get("tags") or []):
            issues.append(f"{rid} missing tags")
        img = robot.get("s3_image") or robot.get("image")
        if img:
            issues.append(f"{rid} unexpected image present under rights hold: {img}")
        for key, expected in (data.get("typed") or {}).items():
            if not isinstance(expected, (int, float)):
                continue
            actual = robot.get(key)
            if actual is None:
                issues.append(f"{rid} missing typed {key}")
            elif abs(float(actual) - float(expected)) > 0.051:
                issues.append(f"{rid} typed {key}={actual} != {expected}")
    for rid in REJECTS:
        robot = by_id.get(rid)
        if robot and robot.get("status") != "rejected":
            issues.append(f"reject {rid} still {robot.get('status')}")
    return {
        "pending_count": len(pending),
        "rejected_count": len(rejected),
        "keeper_ids": sorted(PRODUCTS),
        "reject_ids": sorted(REJECTS),
        "issues": issues,
        "ok": not issues,
    }


def build_tag_map(client: ResearchApiClient) -> dict[int, list[str]]:
    catalog = TagCatalog.load(client=client)
    return {rid: resolve_tags(catalog, data["tags"]) for rid, data in PRODUCTS.items()}


def write_report(payload_obj: dict[str, Any]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload_obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report: {REPORT}", flush=True)


def dry_run(client: ResearchApiClient) -> None:
    tag_map = build_tag_map(client)
    expected = set(PRODUCTS) | set(REJECTS)
    live = {int(r["id"]) for r in client.list_robots_for_company(COMPANY_ID)}
    missing = sorted(expected - live)
    extra = sorted(live - expected)
    report = {
        "company_id": COMPANY_ID,
        "mode": "dry-run",
        "keepers": len(PRODUCTS),
        "rejects": len(REJECTS),
        "keeper_ids": sorted(PRODUCTS),
        "reject_ids": sorted(REJECTS),
        "approve_allowlist": [],
        "imageless_holds": sorted(PRODUCTS),
        "rights_block": IMPRINT,
        "missing_on_live": missing,
        "unexpected_live": extra,
        "sample_payload": scalar_payload(next(iter(PRODUCTS)), tag_map),
        "company_website": COMPANY_WEBSITE,
    }
    write_report(report)
    print(
        f"dry-run OK: {len(PRODUCTS)} keepers / {len(REJECTS)} rejects; "
        f"all imageless (rights). missing={missing} extra={extra}",
        flush=True,
    )


def apply(client: ResearchApiClient) -> None:
    tag_map = build_tag_map(client)
    print("patching company...", flush=True)
    company = patch_company(client)
    print("enriching keepers...", flush=True)
    keepers = apply_keepers(client, tag_map)
    print("rejecting duplicates/legacy...", flush=True)
    rejects = reject_invalid_rows(client)
    print("verifying...", flush=True)
    verified = verify_company(client)
    report = {
        "company_id": COMPANY_ID,
        "mode": "apply",
        "company_patch": {
            "website": (company or {}).get("website"),
            "country_id": (company or {}).get("country_id")
            or (company or {}).get("country"),
        },
        "keepers_applied": keepers,
        "rejects_applied": rejects,
        "verified": verified,
        "approve_allowlist": [],
        "imageless_holds": sorted(PRODUCTS),
        "rights_block": IMPRINT,
        "company_website": COMPANY_WEBSITE,
    }
    write_report(report)
    if not verified["ok"]:
        raise SystemExit(f"verify failed: {verified['issues']}")
    print(
        f"apply OK: {len(PRODUCTS)} pending keepers (all IMAGE TO-DO rights) / "
        f"{len(REJECTS)} rejected / 0 approve allowlist",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    client = ResearchApiClient()
    if args.apply:
        apply(client)
    else:
        dry_run(client)


if __name__ == "__main__":
    main()
