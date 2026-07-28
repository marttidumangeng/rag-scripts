"""Fix Rainbow Robotics (company 228) content-queue enrichment.

OEM: https://www.rainbow-robotics.com (+ rainbowastro.com for RST mounts).

Issues addressed:
- 6 cobots shared identical CDN hero bytes — replace with distinct OEM product_spec renders
- All cobots had payload_kg=3.0 (RB3 copy) — restore OEM payload/reach/weight/repeatability
- Duplicate RB-Y1 (4240) and RB16 alias (4859) — reject
- RBM-S100b carried S100a specs — correct to OEM S100b table
- Imageless RST mounts — rainbowastro product photos
- Missing family_* / wrong tags (Humanoid on cobots) / stale availability
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from robot_auto_research import slugify_robot_name
from tag_suggest import TagCatalog
from youtube_metadata import enrich_video_list

COMPANY_ID = 228
COMPANY_SLUG = "rainbow-robotics"
COMPANY_NAME = "Rainbow Robotics"
KR = "KR"

OEM = "https://www.rainbow-robotics.com"
URL_RB = f"{OEM}/en_rb"
URL_RBY1 = f"{OEM}/en_rby1"
URL_RBQ = f"{OEM}/en_rbq"
URL_RBM = f"{OEM}/en_rbm_s100_new"
URL_ASTRO = f"{OEM}/en_astro"
URL_RST135E = "https://www.rainbowastro.com/rst-135e"
URL_RST135 = "https://www.rainbowastro.com/rst-135"
URL_RST300 = "https://www.rainbowastro.com/rst-300"

# Distinct OEM product_spec / product_info heroes (md5-verified unique).
IMG = {
    "RB3-730": f"{OEM}/storage/app/public/plugin/product_spec/d881b0d8-97e0-11ec-9874-6805cae14dd4/1e/d5/2022091517382629fc5a30c1b0c7d9330982e7189aaec45d5542d7.png",
    "RB3-1200": f"{OEM}/storage/app/public/plugin/product_spec/d881b0d8-97e0-11ec-9874-6805cae14dd4/04/7d/20220915173839627f4a9e6b14b6f598e7c678cb72d2089eb1a7b2.png",
    "RB5-850": f"{OEM}/storage/app/public/plugin/product_info/30a233af-97df-11ec-9874-6805cae14dd4/e2/f9/20241104170324a0b7b9d3b13e5614ba41aebba9e41a82479c035c.png",
    "RB10-1300": f"{OEM}/storage/app/public/plugin/product_spec/d881b0d8-97e0-11ec-9874-6805cae14dd4/ed/37/20220915173943d86aeb6b6c836778d7bdc23225a0fb49d509b309.png",
    "RB16-900": f"{OEM}/storage/app/public/plugin/product_spec/d881b0d8-97e0-11ec-9874-6805cae14dd4/6c/45/2024110118190796c0d772b6ccd1e1ce072c24e5d2704ec23a34e7.png",
    "RB20-1900": f"{OEM}/storage/app/public/plugin/product_spec/d881b0d8-97e0-11ec-9874-6805cae14dd4/cb/93/20241105142545f25bd9320164fb3bcf7f8434e19b9263f0bf986d.PNG",
    "RB6-920": f"{OEM}/storage/app/public/plugin/product_spec/d881b0d8-97e0-11ec-9874-6805cae14dd4/64/15/202411051434541725ce83ee5590e747577062499b688e854cc754.png",
    "RB6-1700": f"{OEM}/storage/app/public/plugin/product_spec/d881b947-97e0-11ec-9874-6805cae14dd4/28/23/202411051050359d568f036c2888754891d2fe6228f6e03e0f0e41.png",
    "RB-Y1": f"{OEM}/storage/app/public/plugin/product_info/d18fdf92-58e5-4692-8681-616532f079cc/63/bd/20250424170529375d22e52b6b52470692e1d9b169e8754c9f263a.PNG",
    "RBQ-10": f"{OEM}/storage/app/public/plugin/product_info/30a232fc-97df-11ec-9874-6805cae14dd4/18/3f/202506131638574d2475e36a3f9adbc49d3cc5453b53567f90844c.png",
    "RBM-S100b": f"{OEM}/storage/app/public/plugin/product_spec/e9c24486-7c02-44a5-82a1-faa70f7a10aa/1f/14/20250515143217b1e0e882300eabe77c0f7fafeb324762a7f87a81.png",
    "RST-135E": "https://www.rainbowastro.com/wp-content/uploads/2021/04/RST-135E_front-1_crop_800px_q8.jpg",
    "RST-135": "https://www.rainbowastro.com/wp-content/uploads/2020/02/RST-135_2_s_c_1.jpg",
    "RST-300": f"{OEM}/storage/app/public/plugin/product_info/30a23450-97df-11ec-9874-6805cae14dd4/7d/e3/20220228021814a00dc4eeb3c2c3194592ac3c16b50ba536c07432.png",
}

YT_RB_CNC = "https://www.youtube.com/watch?v=5jLk5dFBU_E"
YT_RB_LOGISTICS = "https://www.youtube.com/watch?v=N-98Rchcxgk"
YT_RB_STUDIO = "https://www.youtube.com/watch?v=YT3Xbt-_kuc"
YT_RBY1_HL = "https://www.youtube.com/watch?v=D6M2IhSLSmY"
YT_RBY1_FN = "https://www.youtube.com/watch?v=6KCyw5qhYbA"
YT_RBY1_CUPS = "https://www.youtube.com/watch?v=MMAiJi-kodg"
YT_RBQ = "https://www.youtube.com/watch?v=YMsJH2XbERI"
YT_RBM_MULTI = "https://www.youtube.com/watch?v=qr0YqCJPwV8"
YT_RBM_LOAD = "https://www.youtube.com/watch?v=ZgOHfAIuiKA"
YT_RST135E = "https://www.youtube.com/watch?v=eb_IS6ysJEs"
YT_RST135 = "https://www.youtube.com/watch?v=WS6p9XpRrx4"
YT_RST300 = "https://www.youtube.com/watch?v=gbkvhSJc8KU"

TAGS_COBOT = "6-Axis|Collaborative Robot|Cobot|Industrial|Manufacturing|Assembly|Pick-and-Place|Stationary"
TAGS_RBY1 = "Humanoid|Mobile Manipulator|Wheeled|Research|Industrial|Dexterous Manipulation"
TAGS_RBQ = "Quadruped|Legged|Inspection|Patrol|Service|Research"
TAGS_RBM = "AMR|Autonomous Mobile Robot|Logistics|Material Handling|Indoor|Wheeled|Compact"
TAGS_RST = "Research|space|Stationary|Compact"

REJECTS: dict[int, str] = {
    4240: (
        "Duplicate of robot 4861 (RB-Y1). This record used wrong URL "
        "(rainbowrobotics.com without hyphen), incorrect bipedal/education copy, "
        "and no product image. Keep 4861 as the canonical OEM-enriched RB-Y1."
    ),
    4859: (
        "Duplicate of robot 2211 (RB16-900). 'RB16 (16kg Payload)' is the same SKU "
        "as RB16-900 on the OEM cobot family page (16 kg / 900 mm). Keep 2211."
    ),
}

COBOT_FEATURES = (
    "In-house engineered high-performance collaborative arm; "
    "globally certified safety (NRTL, CE, KCs / TÜV SÜD — ISO 13849-1 Cat.3 PL d, "
    "ISO 10218-1, ISO/TS 15066); ±0.05 mm repeatability; IP-rated operating environment "
    "per model; M8 tool flange; 5 m robot-arm cable."
)

COBOT_PURPOSE = (
    "Packaging\nWelding\nAssembly\nQuality inspection\nBonding and gluing\nPicking and placing"
)


def cobot(
    *,
    rid: int,
    name: str,
    payload: float,
    reach: float,
    weight: float,
    footprint_note: str,
    ip: str,
    availability: str = "available",
    name_suffix: str = "",
) -> dict[str, Any]:
    display = name if not name_suffix else f"{name}{name_suffix}"
    return {
        "name": display,
        "model_name": name,
        "variant_code": name,
        "variant_label": name,
        "url": f"{URL_RB}#{name.lower()}",
        "family_key": f"{COMPANY_SLUG}:rb",
        "family_name": "RB Series",
        "family_url": URL_RB,
        "product_url_scope": "exact_variant",
        "image": IMG[name],
        "description": (
            f"The {name} is a Rainbow Robotics collaborative robot arm with a "
            f"{payload:g} kg payload and {reach:g} mm reach, built for safe human-robot "
            f"cooperation on industrial tasks such as packaging, welding, assembly, and inspection."
        ),
        "purpose": COBOT_PURPOSE,
        "features": (
            f"{COBOT_FEATURES} Model {name}: payload {payload:g} kg, reach {reach:g} mm, "
            f"arm weight {weight:g} kg, footprint {footprint_note}, operating environment {ip}."
        ),
        "dof": 6,
        "payload_kg": payload,
        "reach_mm": reach,
        "repeatability_mm": 0.05,
        "weight_kg": weight,
        "weight": f"{weight:g} kg",
        "availability_status_key": availability,
        "movement_type_keys": "stationary",
        "industry_keys": "manufacturing",
        "use_keys": "assembly|pick-and-place|welding|palletizing",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_COBOT,
        "manufacturer_country_code": KR,
        "videos": [YT_RB_CNC, YT_RB_LOGISTICS, YT_RB_STUDIO],
        "information_source_urls": [URL_RB],
        "notes_force": (
            f"[AI Research] OEM specs from {URL_RB} ({name}): payload {payload:g} kg, "
            f"reach {reach:g} mm, weight {weight:g} kg, repeatability ±0.05 mm, {ip}. "
            f"Hero: distinct OEM product render (replaced shared CDN collision hash)."
        ),
        "source_note": f"{URL_RB} Specification — {name}",
    }


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    2196: cobot(rid=2196, name="RB3-730", payload=3, reach=730, weight=11, footprint_note="Ø 128 mm", ip="IP54 / 0-50 °C"),
    2200: cobot(rid=2200, name="RB3-1200", payload=3, reach=1200, weight=22.4, footprint_note="∅ 173 mm", ip="IP66 / 0-50 °C"),
    2202: cobot(rid=2202, name="RB5-850", payload=5, reach=927.7, weight=22, footprint_note="∅ 173 mm", ip="IP66 / 0-50 °C"),
    2206: cobot(rid=2206, name="RB10-1300", payload=10, reach=1300, weight=37.1, footprint_note="∅ 196 mm", ip="IP66 / 0-50 °C"),
    2211: cobot(rid=2211, name="RB16-900", payload=16, reach=900, weight=32, footprint_note="Ø 196 mm", ip="IP66 / 0-50 °C"),
    2215: cobot(rid=2215, name="RB20-1900", payload=20, reach=1900, weight=75, footprint_note="Ø 245 mm", ip="IP66 / 0-50 °C"),
    2221: cobot(
        rid=2221,
        name="RB6-920",
        payload=6,
        reach=920,
        weight=19.6,
        footprint_note="Ø 173 mm",
        ip="IP66 / 0-50 °C",
        availability="announced",
        name_suffix="",
    ),
    2224: cobot(rid=2224, name="RB6-1700", payload=6, reach=1700, weight=39, footprint_note="Ø 128 mm", ip="IP66 / 0-50 °C"),
    4861: {
        "name": "RB-Y1",
        "model_name": "RB-Y1",
        "variant_code": "RB-Y1",
        "variant_label": "RB-Y1",
        "url": URL_RBY1,
        "family_key": f"{COMPANY_SLUG}:rb-y1",
        "family_name": "RB-Y1",
        "family_url": URL_RBY1,
        "product_url_scope": "exact_variant",
        "image": IMG["RB-Y1"],
        "description": (
            "RB-Y1 is Rainbow Robotics' dual-arm mobile manipulator: two 7-DOF arms and a "
            "6-DOF leg on a wheeled base, built as an open platform for AI teleoperation "
            "and industrial dexterous tasks."
        ),
        "purpose": (
            "Dexterous dual-arm manipulation\n"
            "AI research and teleoperation\n"
            "Mobile pick-and-place\n"
            "Humanoid-form industrial assistance"
        ),
        "features": (
            "Dual 7-DOF arms (3 kg payload per arm); 6-DOF leg; 1-DOF grippers x2; "
            "1-DOF wheels x2; total 24 DOF; size 600 x 690 x 1,400 mm (W x D x H); "
            "battery 50 V / 25 Ah (1,270 Wh); mobile velocity 1.5 m/s; total weight 131 kg "
            "(upper 38 / lower 42 / mobile 51 kg)."
        ),
        "dof": 24,
        "payload_kg": 3.0,
        "weight_kg": 131.0,
        "weight": "131 kg",
        "speed": 5.4,  # 1.5 m/s → km/h
        "width_mm": 600,
        "length_mm": 690,
        "height_mm": 1400,
        "battery_wh": 1270,
        "availability_status_key": "available",
        "movement_type_keys": "wheeled",
        "industry_keys": "manufacturing|research",
        "use_keys": "pick-and-place|assembly",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_RBY1,
        "manufacturer_country_code": KR,
        "videos": [YT_RBY1_HL, YT_RBY1_FN, YT_RBY1_CUPS],
        "information_source_urls": [URL_RBY1],
        "notes_force": (
            f"[AI Research] OEM specs from {URL_RBY1}: 24 DOF, 3 kg/arm, 131 kg, "
            "1.5 m/s, 600x690x1400 mm, 1270 Wh. Hero: OEM product_info render."
        ),
        "source_note": f"{URL_RBY1} Specifications",
    },
    4862: {
        "name": "RBQ-10",
        "model_name": "RBQ-10",
        "variant_code": "RBQ-10",
        "variant_label": "RBQ-10",
        "url": f"{URL_RBQ}#rbq-10",
        "family_key": f"{COMPANY_SLUG}:rbq",
        "family_name": "RBQ",
        "family_url": URL_RBQ,
        "product_url_scope": "exact_variant",
        "image": IMG["RBQ-10"],
        "description": (
            "RBQ-10 is Rainbow Robotics' higher-payload quadruped platform for inspection "
            "and field tasks, with LiDAR/camera mounting options and up to about three hours "
            "of operation on a full charge."
        ),
        "purpose": (
            "Quadruped inspection\n"
            "Sensor payload carriage\n"
            "Field and facility patrol"
        ),
        "features": (
            "Size 945 x 440 x 565 mm; weight 37 kg; payload 10 kg; operating time up to "
            "3 hours on full charge (1.5 hours in continuous walking); step walking ability "
            "12 cm; Wi-Fi communication; supports lidar/camera sensor installs."
        ),
        "payload_kg": 10.0,
        "weight_kg": 37.0,
        "weight": "37 kg",
        "width_mm": 440,
        "length_mm": 945,
        "height_mm": 565,
        "runtime_minutes": 180,
        "availability_status_key": "available",
        "movement_type_keys": "legged",
        "industry_keys": "security|manufacturing",
        "use_keys": "inspection",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "security",
        "tags": TAGS_RBQ,
        "manufacturer_country_code": KR,
        "videos": [YT_RBQ],
        "information_source_urls": [URL_RBQ],
        "notes_force": (
            f"[AI Research] OEM specs from {URL_RBQ} RBQ-10: 10 kg payload, 37 kg, "
            "945x440x565 mm, up to 3 h runtime, 12 cm step."
        ),
        "source_note": f"{URL_RBQ} Specification — RBQ-10",
    },
    4860: {
        "name": "RBM-S100b",
        "model_name": "RBM-S100b",
        "variant_code": "RBM-S100b",
        "variant_label": "RBM-S100b",
        "url": f"{URL_RBM}#rbm-s100b",
        "family_key": f"{COMPANY_SLUG}:rbm-s100",
        "family_name": "RBM-S100",
        "family_url": URL_RBM,
        "product_url_scope": "exact_variant",
        "image": IMG["RBM-S100b"],
        "description": (
            "RBM-S100b is Rainbow Robotics' larger autonomous logistics AMR in the RBM-S100 "
            "series, with dual LiDAR plus 3D cameras for multi-robot indoor transport."
        ),
        "purpose": (
            "Autonomous indoor logistics\n"
            "Goods-to-person tote transport\n"
            "Multi-robot warehouse operation"
        ),
        "features": (
            "Size 680 x 710 x 1250 mm; weight 70 kg; payload 100 kg; sensors 2D LiDAR x2 + "
            "3D camera; max speed 1.2 m/s; tray load capacity 365 x 565 x 300 mm; "
            "10.1 in display (1280x800); 2 trays (expandable)."
        ),
        "payload_kg": 100.0,
        "weight_kg": 70.0,
        "weight": "70 kg",
        "speed": 4.32,  # 1.2 m/s → km/h
        "width_mm": 680,
        "length_mm": 710,
        "height_mm": 1250,
        "availability_status_key": "available",
        "movement_type_keys": "wheeled",
        "industry_keys": "logistics|manufacturing",
        "use_keys": "material-handling|pick-and-place",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_RBM,
        "manufacturer_country_code": KR,
        "videos": [YT_RBM_MULTI, YT_RBM_LOAD],
        "information_source_urls": [URL_RBM],
        "notes_force": (
            f"[AI Research] Corrected from S100a mix-up. OEM {URL_RBM} RBM-S100b: "
            "100 kg payload, 70 kg weight, 680x710x1250 mm, 1.2 m/s, 2 trays."
        ),
        "source_note": f"{URL_RBM} Specification — RBM-S100b",
    },
    4863: {
        "name": "RST-135E",
        "model_name": "RST-135E",
        "variant_code": "RST-135E",
        "variant_label": "RST-135E",
        "url": f"{URL_ASTRO}#rst-135e",
        "family_key": f"{COMPANY_SLUG}:rst",
        "family_name": "RST Weightless Mount",
        "family_url": URL_ASTRO,
        "product_url_scope": "exact_variant",
        "image": IMG["RST-135E"],
        "description": (
            "RST-135E is Rainbow Astro's strain-wave (harmonic drive) equatorial/alt-az "
            "weightless mount with Renishaw encoder feedback and ±2.5 arcsec periodic error."
        ),
        "purpose": (
            "Astronomical pointing and tracking\n"
            "Astrophotography mount\n"
            "Portable equatorial / alt-az dual-mode mounting"
        ),
        "features": (
            "Weightless mount (counterweights not required up to rated load); strain wave "
            "gear / harmonic drive; ±2.5 arcsec PE with Renishaw RA encoder; capacity "
            "13.5 kg (max 18 kg with counterweight); mount weight 3.4 kg; 5-year warranty "
            "per Rainbow Astro."
        ),
        "payload_kg": 13.5,
        "weight_kg": 3.4,
        "weight": "3.4 kg",
        "availability_status_key": "available",
        "movement_type_keys": "stationary",
        "industry_keys": "research",
        "use_keys": "",
        "category_slugs": "research-robots",
        "sub_category_slug": "learning",
        "tags": TAGS_RST,
        "manufacturer_country_code": KR,
        "videos": [YT_RST135E],
        "information_source_urls": [URL_ASTRO, URL_RST135E],
        "notes_force": (
            f"[AI Research] OEM specs from {URL_RST135E}: 3.4 kg mount, 13.5 kg capacity "
            "(max 18 kg), ±2.5 arcsec PE. Hero: rainbowastro product photo."
        ),
        "source_note": f"{URL_RST135E} FEATURE SPECIFICATIONS",
    },
    3540: {
        "name": "RST-135",
        "model_name": "RST-135",
        "variant_code": "RST-135",
        "variant_label": "RST-135",
        "url": f"{URL_ASTRO}#rst-135",
        "family_key": f"{COMPANY_SLUG}:rst",
        "family_name": "RST Weightless Mount",
        "family_url": URL_ASTRO,
        "product_url_scope": "exact_variant",
        "image": IMG["RST-135"],
        "description": (
            "RST-135 is Rainbow Astro's ultra-compact strain-wave weightless mount for "
            "equatorial/alt-az celestial tracking without counterweights in typical loads."
        ),
        "purpose": (
            "Astronomical pointing and tracking\n"
            "Portable astrophotography\n"
            "Equatorial / alt-az dual-mode mounting"
        ),
        "features": (
            "Weightless mount; strain wave gear / harmonic drive; ultra-small and ultra-light "
            "form factor for mobile and expedition observing; equatorial/alt-az dual mount."
        ),
        "payload_kg": 13.5,
        "availability_status_key": "available",
        "movement_type_keys": "stationary",
        "industry_keys": "research",
        "category_slugs": "research-robots",
        "sub_category_slug": "learning",
        "tags": TAGS_RST,
        "manufacturer_country_code": KR,
        "videos": [YT_RST135],
        "information_source_urls": [URL_ASTRO, URL_RST135],
        "notes_force": (
            f"[AI Research] OEM pages {URL_ASTRO} / {URL_RST135}. Capacity aligned with "
            "family weightless-mount rating 13.5 kg where cited on sibling RST-135E datasheet; "
            "exact RST-135 mass left blank pending a model-specific OEM weight line. "
            "Hero: rainbowastro product photo."
        ),
        "source_note": f"{URL_RST135} + {URL_ASTRO}",
    },
    3541: {
        "name": "RST-300",
        "model_name": "RST-300",
        "variant_code": "RST-300",
        "variant_label": "RST-300",
        "url": f"{URL_ASTRO}#rst-300",
        "family_key": f"{COMPANY_SLUG}:rst",
        "family_name": "RST Weightless Mount",
        "family_url": URL_ASTRO,
        "product_url_scope": "exact_variant",
        "image": IMG["RST-300"],
        "description": (
            "RST-300 is Rainbow Astro's higher-capacity strain-wave weightless mount "
            "(30 kg without counterweight; up to 50 kg with), with a built-in RA-axis brake."
        ),
        "purpose": (
            "Heavy astronomical payload tracking\n"
            "Observatory and large-OTA mounting\n"
            "Strain-wave celestial pointing"
        ),
        "features": (
            "Weightless mount; strain wave gear; built-in brake on RA axis; rated load "
            "30 kg without counterweight / up to 50 kg with counterweight (Rainbow Astro)."
        ),
        "payload_kg": 30.0,
        "availability_status_key": "announced",
        "movement_type_keys": "stationary",
        "industry_keys": "research",
        "category_slugs": "research-robots",
        "sub_category_slug": "learning",
        "tags": TAGS_RST,
        "manufacturer_country_code": KR,
        "videos": [YT_RST300],
        "information_source_urls": [URL_ASTRO, URL_RST300],
        "notes_force": (
            f"[AI Research] Payload from Rainbow Astro RST-300 announcement "
            f"({URL_RST300}): 30 kg / 50 kg with CW. Availability set to announced "
            "(OEM page historically marked under development). Hero: OEM product_info photo."
        ),
        "source_note": f"{URL_RST300} + {URL_ASTRO}",
    },
}

# Fix RB6-920 display name (drop "To be released" clutter; availability=announced)
ROBOT_FIXES[2221]["name"] = "RB6-920"
ROBOT_FIXES[2221]["notes_force"] += " OEM lists as '(To be released)' — availability_status=announced."


def _admin_base() -> str:
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    return api.replace("/api/v1", "") or "https://ragadmin.robotaigeek.com"


def _internal_secret() -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    return secret


def reject_robot(rid: int, reason: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {"Content-Type": "application/json", "X-Internal-Secret": _internal_secret()}
    try:
        resp = requests.post(
            url, headers=headers, json={"type": "robot", "reason": reason}, timeout=120
        )
        return f"{resp.status_code} {(resp.text or '')[:160]}"
    except requests.RequestException as e:
        return f"ERR {e}"


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = _internal_secret()
    api = _admin_base()
    if not secret:
        print("WARN: no INTERNAL_API_SECRET for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            body: dict[str, Any] = {}
            try:
                body = resp.json() if resp.content else {}
            except Exception:
                body = {}
            success = bool(body.get("success")) if "success" in body else resp.ok
            if resp.ok and success:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code} body={body}", flush=True)
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.2)
    return ok, fail


def resolve_tags(catalog: TagCatalog, pipe: str) -> str:
    names = [n.strip() for n in pipe.split("|") if n.strip()]
    out: list[str] = []
    missing: list[str] = []
    for n in names:
        hit = catalog._by_name.get(n.lower())
        if hit:
            out.append(str(hit.get("name") or n))
        else:
            missing.append(n)
    if missing:
        print(f"WARN unresolved tags: {missing}", file=sys.stderr)
    return "|".join(out)


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
    }
    skip = {"videos", "notes_force", "source_note", "images", "replace_media"}
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        row["research_notes"] = fix["source_note"]
    videos = fix.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    if fix.get("image"):
        row["images"] = [fix["image"]]
    return row


_AVAIL_IDS = {"announced": 10, "available": 11, "released": 3, "discontinued": 4, "pre_order": 12}


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    """Re-PATCH typed columns + family after bulk-import (can wipe some fields).

    Send fields one-at-a-time: a single bad key (e.g. availability_status as a
    string key) 400s the whole batch. Availability must be the integer FK id.
    """
    body: dict[str, Any] = {}
    for k in (
        "payload_kg",
        "reach_mm",
        "repeatability_mm",
        "weight_kg",
        "dof",
        "speed",
        "width_mm",
        "length_mm",
        "height_mm",
        "runtime_minutes",
        "battery_wh",
        "family_key",
        "family_name",
        "family_url",
        "model_name",
        "variant_code",
        "variant_label",
        "product_url_scope",
        "purpose",
        "name",
        "manufacturer_country_code",
    ):
        if k in fix and fix[k] not in (None, ""):
            body[k] = fix[k]
    avail_key = fix.get("availability_status_key")
    if avail_key:
        body["availability_status"] = _AVAIL_IDS.get(str(avail_key), avail_key)
    ok_keys: list[str] = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok_keys.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Rainbow Robotics company 228")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--reject-dupes", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    all_robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    if args.reject_dupes:
        for rid, reason in REJECTS.items():
            if args.only and rid not in args.only:
                continue
            if not args.apply:
                print(f"dry-run reject {rid}: {reason[:80]}...")
                continue
            msg = reject_robot(rid, reason)
            print(f"reject {rid}: {msg}")

    targets = []
    for rid, fix in ROBOT_FIXES.items():
        if args.only and rid not in args.only:
            continue
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        row = build_row(fix, tags=tags)
        if len(row.get("features") or "") < 40:
            print(f"ERROR {rid}: features too short", file=sys.stderr)
            return 1
        if not row.get("family_key"):
            print(f"ERROR {rid}: missing family_key", file=sys.stderr)
            return 1
        if not row.get("image"):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        if not row.get("video_urls"):
            print(f"ERROR {rid}: missing videos", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: payload={row.get('payload_kg')} "
            f"reach={row.get('reach_mm')} fam={row.get('family_key')} "
            f"avail={row.get('availability_status_key')} vids={len(row.get('video_urls') or [])}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "rainbow-228-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "payload_kg": t["row"].get("payload_kg"),
                    "reach_mm": t["row"].get("reach_mm"),
                    "family_key": t["row"].get("family_key"),
                    "image": (t["row"].get("image") or "")[:120],
                    "availability": t["row"].get("availability_status_key"),
                }
                for t in targets
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not targets and not args.reject_dupes:
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media --verify-cdn --reject-dupes")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="rainbow-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    imported: list[int] = []
    for item in targets:
        rid = item["id"]
        row = item["row"]
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        fpath = tmp / f"{slugify_robot_name(str(item['name']))}-{rid}.json"
        fpath.write_text(json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            result = client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=False,
                replace_media=True,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            continue
        created = int(result.get("created_count") or 0)
        if created:
            print(f"IMPORT FAIL {rid}: unexpected created_count={created} {result}", file=sys.stderr)
            continue
        err = int(result.get("error_count") or 0)
        if err:
            print(f"IMPORT FAIL {rid}: {result}", file=sys.stderr)
        else:
            imported.append(rid)
            patch_typed(client, rid, item["fix"])
            notes = item["fix"].get("notes_force")
            if notes:
                try:
                    client._patch(f"robots/robots/{rid}/", {"notes": notes})
                except Exception as exc:
                    print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  imported {rid}: {result.get('results')}")

    copy_stats = None
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        copy_stats = {"ok": ok, "fail": fail, "ids": imported}
        print(f"copy-media ok={ok} fail={fail}")

    if args.verify_cdn and imported:
        from verify_cdn_images import main as verify_main  # type: ignore

        # Prefer CLI helper
        import subprocess

        rc = subprocess.call(
            [sys.executable, str(_RESEARCH_DIR / "verify_cdn_images.py"), "--company-id", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )
        if rc != 0:
            print("CDN verify FAILED", file=sys.stderr)
            return rc

    if args.mark_done and imported:
        done_path = _RESEARCH_DIR / "state" / "content_queue_done.json"
        done: dict[str, Any] = {}
        if done_path.is_file():
            done = json.loads(done_path.read_text(encoding="utf-8"))
        done[str(COMPANY_ID)] = {
            "name": COMPANY_NAME,
            "at": time.strftime("%Y-%m-%d"),
            "robots": imported,
        }
        done_path.write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
        print(f"marked done in {done_path}")

    print("totals", totals, "copy", copy_stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
