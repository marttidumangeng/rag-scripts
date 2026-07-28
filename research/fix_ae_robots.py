"""Fix AE Robotics (company 1375) content-queue — AE-own / white-label products.

aerobot.cc is dead DNS; storefront is automationar.com. Rejects AUBO thumbs,
TYYROBOT wiring diagrams, and DRAStudio-style junk. Reseller AUBO/Fanuc/JAKA/UR
rows are out of scope for this script (separate pass).
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
from youtube_metadata import enrich_video_list

COMPANY_ID = 1375
COMPANY_SLUG = "ae-robotics-co-ltd"
COMPANY_NAME = "AE Robotics Co., Ltd."

# Full-size digood / OEM CDN (no w/170 thumbs). Visually verified 2026-07-13.
IMG_AIR3 = "https://qiniu.digood-assets-fallback.work/5/image_1580699296_AIR3-5.jpg"
IMG_AIR3_DESK = "https://qiniu.digood-assets-fallback.work/5/image_1657269636_1634636858(1).jpg"
IMG_AIR7 = "https://qiniu.digood-assets-fallback.work/5/image_1657270434_7L--B-(4).jpg"
IMG_AIR8 = "https://qiniu.digood-assets-fallback.work/5/image_1657274968_AIR8-710-(2).jpg"
IMG_AIR8_ALT = "https://qiniu.digood-assets-fallback.work/5/image_1657597610_AE-AIR8-A.jpg"
IMG_AIR10 = "https://qiniu.digood-assets-fallback.work/5/image_1657276460_AIR10-A-(4).jpg"
IMG_AIR20 = "https://qiniu.digood-assets-fallback.work/5/image_1657278655_1631609778(1).jpg"
IMG_SCARA = "https://qiniu.digood-assets-fallback.work/5/image_1531629150_TS6-600.jpg"
IMG_DELTA = "https://qiniu.digood-assets-fallback.work/5/image_1560584995_parallels.png"
IMG_PALLET = "https://qiniu.digood-assets-fallback.work/5/image_1692176116_AE-4.jpg"

TAGS_AIR = "6-Axis|Industrial|Manufacturing|Assembly|Pick-and-Place|Factory Automation"
TAGS_WELD = "6-Axis|Industrial|Manufacturing|Welding|Factory Automation"
TAGS_SCARA = "scara|Industrial|Assembly|Pick-and-Place|Electronics|Manufacturing"
TAGS_DELTA = "Delta Robot|Industrial|Pick-and-Place|Packaging|Food|Manufacturing"
TAGS_PALLET = "6-Axis|Industrial|Manufacturing|Warehouse|Logistics|Factory Automation"
TAGS_COBOT = "Collaborative|6-Axis|Industrial|Manufacturing|Assembly"

YT_AIR3 = ["https://www.youtube.com/watch?v=WJV40tC8pv8", "https://www.youtube.com/watch?v=h76ct0olHOI"]
YT_AIR8 = ["https://www.youtube.com/watch?v=4G1YJzqriQM", "https://www.youtube.com/watch?v=h76ct0olHOI"]
YT_AIR10 = ["https://www.youtube.com/watch?v=KWeblfCkhsA", "https://www.youtube.com/watch?v=h76ct0olHOI"]
YT_WELD = ["https://www.youtube.com/watch?v=nOCPZ5022gQ", "https://www.youtube.com/watch?v=98NCv1DWIBQ"]
YT_SCARA = ["https://www.youtube.com/watch?v=dsqVq20pjUs"]
YT_PALLET = ["https://www.youtube.com/watch?v=XVym0x678iU"]
YT_DELTA = ["https://www.youtube.com/watch?v=mmHWsQmzmnU"]  # Warsonco OEM (white-label on AE storefront)
YT_AIR20 = ["https://www.youtube.com/watch?v=h76ct0olHOI", "https://www.youtube.com/watch?v=XVym0x678iU"]

FEAT_AIR3 = (
    "Compact 6-axis AE industrial arm for multi-machine cells; floor/wall/ceiling mount. "
    "Cited storefront specs: 3 kg max payload, 560 mm arm reach, ~23 kg body mass. "
    "EtherCAT-capable cells; sold via automationar.com (aerobot.cc DNS dead)."
)
FEAT_AIR7 = (
    "6-axis AE AIR7L-B industrial / arc-welding manipulator. Storefront cites ~7 kg payload "
    "and ~920 mm reach with ±0.02 mm class repeatability; Ethernet TCP I/O for cell integration."
)
FEAT_AIR8 = (
    "6-axis AE AIR8-A articulated industrial arm. Storefront/YouTube cite 8 kg payload and "
    "710 mm reach for pick-and-place, assembly, and light handling."
)
FEAT_AIR10 = (
    "6-axis AE AIR10-A mid-size industrial arm for pick-and-place and handling. "
    "AutomationAR / AE Robotics demos cite ~10 kg payload and ~1420 mm reach class."
)
FEAT_AIR20 = (
    "6-axis AE AIR20-A higher-payload industrial arm (storefront cites 20 kg payload / "
    "~1720 mm reach) for handling, packing, bending, and palletizing cells."
)
FEAT_SCARA = (
    "4-axis SCARA sold on AE/AutomationAR storefront (TS5/TS6-600 class). Cited: 5 kg payload, "
    "600 mm reach for small-parts pick-and-place. Chassis branding on OEM still is Tiantai — "
    "white-label listing under AE."
)
FEAT_DELTA = (
    "3/4-axis parallel (delta) robot for high-speed pick-and-place packing. Sold on AE "
    "AutomationAR storefront; product stills show Warsonco (华盛控) branding — white-label."
)
FEAT_PALLET = (
    "AE Robotics palletizing cell: industrial arm on wheeled yellow/black cabinet with vacuum "
    "EOAT for carton handling. Official AE Robotics marketing still (not AUBO cobot thumbs)."
)
FEAT_COBOT = (
    "AE20 collaborative 6-axis arm listed on AutomationAR. Storefront PDP embeds AUBO sidebar "
    "thumbs only — no AE-logo cobot still found; using AIR20 family industrial hero as interim."
)

# robot_id -> curated overwrite
ROBOT_FIXES: dict[int, dict[str, Any]] = {
    1446: {
        "name": "AE AIR3-A",
        "model_name": "AIR3-A",
        "url": "https://www.automationar.com/product/ae--robot-3kg-payload-560mm-arm-reach---china-one-stop-robot-supplier-industrial-robotic-arm.html",
        "image": IMG_AIR3,
        "images": [IMG_AIR3],
        "replace_media": True,
        "description": "AE AIR3-A compact 6-axis industrial robot (3 kg / 560 mm class).",
        "features": FEAT_AIR3,
        "dof": 6,
        "payload_kg": 3.0,
        "reach_mm": 560.0,
        "weight_kg": 23.0,
        "weight": "23 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_AIR,
        "videos": YT_AIR3,
        "notes_force": (
            "Specs from automationar.com AIR3 PDP (3 kg / 560 mm / 23 kg). "
            "Hero digood AIR3-5.jpg (older a2 chassis mark on some stills). aerobot.cc DNS dead."
        ),
        "source_note": "automationar.com AIR3 PDP + YouTube WJV40tC8pv8",
    },
    1447: {
        "name": "AE AIR3-a (Desktop)",
        "model_name": "AIR3-A Desktop",
        "url": "https://www.automationar.com/product/ae-air3-a-robot-arm-industrial-6-axis-payload-3kg-and-arm-reach-560mm-robot-mechanical-arm-claw-166.html",
        "image": IMG_AIR3_DESK,
        "images": [IMG_AIR3_DESK],
        "replace_media": True,
        "description": "Desktop-oriented AE AIR3-A 6-axis arm (3 kg / 560 mm class).",
        "features": FEAT_AIR3,
        "dof": 6,
        "payload_kg": 3.0,
        "reach_mm": 560.0,
        "weight_kg": 23.0,
        "weight": "23 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_AIR,
        "videos": YT_AIR3,
        "notes_force": "Desktop listing of AIR3-A; distinct desk-pose hero vs floor-mount AIR3 still.",
        "source_note": "automationar.com desktop AIR3 PDP",
    },
    1448: {
        "name": "AE AIR7L-B",
        "model_name": "AIR7L-B",
        "url": "https://www.automationar.com/product/ae-air7l-b-arc-welding-robot-manipulator-intelligent-robotic-arm-pick-and-place-robot.html",
        "image": IMG_AIR7,
        "images": [IMG_AIR7],
        "replace_media": True,
        "description": "AE AIR7L-B 6-axis industrial / arc-welding robot.",
        "features": FEAT_AIR7,
        "dof": 6,
        "payload_kg": 7.0,
        "reach_mm": 920.0,
        "weight_kg": 53.0,
        "weight": "53 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_WELD,
        "videos": YT_WELD,
        "notes_force": "Payload/reach from storefront; body weight 53 kg from prior CRM (kept when cited).",
        "source_note": "automationar.com AIR7L-B + welding demos",
    },
    1449: {
        "name": "AE AIR8-A",
        "model_name": "AIR8-A",
        "url": "https://www.automationar.com/product/ae-industrial-robot-air8-a-6-axis-robot-programmig-8kg-payload-cobot-industrial-robotic-arm-from-sh.html",
        "image": IMG_AIR8,
        "images": [IMG_AIR8],
        "replace_media": True,
        "description": "AE AIR8-A 6-axis industrial robot (8 kg / 710 mm class).",
        "features": FEAT_AIR8,
        "dof": 6,
        "payload_kg": 8.0,
        "reach_mm": 710.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_AIR,
        "videos": YT_AIR8,
        "notes_force": "8 kg / 710 mm from AutomationAR YouTube AIR8-A demo + PDP.",
        "source_note": "automationar.com AIR8-A + watch?v=4G1YJzqriQM",
    },
    1450: {
        "name": "AE AIR10-A",
        "model_name": "AIR10-A",
        "url": "https://www.automationar.com/product/ae-air10-a-automation-manipulator-industrial-middle-6-axis-robot-arm-like-kuka-robot-arm.html",
        "image": IMG_AIR10,
        "images": [IMG_AIR10],
        "replace_media": True,
        "description": "AE AIR10-A mid-size 6-axis industrial robot.",
        "features": FEAT_AIR10,
        "dof": 6,
        "payload_kg": 10.0,
        "reach_mm": 1420.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_AIR,
        "videos": YT_AIR10,
        "notes_force": "Payload/reach class from AE Robotics AIR10-A pick-and-place YouTube + PDP.",
        "source_note": "automationar.com AIR10-A + KWeblfCkhsA",
    },
    1451: {
        "name": "AE AIR20-A",
        "model_name": "AIR20-A",
        "url": "https://www.automationar.com/product/industry-robot-arm-AE-China-AIR20-A-6-axis-robot-arm-20kg-payload-industrial-robots-from-shenzhen.html",
        "image": IMG_AIR20,
        "images": [IMG_AIR20],
        "replace_media": True,
        "description": "AE AIR20-A 6-axis industrial robot (20 kg / ~1720 mm class).",
        "features": FEAT_AIR20,
        "dof": 6,
        "payload_kg": 20.0,
        "reach_mm": 1720.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_AIR,
        "videos": YT_AIR20,
        "notes_force": (
            "20 kg payload / ~1720 mm reach from AutomationAR AIR20 listing + AE YouTube bending demo. "
            "Corrected CRM URL away from AIR3 slug."
        ),
        "source_note": "industry-robot-arm-AE-China-AIR20-A PDP",
    },
    3534: {
        "name": "AE AIR20-A Industrial Robot",
        "model_name": "AIR20-A",
        "url": "https://www.automationar.com/product/industry-robot-arm-AE-China-AIR20-A-6-axis-robot-arm-20kg-payload-industrial-robots-from-shenzhen.html",
        "image": IMG_AIR20,
        "images": [IMG_AIR20],
        "replace_media": True,
        "description": "AE AIR20-A industrial robot (duplicate CRM row of AIR20-A).",
        "features": FEAT_AIR20,
        "dof": 6,
        "payload_kg": 20.0,
        "reach_mm": 1720.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_AIR,
        "videos": YT_AIR20,
        "notes_force": "Duplicate of AE AIR20-A #1451; fixed wrong AIR3 CRM URL slug.",
        "source_note": "AIR20-A duplicate",
    },
    4831: {
        "name": "AE AIR3-A Industrial Robotic Arm",
        "model_name": "AIR3-A",
        "url": "https://www.automationar.com/product/ae--robot-3kg-payload-560mm-arm-reach---china-one-stop-robot-supplier-industrial-robotic-arm.html",
        "image": IMG_AIR3,
        "images": [IMG_AIR3],
        "replace_media": True,
        "description": "AE AIR3-A industrial robotic arm (duplicate CRM row).",
        "features": FEAT_AIR3,
        "dof": 6,
        "payload_kg": 3.0,
        "reach_mm": 560.0,
        "weight_kg": 23.0,
        "weight": "23 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_AIR,
        "videos": YT_AIR3,
        "notes_force": "Duplicate of AE AIR3-A #1446; same series hero/specs.",
        "source_note": "automationar.com AIR3 PDP",
    },
    4832: {
        "name": "AE AIR7L-B Arc Welding Robot",
        "model_name": "AIR7L-B",
        "url": "https://www.automationar.com/product/ae-air7l-b-arc-welding-robot-manipulator-intelligent-robotic-arm-pick-and-place-robot.html",
        "image": IMG_AIR7,
        "images": [IMG_AIR7],
        "replace_media": True,
        "description": "AE AIR7L-B arc welding robot (duplicate CRM row).",
        "features": FEAT_AIR7,
        "dof": 6,
        "payload_kg": 7.0,
        "reach_mm": 920.0,
        "weight_kg": 53.0,
        "weight": "53 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_WELD,
        "videos": YT_WELD,
        "notes_force": "Duplicate of AE AIR7L-B #1448.",
        "source_note": "automationar.com AIR7L-B",
    },
    4833: {
        "name": "AE AIR8-A Industrial Robot",
        "model_name": "AIR8-A",
        "url": "https://www.automationar.com/product/ae-industrial-robot-air8-a-6-axis-robot-programmig-8kg-payload-cobot-industrial-robotic-arm-from-sh.html",
        "image": IMG_AIR8_ALT,
        "images": [IMG_AIR8_ALT],
        "replace_media": True,
        "description": "AE AIR8-A industrial robot (duplicate CRM row).",
        "features": FEAT_AIR8,
        "dof": 6,
        "payload_kg": 8.0,
        "reach_mm": 710.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_AIR,
        "videos": YT_AIR8,
        "notes_force": (
            "Replaced wrong AUBO-i3 thumbnail from broken PDP scrape; "
            "crate/transport AE-AIR8-A still (AE logo verified)."
        ),
        "source_note": "digood AE-AIR8-A.jpg; rejected aubo-i3.jpg",
    },
    4834: {
        "name": "AE AIR10-A Industrial Robot",
        "model_name": "AIR10-A",
        "url": "https://www.automationar.com/product/ae-air10-a-automation-manipulator-industrial-middle-6-axis-robot-arm-like-kuka-robot-arm.html",
        "image": IMG_AIR10,
        "images": [IMG_AIR10],
        "replace_media": True,
        "description": "AE AIR10-A industrial robot (duplicate CRM row).",
        "features": FEAT_AIR10,
        "dof": 6,
        "payload_kg": 10.0,
        "reach_mm": 1420.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_AIR,
        "videos": YT_AIR10,
        "notes_force": "Replaced wrong AUBO-i3 thumbnail; AIR10-A studio hero.",
        "source_note": "automationar.com AIR10-A",
    },
    1452: {
        "name": "AE AE-25 Palletizer",
        "model_name": "AE-25",
        "url": "https://www.automationar.com/product/ae-25-series-6-axis-industrial-robot-arm-palletizer-robot.html",
        "image": IMG_PALLET,
        "images": [IMG_PALLET],
        "replace_media": True,
        "description": "AE Robotics palletizing cell (AE-25 series listing).",
        "features": FEAT_PALLET,
        "dof": 6,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_PALLET,
        "videos": YT_PALLET,
        "notes_force": (
            "Replaced AUBO-i3 junk hero with AE-4.jpg palletizing cell (AE ROBOTICS branding). "
            "Typed payload not cited on thin PDP — left unset."
        ),
        "source_note": "digood AE-4.jpg + YouTube XVym0x678iU",
    },
    1453: {
        "name": "AE AE20 Cobot",
        "model_name": "AE20 Cobot",
        "url": "https://www.automationar.com/product/ae20-cobot-6-axis-collaborative-robot-arm.html",
        "image": IMG_AIR20,
        "images": [IMG_AIR20],
        "replace_media": True,
        "description": "AE20 collaborative 6-axis arm (AutomationAR listing).",
        "features": FEAT_COBOT,
        "dof": 6,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_COBOT,
        "videos": YT_AIR20,
        "notes_force": (
            "PDP only embeds AUBO sidebar images — rejected. Interim hero = AIR20 AE-logo "
            "industrial still until a cobot-specific AE photo is published."
        ),
        "source_note": "ae20-cobot PDP text; rejected aubo-i3.jpg",
    },
    1454: {
        "name": "AE SCARA Robot",
        "model_name": "TS5-600 / TS6-600",
        "url": "https://www.automationar.com/product/china-hotsale-4-axis-scara-robot-5kg-payload-600mm-arm-reach.html",
        "image": IMG_SCARA,
        "images": [IMG_SCARA],
        "replace_media": True,
        "description": "4-axis SCARA (5 kg / 600 mm) listed by AE AutomationAR.",
        "features": FEAT_SCARA,
        "dof": 4,
        "payload_kg": 5.0,
        "reach_mm": 600.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_SCARA,
        "videos": YT_SCARA,
        "notes_force": (
            "Replaced TYYROBOT wiring-diagram hero with TS6-600 product still (Tiantai brand "
            "on chassis — white-label under AE storefront)."
        ),
        "source_note": "digood TS6-600.jpg + YouTube dsqVq20pjUs",
    },
    1455: {
        "name": "AE Delta Robot",
        "model_name": "AR-600D class",
        "url": "https://www.automationar.com/product/3-4axis-delta-robot-1kg-payload-600mm-working-diameter-for-packing-application.html",
        "image": IMG_DELTA,
        "images": [IMG_DELTA],
        "replace_media": True,
        "description": "Delta/parallel packing robot (AR-600 class) via AE storefront.",
        "features": FEAT_DELTA,
        "dof": 4,
        "payload_kg": 1.0,
        "reach_mm": 600.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_DELTA,
        "videos": YT_DELTA,
        "notes_force": "Warsonco-branded hero; 1 kg / 600 mm working diameter from PDP title.",
        "source_note": "automationar delta PDP + Warsonco YouTube mmHWsQmzmnU",
    },
    3531: {
        "name": "Delta Robot AR-600D",
        "model_name": "AR-600D",
        "url": "https://www.automationar.com/product/3-4axis-delta-robot-1kg-payload-600mm-working-diameter-for-packing-application.html",
        "image": IMG_DELTA,
        "images": [IMG_DELTA],
        "replace_media": True,
        "description": "AR-600D delta robot — 1 kg payload, 600 mm working diameter.",
        "features": FEAT_DELTA + " Model AR-600D: 1 kg / 600 mm class per PDP.",
        "dof": 4,
        "payload_kg": 1.0,
        "reach_mm": 600.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_DELTA,
        "videos": YT_DELTA,
        "notes_force": "Series hero shared with other AR-* (OEM publishes one Warsonco still).",
        "source_note": "AR-600D PDP",
    },
    4819: {
        "name": "Delta Robot AR-500D",
        "model_name": "AR-500D",
        "url": "https://www.automationar.com/product/3-4axis-delta-robot-1kg-payload-500mm-working-diameter-for-packing-application.html",
        "image": IMG_DELTA,
        "images": [IMG_DELTA],
        "replace_media": True,
        "description": "AR-500D delta robot — 1 kg payload, 500 mm working diameter.",
        "features": FEAT_DELTA + " Model AR-500D: 1 kg / 500 mm class per PDP.",
        "dof": 4,
        "payload_kg": 1.0,
        "reach_mm": 500.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_DELTA,
        "videos": YT_DELTA,
        "notes_force": "Shared Warsonco series hero; diameter from PDP title.",
        "source_note": "AR-500D PDP",
    },
    4820: {
        "name": "Delta Robot AR-800D",
        "model_name": "AR-800D",
        "url": "https://www.automationar.com/product/3-4axis-delta-robot-3kg-payload-800mm-working-diameter-for-packing-application.html",
        "image": IMG_DELTA,
        "images": [IMG_DELTA],
        "replace_media": True,
        "description": "AR-800D delta robot — 3 kg payload, 800 mm working diameter.",
        "features": FEAT_DELTA + " Model AR-800D: 3 kg / 800 mm class per PDP.",
        "dof": 4,
        "payload_kg": 3.0,
        "reach_mm": 800.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_DELTA,
        "videos": YT_DELTA,
        "notes_force": "Shared Warsonco series hero; 3 kg / 800 mm from PDP title.",
        "source_note": "AR-800D PDP",
    },
    4821: {
        "name": "Delta Robot AR-1000D",
        "model_name": "AR-1000D",
        "url": "https://www.automationar.com/product/3-4axis-delta-robot-5kg-payload-1000mm-working-diameter-for-packing-application.html",
        "image": IMG_DELTA,
        "images": [IMG_DELTA],
        "replace_media": True,
        "description": "AR-1000D delta robot — 5 kg payload, 1000 mm working diameter.",
        "features": FEAT_DELTA + " Model AR-1000D: 5 kg / 1000 mm class per PDP.",
        "dof": 4,
        "payload_kg": 5.0,
        "reach_mm": 1000.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_DELTA,
        "videos": YT_DELTA,
        "notes_force": "Shared Warsonco series hero; 5 kg / 1000 mm from PDP title.",
        "source_note": "AR-1000D PDP",
    },
}


def _tag_string(robot: dict[str, Any]) -> str:
    tags = robot.get("tags") or robot.get("tags_m2m") or []
    if isinstance(tags, str):
        return tags
    if isinstance(tags, list):
        names = []
        for t in tags:
            if isinstance(t, dict):
                names.append(str(t.get("name") or t.get("slug") or "").strip())
            else:
                names.append(str(t).strip())
        return "|".join(n for n in names if n)
    return ""


def preserve_base(robot: dict[str, Any]) -> dict[str, Any]:
    img = (robot.get("s3_image") or robot.get("image") or "").strip()
    return {
        "name": robot.get("name") or "",
        "model_name": robot.get("model_name") or robot.get("name") or "",
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "url": robot.get("url") or "",
        "image": img,
        "description": robot.get("description") or "",
        "purpose": robot.get("purpose") or "",
        "features": robot.get("features") or "",
        "notes": robot.get("notes") or "",
        "tags": _tag_string(robot),
        "source_locale": robot.get("source_locale") or "en",
        "release_year": robot.get("release_year"),
        "weight_kg": robot.get("weight_kg"),
        "weight": robot.get("weight") or "",
        "payload_kg": robot.get("payload_kg"),
        "dof": robot.get("dof"),
        "reach_mm": robot.get("reach_mm"),
    }


def build_row(robot: dict[str, Any], fix: dict[str, Any]) -> dict[str, Any]:
    row = preserve_base(robot)
    for key, val in fix.items():
        if key in ("replace_media", "notes_force", "source_note", "videos", "images"):
            continue
        if val is not None and val != "":
            row[key] = val
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        existing = (row.get("research_notes") or "").strip()
        row["research_notes"] = (
            f"{existing} | {fix['source_note']}" if existing else fix["source_note"]
        )
    videos = fix.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    if fix.get("images"):
        row["images"] = list(fix["images"])
    row["company_slug"] = COMPANY_SLUG
    row["company_name"] = COMPANY_NAME
    return row


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("WARN: no INTERNAL_API_SECRET / API base for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}", flush=True)
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.15)
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix AE Robotics company 1375 AE-own robots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--no-replace-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
    parser.add_argument("--mark-done", action="store_true", help="Only if all company gaps cleared")
    args = parser.parse_args()

    client = ResearchApiClient()
    all_robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    targets = []
    for rid, fix in ROBOT_FIXES.items():
        if args.only and rid not in args.only:
            continue
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        row = build_row(robot, fix)
        if not (row.get("image") or "") or len(row.get("features") or "") < 40:
            print(f"ERROR dry-run gate fail {rid}: need image+features", file=sys.stderr)
            return 1
        if not row.get("video_urls"):
            print(f"ERROR dry-run gate fail {rid}: need videos", file=sys.stderr)
            return 1
        if not (row.get("tags") or ""):
            print(f"ERROR dry-run gate fail {rid}: need tags", file=sys.stderr)
            return 1
        do_replace = bool(fix.get("replace_media")) and not args.no_replace_media
        targets.append(
            {
                "id": rid,
                "name": robot.get("name"),
                "replace_media": do_replace,
                "image": row.get("image") or "",
                "features_len": len(row.get("features") or ""),
                "vids": len(row.get("video_urls") or []),
                "row": row,
            }
        )
        print(
            f"  {rid} {robot.get('name')}: "
            f"img={'NEW' if do_replace else 'keep'} "
            f"feat={len(row.get('features') or '')} vids={len(row.get('video_urls') or [])}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "ae-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            [{k: v for k, v in t.items() if k != "row"} for t in targets],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not targets:
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="ae-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    imported: list[int] = []
    all_ok = True
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
                replace_media=bool(item.get("replace_media")),
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            continue
        err = int(result.get("error_count") or 0)
        if err:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result}", file=sys.stderr)
        else:
            imported.append(rid)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  imported {rid}: {result.get('results')}")

    for item in targets:
        rid = item["id"]
        notes = ROBOT_FIXES[rid].get("notes_force")
        if not notes:
            continue
        try:
            client._patch(f"robots/robots/{rid}/", {"notes": notes})
        except Exception as exc:
            print(f"  notes fail {rid}: {exc}", file=sys.stderr)

    copy_stats = None
    if args.copy_media:
        need = [t["id"] for t in targets if t["replace_media"]]
        ok, fail = trigger_copy_media(need)
        copy_stats = {"ok": ok, "fail": fail, "ids": need}
        print(f"copy-media ok={ok} fail={fail}")

    if args.mark_done and all_ok:
        print("WARN: --mark-done ignored — reseller gaps remain on company 1375", file=sys.stderr)

    out = {"ok": all_ok, **totals, "imported": imported, "copy_media": copy_stats}
    (_RESEARCH_DIR / "staging" / "reports" / "ae-fix-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
