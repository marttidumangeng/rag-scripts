"""Curated full enrichment for Gurki, inVia, 6 River Systems, and Plus One.

Applies only to the explicitly targeted production records. Kept robots remain
pending_review; proven software/workflow shells are rejected with coded reasons.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

AVAILABLE = 11
COUNTRY_IDS = {"CN": 3, "US": 20}
REPORT = _RESEARCH / "staging" / "reports" / "curated-gurki-invia-sixriver-plusone.json"

GURKI_FAMILY_URL = "https://www.gurkipack.com/products/Palletizer"
INVIA_PICKER_URL = "https://inviarobotics.com/our-system/invia-picker-robots/"
CHUCK_URL = "https://ocadointelligentautomation.com/systems/chuck-amr"
CHUCK_DATASHEET = (
    "https://ocadointelligentautomation.com/hubfs/Datasheets%20Download/"
    "OIA_datasheet_2025_CHUCK-AMR.pdf?hsLang=en"
)
CHUCK_FACTSHEET = (
    "https://ocadointelligentautomation.com/hubfs/Fact%20Sheets/"
    "OIA_Chuck%20AMR_%20Fact%20Sheet.pdf?hsLang=en"
)
INVIA_CASE_STUDY = (
    "https://inviarobotics.com/wp-content/uploads/2023/06/"
    "inVia-PickerWall-Case-Study.pdf"
)
INVIA_OVERVIEW = (
    "https://inviarobotics.com/blog/"
    "product-overview-video-how-invia-robotics-raas-platform-works/"
)

USE_IDS = {
    "handling": 46,
    "intralogistics": 74,
    "inventory": 8,
    "packaging": 37,
    "palletizing": 25,
    "picking": 11,
    "sorting": 47,
    "transport": 16,
    "warehouse": 78,
}
INDUSTRY_IDS = {
    "commercial": 48,
    "fmcg": 30,
    "food-beverage": 59,
    "industrial": 50,
    "logistics": 11,
    "manufacturing": 12,
    "warehousing": 45,
}
MOVEMENT_IDS = {"fixed": 19, "mobile": 17, "stationary": 10, "wheeled": 4}

GURKI_BASE_FEATURES = (
    "Touchscreen operation; integrated robot, power, pneumatics, and lifting "
    "column; manual or automatic pallet supply; suction-cup or clamp gripper; "
    "standalone use or integration with pallet feeders and conveyors."
)
GURKI_PURPOSE = (
    "Carton and case palletizing\n"
    "Food and beverage palletizing\n"
    "Pharmaceutical and daily-chemical palletizing\n"
    "End-of-line packaging automation"
)
GURKI_TAGS = [
    "Automation",
    "Collaborative Robot",
    "Material Handling",
    "Packaging",
    "palletizing",
    "Stationary",
    "Warehouse",
]


def gurki(
    *,
    robot_id: int,
    model: str,
    url: str,
    image: str,
    expected_md5: str,
    payload_kg: float,
    weight_kg: float,
    reach_mm: float,
    rate: str,
    palletizing_height: str,
    machine_height: str,
    power: str,
    protection: str,
    compatible_size: str,
    height_mm: float | None = None,
    exact_video: str | None = None,
    extra: str = "",
) -> dict[str, Any]:
    typed: dict[str, Any] = {
        "payload_kg": payload_kg,
        "weight_kg": weight_kg,
        "reach_mm": reach_mm,
    }
    if height_mm is not None:
        typed["height_mm"] = height_mm
    video = exact_video or "https://www.youtube.com/watch?v=BfVi58p_hBI"
    video_note = (
        "Exact-model OEM video retained."
        if exact_video
        else (
            "Dead search: OEM PDP, page HTML, and exact-model YouTube search exposed "
            "no model-specific clip; retained one clearly labeled Gurki palletizer "
            "family demonstration and removed sibling-model clips."
        )
    )
    features = (
        f"{GURKI_BASE_FEATURES} OEM specifications for {model}: {rate}; "
        f"{payload_kg:g} kg load; {reach_mm:g} mm working radius; {weight_kg:g} kg "
        f"equipment weight; palletizing height {palletizing_height}; machine height "
        f"{machine_height}; {power}; {protection}; compatible product size "
        f"{compatible_size}.{(' ' + extra.strip()) if extra.strip() else ''}"
    )
    return {
        "id": robot_id,
        "company_id": 974,
        "name": model,
        "model_name": model,
        "variant_code": model,
        "variant_label": f"{payload_kg:g} kg collaborative palletizer",
        "url": url,
        "family_key": "huizhou-gurki-intelligent-equipment-co-ltd:gpm-r",
        "family_name": "GPM-R Collaborative Palletizers",
        "family_url": GURKI_FAMILY_URL,
        "product_url_scope": "exact_variant",
        "country": "CN",
        "description": (
            f"The Gurki {model} is a {payload_kg:g} kg-payload collaborative "
            "end-of-line palletizing workstation for cartons and other packaged "
            "goods. It combines a robot arm, lifting column, controls, pneumatics, "
            "and palletizing base in an integrated system."
        ),
        "purpose": GURKI_PURPOSE,
        "features": features,
        "categories": ["Warehouse-Robots"],
        "sub_category": 6,
        "uses": ["handling", "packaging", "palletizing", "warehouse"],
        "industries": ["fmcg", "food-beverage", "industrial", "manufacturing"],
        "movement": ["fixed", "stationary"],
        "tags": GURKI_TAGS,
        "sources": [url],
        "image": image,
        "expected_md5": expected_md5,
        "video_urls": [video],
        "typed": typed,
        "dead_search": video_note,
    }


ROBOTS: list[dict[str, Any]] = [
    gurki(
        robot_id=2964,
        model="GPM-R30H",
        url="https://www.gurkipack.com/product/R30H",
        image="https://www.gurkipack.com/uploads/pro89/240806041913-26996.jpg",
        expected_md5="ca5c6190a7434b2feb0fd33f0286e77f",
        payload_kg=30,
        weight_kg=560,
        reach_mm=1800,
        rate="8–10 palletizing cycles per minute",
        palletizing_height="300–2200 mm",
        machine_height="OEM table repeats 300–2200 mm; not mapped to typed height",
        power="3000 W at 220 V",
        protection="IP65",
        compatible_size="L200–1200 × W200–600 × H100–600 mm",
        exact_video="https://www.youtube.com/watch?v=bDKHRTHqM6M",
        extra="Maximum listed pallet size is L1200 × W1200 mm.",
    ),
    gurki(
        robot_id=2963,
        model="GPM-R20H",
        url="https://www.gurkipack.com/product/GPM-R20H",
        image="https://www.gurkipack.com/uploads/dir31/20H.jpg",
        expected_md5="8ee171972eb641c7f5c895996cb7dbe9",
        payload_kg=20,
        weight_kg=520,
        reach_mm=1700,
        rate="8–10 boxes per minute",
        palletizing_height="300–2200 mm",
        machine_height="2250–2800 mm",
        power="3000 W at 220 V / 50 Hz",
        protection="protection rating not published",
        compatible_size="L200–600 × W200–600 × H100–600 mm",
        extra=(
            "OEM states deployment within three hours and a footprint below 1 m²; "
            "the ambiguous '1000×1200×140 mm covered area' row was not mapped to "
            "typed dimensions."
        ),
    ),
    gurki(
        robot_id=2962,
        model="GPM-R30GD",
        url="https://www.gurkipack.com/product/gpm-r30wd",
        image="https://www.gurkipack.com/uploads/pro93/R30GD.jpg",
        expected_md5="c657921e5321af495bca17c12434040a",
        payload_kg=30,
        weight_kg=550,
        reach_mm=2000,
        rate="8–10 boxes per minute",
        palletizing_height="300–2300 mm",
        machine_height="2850 mm",
        power="2500 W at 220 V",
        protection="IP54",
        compatible_size="L200–1200 × W200–1200 × H100–600 mm",
        height_mm=2850,
        extra=(
            "2000 mm arm length; maximum pallet L1200 × W1200 × H140 mm; "
            "6 m² double-stacking area; 0–55 °C operating range; up to 800 paths."
        ),
    ),
    gurki(
        robot_id=2961,
        model="GPM-R30",
        url="https://www.gurkipack.com/product/gpm-r30",
        image="https://www.gurkipack.com/uploads/pro71/250527040428-160322.jpg",
        expected_md5="c3a0d766fb0b96daec7cf8e1fa0289eb",
        payload_kg=30,
        weight_kg=550,
        reach_mm=1800,
        rate="8–11 boxes per minute",
        palletizing_height="300–2400 mm including pallet height",
        machine_height="2580–3130 mm",
        power="3000 W at 220 V / 50 Hz",
        protection="IP54",
        compatible_size="L200–1200 × W200–1200 × H100–600 mm",
        extra=(
            "Maximum listed pallet size L1200 × W1200 × H140 mm; visual "
            "programming; ten-level collision detection and 16 safety I/O."
        ),
    ),
    gurki(
        robot_id=2960,
        model="GPM-R50H",
        url="https://www.gurkipack.com/product/r50h",
        image=(
            "https://www.gurkipack.com/uploads/dir96/"
            "maduoji-250422051651-175647.jpg"
        ),
        expected_md5="1ba729c6621c9726634d4aa32e4aa3a9",
        payload_kg=50,
        weight_kg=550,
        reach_mm=1800,
        rate="6–10 palletizing cycles per minute",
        palletizing_height="300–2200 mm",
        machine_height="2300–2840 mm",
        power="4 kW at 220 V / 50 Hz",
        protection="IP54",
        compatible_size="L200–1200 × W200–1200 × H100–600 mm",
        extra="Applicable products include cartons, film bags, woven bags, and barrels.",
    ),
    gurki(
        robot_id=2959,
        model="GPM-R35HGD",
        url="https://www.gurkipack.com/product/pro-108.html",
        image="https://www.gurkipack.com/uploads/pro108/GPM-R35HGD-1.jpg",
        expected_md5="2b22c68c96c41661c3f6ab488993d589",
        payload_kg=35,
        weight_kg=550,
        reach_mm=2000,
        rate="9–10 palletizing cycles per minute",
        palletizing_height="300–2200 mm",
        machine_height="2650 mm",
        power="4 kW at 220 V / 50 Hz",
        protection="IP54",
        compatible_size="L200–1200 × W200–1200 × H100–600 mm",
        height_mm=2650,
        extra="Applicable products include cartons, film bags, woven bags, and barrels.",
    ),
    gurki(
        robot_id=2958,
        model="GPM-R50HGD",
        url="https://www.gurkipack.com/product/pro-107.html",
        image="https://www.gurkipack.com/uploads/dir31/11.jpg",
        expected_md5="1a006404ea294df69837b5eea2f63e38",
        payload_kg=50,
        weight_kg=550,
        reach_mm=2000,
        rate="6–8 palletizing cycles per minute",
        palletizing_height="300–2200 mm",
        machine_height="2650 mm",
        power="4 kW at 220 V / 50 Hz",
        protection="IP54",
        compatible_size="L200–1200 × W200–1200 × H100–600 mm",
        height_mm=2650,
        extra="Applicable products include cartons, film bags, woven bags, and barrels.",
    ),
    gurki(
        robot_id=2957,
        model="GPM-R85HGD",
        url="https://www.gurkipack.com/product/pro-106.html",
        image=(
            "https://www.gurkipack.com/uploads/dir31/"
            "file-260401104318-25.jpg"
        ),
        expected_md5="b6598382256e889592a3e1f6c0b57796",
        payload_kg=85,
        weight_kg=650,
        reach_mm=1900,
        rate="4–6 palletizing cycles per minute",
        palletizing_height="300–2000 mm",
        machine_height="2500 mm",
        power="4.5 kW at 220 V / 50 Hz",
        protection="IP54",
        compatible_size="L200–1200 × W200–1200 × H100–600 mm",
        height_mm=2500,
        exact_video="https://www.youtube.com/watch?v=z-nOKs8qfRY",
        extra="Applicable products include cartons, film bags, woven bags, and barrels.",
    ),
    {
        "id": 2977,
        "company_id": 397,
        "name": "inVia Picker robot",
        "model_name": "inVia Picker",
        "variant_code": "Picker",
        "variant_label": "Goods-to-person AMR",
        "url": INVIA_PICKER_URL,
        "family_key": "invia-robotics:picker",
        "family_name": "inVia Picker",
        "family_url": INVIA_PICKER_URL,
        "product_url_scope": "exact_variant",
        "country": "US",
        "description": (
            "inVia Picker is a compact autonomous mobile robot that retrieves totes "
            "from existing warehouse racking with an extendable lift and suction-cup "
            "gripper, then delivers inventory to goods-to-person picking stations."
        ),
        "purpose": (
            "Autonomous tote retrieval and putaway\n"
            "Goods-to-person order fulfillment\n"
            "Warehouse replenishment and inventory movement\n"
            "Lights-out warehouse operation"
        ),
        "features": (
            "OEM specifications: 25.5 in (647.7 mm) high × 26.1 in (662.94 mm) "
            "wide; 136 lb (61.69 kg); payload up to 40 lb (18.14 kg); payload "
            "envelope 14 in H × 15 in W × 24 in L (355.6 × 381 × 609.6 mm); "
            "reach up to 8 ft (2438.4 mm); 5 mph (8.05 km/h) maximum speed; "
            "hot-swappable 10-hour battery and optional self-charging. Fiducial "
            "machine vision, built-in lighting, extendable lift, and industrial "
            "suction cups support autonomous tote handling."
        ),
        "categories": ["Warehouse-Robots", "Mobile-Robots"],
        "sub_category": 6,
        "uses": ["intralogistics", "inventory", "picking", "transport", "warehouse"],
        "industries": ["commercial", "fmcg", "logistics", "warehousing"],
        "movement": ["mobile", "wheeled"],
        "tags": [
            "AMR",
            "Autonomous",
            "Autonomous Mobile Robot",
            "Logistics",
            "Material Handling",
            "Mobile Robot",
            "Order Fulfillment",
            "Warehouse",
            "Wheeled",
        ],
        "sources": [INVIA_PICKER_URL, INVIA_OVERVIEW, INVIA_CASE_STUDY],
        # Exact Picker photo credited to inVia Robotics by IEEE Robots Guide.
        "image": (
            "https://assets.robotsguide.com/images/7p2whiua/production/"
            "a6f69a87242f47081e45bb39433d55763f8fe742-2048x1536.jpg"
            "?w=1200&auto=format"
        ),
        "expected_md5": "a6c2e0df39f0341843d75976ab65a002",
        "video_urls": ["https://www.youtube.com/watch?v=WDQ3Ftd0pvc"],
        "typed": {
            "payload_kg": 18.14,
            "weight_kg": 61.69,
            "speed": 8.04672,
            "width_mm": 662.94,
            "height_mm": 647.7,
            "runtime_minutes": 600,
            "reach_mm": 2438.4,
        },
        "dead_search": (
            "Length is not published as a robot dimension on the live OEM PDP; "
            "24 in is the payload envelope length and was not mapped to robot length. "
            "OEM PDP, official overview, and case study were checked. The previous "
            "image-menu.png wireframe was removed as a drawing; the replacement is "
            "an exact-model studio photo credited to inVia Robotics."
        ),
    },
    {
        "id": 1238,
        "company_id": 1373,
        "name": "Chuck AMR",
        "model_name": "Chuck",
        "variant_code": "Chuck",
        "variant_label": "Regular / Chuck+ shelf variants",
        "url": CHUCK_URL,
        "family_key": "6-river-systems:chuck",
        "family_name": "Chuck AMR",
        "family_url": CHUCK_URL,
        "product_url_scope": "family",
        "country": "US",
        "description": (
            "Chuck is the 6 River Systems autonomous mobile robot now offered by "
            "Ocado Intelligent Automation for person-to-goods warehouse workflows. "
            "It collaborates with associates and other Chucks through cloud "
            "orchestration to guide picking, putaway, sorting, and returns."
        ),
        "purpose": (
            "System-directed warehouse picking\n"
            "Putaway, sorting, and returns\n"
            "Order and tote transportation\n"
            "Associate guidance and route optimization"
        ),
        "features": (
            "Official 2025 specifications: 1600 mm overall height × 610 mm base "
            "width × 1067 mm base depth; 90 kg maximum payload; 57.6 kg base "
            "without battery or 69.9 kg with battery; 12.2 kg battery; up to 12 "
            "hours per charge depending on payload; 25.6 V, 42 Ah battery. Up to "
            "six configurable shelf levels; 45.4 kg per-shelf capacity; 13.6 kg "
            "top-canopy capacity; Chuck+ uses 750 × 910 mm shelves versus "
            "600 × 910 mm Chuck shelves. AI/computer-vision navigation, lidar and "
            "camera object detection, autonomous charging, touchscreen-directed "
            "workflows, and existing-Wi-Fi deployment."
        ),
        "categories": ["Mobile-Robots", "Warehouse-Robots"],
        "sub_category": 6,
        "uses": ["intralogistics", "picking", "sorting", "transport", "warehouse"],
        "industries": ["commercial", "fmcg", "logistics", "warehousing"],
        "movement": ["mobile", "wheeled"],
        "tags": [
            "AMR",
            "Autonomous",
            "Autonomous Mobile Robot",
            "Logistics",
            "Material Handling",
            "Mobile Robot",
            "Order Fulfillment",
            "Warehouse",
            "Wheeled",
        ],
        "sources": [CHUCK_URL, CHUCK_DATASHEET, CHUCK_FACTSHEET],
        "image": (
            "https://ocadointelligentautomation.com/hs-fs/hubfs/"
            "OIA%20MHE%20Assets/Chuck%20AMR%20Images%202024/13.jpg"
            "?width=2000&name=13.jpg"
        ),
        "expected_md5": "6b2a2e841ca260f46bccea2a67854314",
        "video_urls": ["https://www.youtube.com/watch?v=MorgeqVkedw"],
        "typed": {
            "payload_kg": 90,
            "weight_kg": 69.9,
            "length_mm": 1067,
            "width_mm": 610,
            "height_mm": 1600,
            "runtime_minutes": 720,
            "battery_wh": 1075.2,
        },
        "dead_search": (
            "No maximum travel speed is stated on the live OEM PDP, 2025 "
            "datasheet, or official fact sheet; speed remains blank. Regular and "
            "Chuck+ share the same base; variant-specific shelf widths remain in "
            "features rather than being misapplied to base width."
        ),
    },
]

REJECTIONS = {
    2978: (
        "non_robot_workflow: inVia PickerWall is a dynamic pick/put-wall workflow "
        "built each day by inVia Picker robots, not a robot model or physical robot "
        "SKU. OEM PDP describes the robots delivering inventory to the wall."
    ),
    3793: (
        "non_robot_software: PickOne is Plus One Robotics AI-powered 2D+3D vision "
        "software for third-party logistics robots, not a robot or hardware SKU. "
        "OEM product page explicitly identifies it as warehouse automation software."
    ),
}


def validate_source_image(spec: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(spec["image"], timeout=60)
    response.raise_for_status()
    body = response.content
    image = Image.open(io.BytesIO(body))
    image.verify()
    md5 = hashlib.md5(body).hexdigest()
    if md5 != spec["expected_md5"]:
        raise ValueError(
            f"{spec['id']} media hash changed: expected {spec['expected_md5']} got {md5}"
        )
    if len(body) < 20_000:
        raise ValueError(f"{spec['id']} media too small: {len(body)} bytes")
    return {
        "id": spec["id"],
        "url": spec["image"],
        "bytes": len(body),
        "md5": md5,
        "format": image.format,
        "size": list(image.size),
    }


def trigger_copy_media(robot_id: int) -> dict[str, Any]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    base = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace(
        "/api/v1", ""
    )
    if not secret or not base:
        raise RuntimeError("INTERNAL_API_SECRET and IMPORT_SYNC_API_BASE_URL are required")
    url = f"{base}/admin/robots/robot/content-queue/api/robot/{robot_id}/copy-media/"
    response = requests.post(
        url,
        headers={"X-Internal-Secret": secret},
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"copy-media {robot_id} returned {data}")
    return data


def verify_owned_hero(robot: dict[str, Any]) -> dict[str, Any]:
    url = robot.get("s3_image") or robot.get("image") or ""
    if "cdn.robotaigeek.com/" not in url:
        raise ValueError(f"{robot['id']} has no owned CDN hero after copy-media: {url}")
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    body = response.content
    image = Image.open(io.BytesIO(body))
    image.verify()
    if len(body) < 20_000:
        raise ValueError(f"{robot['id']} CDN image too small: {len(body)} bytes")
    return {
        "id": robot["id"],
        "url": url,
        "status": response.status_code,
        "bytes": len(body),
        "md5": hashlib.md5(body).hexdigest(),
        "format": image.format,
        "size": list(image.size),
    }


def payload(spec: dict[str, Any]) -> dict[str, Any]:
    country_id = COUNTRY_IDS[spec["country"]]
    notes = (
        "[AI Research] Curated full enrichment 2026-07-21. "
        f"Sources: {' | '.join(spec['sources'])}\n"
        f"{spec['dead_search']}"
    )
    body: dict[str, Any] = {
        "name": spec["name"],
        "model_name": spec["model_name"],
        "variant_code": spec["variant_code"],
        "variant_label": spec["variant_label"],
        "url": spec["url"],
        "family_key": spec["family_key"],
        "family_name": spec["family_name"],
        "family_url": spec["family_url"],
        "product_url_scope": spec["product_url_scope"],
        "availability_status": AVAILABLE,
        "manufacturer_countries": [country_id],
        "manufacturer_country_ref": country_id,
        "description": spec["description"],
        "purpose": spec["purpose"],
        "features": spec["features"],
        "categories": spec["categories"],
        "sub_category": spec["sub_category"],
        "uses": [USE_IDS[key] for key in spec["uses"]],
        "industries": [INDUSTRY_IDS[key] for key in spec["industries"]],
        "movement_types": [MOVEMENT_IDS[key] for key in spec["movement"]],
        "tags": spec["tags"],
        "information_source_urls": spec["sources"],
        "image": spec["image"],
        "images": [spec["image"]],
        "video_urls": spec["video_urls"],
        "notes": notes,
        "status": "pending_review",
    }
    body.update(spec["typed"])
    return body


def soft_payload(spec: dict[str, Any]) -> dict[str, Any]:
    """Reassert fields that import/copy workflows may wipe, without resetting media."""
    body = payload(spec)
    for key in ("image", "images", "video_urls"):
        body.pop(key, None)
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    args = parser.parse_args()

    source_media = [validate_source_image(spec) for spec in ROBOTS]
    hashes: dict[str, list[int]] = {}
    for row in source_media:
        hashes.setdefault(row["md5"], []).append(row["id"])
    duplicate_hashes = {h: ids for h, ids in hashes.items() if len(ids) > 1}
    if duplicate_hashes:
        raise ValueError(f"cross-model duplicate source images: {duplicate_hashes}")

    client = ResearchApiClient()
    current = {
        int(r["id"]): r
        for company_id in (974, 397, 1373, 254)
        for r in client.list_robots_for_company(company_id)
    }
    expected_ids = {spec["id"] for spec in ROBOTS} | set(REJECTIONS)
    missing = expected_ids - set(current)
    if missing:
        raise ValueError(f"target IDs missing from production: {sorted(missing)}")
    wrong_status = {
        rid: current[rid].get("status")
        for rid in expected_ids
        if (
            (rid in REJECTIONS and current[rid].get("status") not in {"pending_review", "rejected"})
            or (rid not in REJECTIONS and current[rid].get("status") != "pending_review")
        )
    }
    if wrong_status:
        raise ValueError(f"targets no longer pending_review: {wrong_status}")

    preview = {
        "mode": "apply" if args.apply else "dry-run",
        "targets": [spec["id"] for spec in ROBOTS],
        "rejections": REJECTIONS,
        "source_media": source_media,
        "dead_search": {spec["id"]: spec["dead_search"] for spec in ROBOTS},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(preview, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if not args.apply:
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        print(f"Dry run only. Report: {REPORT}")
        return 0

    patched: list[int] = []
    copied: dict[int, Any] = {}
    cdn_media: list[dict[str, Any]] = []
    for spec in ROBOTS:
        robot_id = spec["id"]
        client._patch(f"robots/robots/{robot_id}/", payload(spec))
        patched.append(robot_id)
        print(f"PATCH OK {robot_id} {spec['name']}", flush=True)
        if args.copy_media:
            # A stale robot-level ImageField makes copy-media skip a newly curated
            # external hero even after the RobotPhoto gallery was replaced.
            client._patch(f"robots/robots/{robot_id}/", {"s3_image": None})
            copied[robot_id] = trigger_copy_media(robot_id)
            print(f"COPY OK {robot_id}", flush=True)
        # Reassert soft fields without deleting the freshly copied RobotPhoto objects.
        client._patch(f"robots/robots/{robot_id}/", soft_payload(spec))
        after = client._get(f"robots/robots/{robot_id}/")
        if after.get("status") != "pending_review":
            raise ValueError(f"{robot_id} status changed to {after.get('status')}")
        if after.get("family_key") != spec["family_key"]:
            raise ValueError(f"{robot_id} family_key did not persist")
        if args.copy_media:
            verified = verify_owned_hero(after)
            # The media copier may transcode a JPEG source to WebP, so byte hashes
            # need not match even when the pixels do. Preserve both hashes for audit.
            verified["source_md5"] = spec["expected_md5"]
            verified["source_hash_match"] = (
                verified["md5"] == spec["expected_md5"]
            )
            cdn_media.append(verified)
        time.sleep(0.1)

    rejected: list[int] = []
    for robot_id, reason in REJECTIONS.items():
        client._patch(
            f"robots/robots/{robot_id}/",
            {
                "status": "rejected",
                "rejection_reason": reason[:500],
                "notes": f"[REJECTED 2026-07-21]\n{reason}\n---\n",
            },
        )
        after = client._get(f"robots/robots/{robot_id}/")
        if after.get("status") != "rejected":
            raise ValueError(f"{robot_id} rejection did not persist")
        rejected.append(robot_id)
        print(f"REJECT OK {robot_id}: {reason}", flush=True)

    cdn_hashes: dict[str, list[int]] = {}
    for row in cdn_media:
        cdn_hashes.setdefault(row["md5"], []).append(row["id"])
    cdn_duplicates = {h: ids for h, ids in cdn_hashes.items() if len(ids) > 1}
    if cdn_duplicates:
        raise ValueError(f"cross-model duplicate CDN heroes: {cdn_duplicates}")

    result = {
        "ok": True,
        "patched_pending_review": patched,
        "rejected": rejected,
        "copy_media": copied,
        "source_media": source_media,
        "cdn_media": cdn_media,
        "dead_search": {spec["id"]: spec["dead_search"] for spec in ROBOTS},
    }
    REPORT.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
