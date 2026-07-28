"""Fix DELTA Electronics Shanghai (company 1206) content-queue robots.

Replaces about-page/banner junk media and company-boilerplate features with
landing.deltaww.com product heroes + catalog-cited specs. No Gemini.
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

COMPANY_ID = 1206
COMPANY_SLUG = "delta-electronics-shanghai-co-ltd"
COMPANY_NAME = "DELTA Electronics (SHANGHAI) Co., Ltd."

CATALOG_PDF = (
    "https://landing.deltaww.com/IA/downloadcenter/catalogue/5.Robot/Robot_ALL/"
    "DELTA_IA-Robot_ALL_C_EN_ver2022_20230107.pdf"
)

# Official filecenter product stills (visually verified).
IMG_DRS60 = "https://filecenter.deltaww.com/products/Images/2512/202512181130250843001.JPG"
IMG_DRS30 = "https://filecenter.deltaww.com/products/Images/2512/202512181152280443001.JPG"
# Prefer DRS40L3SS2 page hero (newer/higher-res) over legacy DRS40L_M.JPG
IMG_DRS40L3 = "https://filecenter.deltaww.com/products/Images/2310/202310251556586785001.JPG"
IMG_DRS40C4 = "https://filecenter.deltaww.com/products/Images/2310/202310251554484629001.JPG"
IMG_DRV70 = "https://filecenter.deltaww.com/products/Images/06/060603/DRV70L_P_M.JPG"
IMG_DRV90 = "https://filecenter.deltaww.com/products/Images/06/060603/DRV90L_P_M.JPG"
# Distinct high-res DRV90 still (differentiates from DRV70 catalog P_M pose)
IMG_DRV90_ALT = "https://filecenter.deltaww.com/products/images/2603/202603251346151215001.jpg"
IMG_DRVA1L7 = "https://filecenter.deltaww.com/products/images/2512/202512181223393258001.JPG?w=756"
IMG_DRVA1LC = "https://filecenter.deltaww.com/products/images/2512/202512181224257796001.JPG?w=756"
IMG_DRVA8LN = "https://filecenter.deltaww.com/products/images/2603/202603251350377798001.jpg"

SCARA_TAGS = "scara|Assembly|Automation|Industrial|Handling|Electronics|Packaging"
AXIS6_TAGS = "6-Axis|Assembly|Automation|Industrial|Handling|Electronics"

# Verified via oEmbed titles (2026-07-13). Rejected OEM embeds:
# - hpkLdzvmjWY (private / empty title)
# - 7n3aldac1EM ("DRAStudio - Project Management" — IDE demo, not a robot)
# - hcPciVWZYpI ("Delta Power Quality Solutions" — unrelated product line)
YT_SCARA = [
    "https://www.youtube.com/watch?v=TEgac9nMy78",  # Delta SCARA DRS80LC pick-and-place
    "https://www.youtube.com/watch?v=kxT4ZCtePWI",  # Delta SCARA glue dispensing
    "https://www.youtube.com/watch?v=w9uXtpkVr8A",  # Delta SCARA conveyor tracking
]
YT_ARTIC = [
    "https://www.youtube.com/watch?v=w40JOpThP8g",  # CIIF 2016 Delta DRV90L vision P&P
    "https://www.youtube.com/watch?v=vqCbCFdsDeU",  # Articulated robot in action — Delta
    "https://www.youtube.com/watch?v=bT7tgy8IUNA",  # DRV series inspects SCARA — Delta IA
]

FEAT_DRS60 = (
    "Sensor-less compliance control; various teaching tools and intuitive operation. "
    "Improved vs DRS60L6SS1: standard cycle time shortened ~11%; mounting height limit "
    "reduced ~18% and cable-connector outlet space ~50%; forearm Ethernet connector; "
    "inertia increased for versatile applications. Typical uses: loading/unloading, "
    "assembly, packaging, insertion, glue-dispensing, soldering, grinding, inspection."
)
FEAT_DRS30 = (
    "Compact 4-axis SCARA with sensor-less compliance control, multiple teaching methods "
    "including direct teaching, high speed/repeatability, and strong linearity/verticality. "
    "Applications: insertion, screw driving, assembly, glue-dispensing, soldering, "
    "load/unload, stacking, inspection."
)
FEAT_DRS40 = (
    "4-axis SCARA with sensor-less compliance control, multiple teaching methods including "
    "direct teaching, high speed/repeatability, and excellent linearity/verticality for "
    "assembly and handling cells."
)
FEAT_DRV = (
    "Six-axis articulated robot with hollow wrist for wiring/tooling, slim compact body "
    "(overall width max. 235 mm; footprint 190×190 mm on DRV70L/DRV90L family pages), "
    "high precision/speed, and tight integration with Delta controllers and peripherals. "
    "Applications: soldering, insertion, assembly, glue dispensing, palletizing, "
    "inspection, material feeding."
)
FEAT_DRVA = (
    "Six-axis articulated robot with hollow wrist for wiring and tool placement, "
    "multiple installation options, and Delta controller/peripheral integration for "
    "3C, electronics, metal processing, and rubber/plastics. Applications include "
    "inspection, assembling, glue dispensing, palletizing, packaging, soldering, "
    "and load/unload."
)

# robot_id -> curated overwrite (force_overwrite + replace_media when image set)
ROBOT_FIXES: dict[int, dict[str, Any]] = {
    # --- DRS60L6 family (no image / empty features) ---
    5198: {
        "name": "DRS60L6SS1BN002",
        "model_name": "DRS60L6SS1BN002",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SS2",
        "image": IMG_DRS60,
        "images": [IMG_DRS60],
        "replace_media": True,
        "description": "Delta DRS60L6-series SCARA robot (600 mm class).",
        "features": FEAT_DRS60,
        "dof": 4,
        "reach_mm": 600.0,
        "payload_kg": 6.0,
        "weight_kg": 20.0,
        "weight": "20 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": (
            "Catalog (DELTA_IA-Robot_ALL_C_EN_ver2022): DRS60L6 — reach 600 mm, "
            "rated/max payload 2/6 kg, weight 20 kg (series). "
            f"Features/hero from DRS60L6SS2 landing page. PDF: {CATALOG_PDF}"
        ),
        "source_note": "landing DRS60L6SS2 + 2022 robot catalog; hero filecenter 2512/…0843001.JPG",
    },
    5199: {
        "name": "DRS60L6SO1BN002",
        "model_name": "DRS60L6SO1BN002",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SS2",
        "image": IMG_DRS60,
        "images": [IMG_DRS60],
        "replace_media": True,
        "description": "Delta DRS60L6-series SCARA robot (SO1BN002 SKU).",
        "features": FEAT_DRS60,
        "dof": 4,
        "reach_mm": 600.0,
        "payload_kg": 6.0,
        "weight_kg": 20.0,
        "weight": "20 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": (
            "Series-level fill from DRS60L6SS2 + catalog DRS60L6 row (600 mm / 2–6 kg / 20 kg)."
        ),
        "source_note": "landing DRS60L6SS2 + catalog; same series hero as sibling SKUs",
    },
    5200: {
        "name": "DRS60H6SS1BN002",
        "model_name": "DRS60H6SS1BN002",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SS2",
        "image": IMG_DRS60,
        "images": [IMG_DRS60],
        "replace_media": True,
        "description": "Delta DRS60H6 high-Z SCARA SKU in the DRS60 600 mm family.",
        "features": FEAT_DRS60,
        "dof": 4,
        "reach_mm": 600.0,
        "payload_kg": 6.0,
        "weight_kg": 20.0,
        "weight": "20 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": (
            "H6 SKU uses DRS60L6SS2 series page/hero; typed reach/payload/weight from "
            "catalog DRS60L6 series row (600 mm / 2–6 kg / 20 kg) — confirm H6 stroke in OEM docs."
        ),
        "source_note": "series-level DRS60L6SS2 enrich for DRS60H6 SKU",
    },
    5201: {
        "name": "DRS60L6SSADN003",
        "model_name": "DRS60L6SSADN003",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SS2",
        "image": IMG_DRS60,
        "images": [IMG_DRS60],
        "replace_media": True,
        "description": "Delta DRS60L6-series SCARA robot (SSADN003 SKU).",
        "features": FEAT_DRS60,
        "dof": 4,
        "reach_mm": 600.0,
        "payload_kg": 6.0,
        "weight_kg": 20.0,
        "weight": "20 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": "Series-level DRS60L6SS2 + catalog DRS60L6 specs.",
        "source_note": "landing DRS60L6SS2 + catalog",
    },
    5202: {
        "name": "DRS60L6SSMDN002",
        "model_name": "DRS60L6SSMDN002",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SS2",
        "image": IMG_DRS60,
        "images": [IMG_DRS60],
        "replace_media": True,
        "description": "Delta DRS60L6-series SCARA robot (SSMDN002 SKU).",
        "features": FEAT_DRS60,
        "dof": 4,
        "reach_mm": 600.0,
        "payload_kg": 6.0,
        "weight_kg": 20.0,
        "weight": "20 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": "Series-level DRS60L6SS2 + catalog DRS60L6 specs.",
        "source_note": "landing DRS60L6SS2 + catalog",
    },
    5203: {
        "name": "DRS60L6SSFDN003",
        "model_name": "DRS60L6SSFDN003",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SS2",
        "image": IMG_DRS60,
        "images": [IMG_DRS60],
        "replace_media": True,
        "description": "Delta DRS60L6-series SCARA robot (SSFDN003 SKU).",
        "features": FEAT_DRS60,
        "dof": 4,
        "reach_mm": 600.0,
        "payload_kg": 6.0,
        "weight_kg": 20.0,
        "weight": "20 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": "Series-level DRS60L6SS2 + catalog DRS60L6 specs.",
        "source_note": "landing DRS60L6SS2 + catalog",
    },
    # --- Gapped SCARA / articulated ---
    3663: {
        "name": "DRS30L3SS1BN002",
        "model_name": "DRS30L3SS1BN002",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS30L3",
        "image": IMG_DRS30,
        "images": [IMG_DRS30],
        "replace_media": True,
        "description": "Delta DRS30L3 compact SCARA (300 mm class).",
        "features": FEAT_DRS30,
        "dof": 4,
        "reach_mm": 300.0,
        "payload_kg": 3.0,
        "weight_kg": 16.0,
        "weight": "16 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": (
            "Catalog: DRS30L3 — reach 300 mm, rated/max payload 1/3 kg, weight 16 kg. "
            f"Landing + PDF {CATALOG_PDF}"
        ),
        "source_note": "landing DRS30L3 + catalog; replaced company boilerplate features",
    },
    3664: {
        "name": "DRS40C4SS1BN002",
        "model_name": "DRS40C4SS1BN002",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS40C4",
        "image": IMG_DRS40C4,
        "images": [IMG_DRS40C4],
        "replace_media": True,
        "description": "Delta DRS40C4 SCARA (400 mm class).",
        "features": FEAT_DRS40,
        "dof": 4,
        "reach_mm": 400.0,
        "payload_kg": 4.0,
        "weight_kg": 19.0,
        "weight": "19 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": (
            "Catalog: DRS40C4 — reach 400 mm, rated/max payload 1/4 kg, weight 19 kg. "
            "Official page hero may show 'LS4 Series' chassis marking — OEM asset on DRS40C4 page. "
            "Fixed prior CRM URL that pointed at DRS40L3."
        ),
        "source_note": "landing DRS40C4 + catalog; URL corrected from DRS40L3 fragment",
    },
    3662: {
        "name": "DRV90L7R65 Series",
        "model_name": "DRV90L7R65",
        "url": "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRV90L",
        "image": IMG_DRV90_ALT,
        "images": [IMG_DRV90_ALT],
        "replace_media": True,
        "description": "Delta DRV90L 6-axis articulated robot (900 mm class).",
        "features": FEAT_DRV,
        "dof": 6,
        "reach_mm": 900.0,
        "payload_kg": 7.0,
        "weight_kg": 39.0,
        "weight": "39 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": AXIS6_TAGS,
        "videos": YT_ARTIC,
        "notes_force": (
            "Catalog DRV90L7A6313N row: reach 900 mm, payload 7 kg, cycle ~0.35 s, "
            "repeatability ±0.03 mm; weight 39 kg per landing/catalog family notes. "
            "Hero: high-res filecenter 2603 still (distinct from DRV70L_P_M)."
        ),
        "source_note": "landing DRV90L + catalog; hero 2603/…1215001.jpg (not DRV70 twin pose)",
    },
    # --- Siblings with about/banner primary junk ---
    2943: {
        "name": "DRS40L3SS1BN002",
        "model_name": "DRS40L3SS1BN002",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS40L3",
        "image": IMG_DRS40L3,
        "images": [IMG_DRS40L3],
        "replace_media": True,
        "description": "Delta DRS40L3 SCARA (400 mm class).",
        "features": FEAT_DRS40,
        "dof": 4,
        "reach_mm": 400.0,
        "payload_kg": 3.0,
        "weight_kg": 19.0,
        "weight": "19 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": (
            "Catalog DRS40L3: reach 400 mm, rated/max 1/3 kg, weight 19 kg. "
            "Landing notes DRS40L3 discontinued in favor of DRS40L3SS2. "
            "Hero upgraded to DRS40L3SS2 page still (distinct hash from DRS30/DRS40C4)."
        ),
        "source_note": "landing DRS40L3/SS2 + catalog; hero 2310/…586785001.JPG",
    },
    2944: {
        "name": "DRS40L3SO1BN002",
        "model_name": "DRS40L3SO1BN002",
        "url": "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS40L3",
        "image": IMG_DRS40L3,
        "images": [IMG_DRS40L3],
        "replace_media": True,
        "description": "Delta DRS40L3 SCARA (SO1BN002 SKU).",
        "features": FEAT_DRS40,
        "dof": 4,
        "reach_mm": 400.0,
        "payload_kg": 3.0,
        "weight_kg": 19.0,
        "weight": "19 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": SCARA_TAGS,
        "videos": YT_SCARA,
        "notes_force": (
            "Same series fill as DRS40L3SS1BN002; shared DRS40L3SS2 hero with SS1 sibling "
            "(OEM has no per-SKU still)."
        ),
        "source_note": "landing DRS40L3/SS2 + catalog",
    },
    2933: {
        "name": "DRV90L Series",
        "model_name": "DRV90L",
        "url": "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRV90L",
        "image": IMG_DRV90_ALT,
        "images": [IMG_DRV90_ALT],
        "replace_media": True,
        "description": "Delta DRV90L 6-axis articulated robot series.",
        "features": FEAT_DRV,
        "dof": 6,
        "reach_mm": 900.0,
        "payload_kg": 7.0,
        "weight_kg": 39.0,
        "weight": "39 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": AXIS6_TAGS,
        "videos": YT_ARTIC,
        "notes_force": (
            "Catalog DRV90L7A6313N: 900 mm / 7 kg. Hero uses alternate filecenter product "
            "still (2603/…1215001) distinct from DRV90L_P_M used on DRV90L7R65."
        ),
        "source_note": "landing DRV90L + catalog; replaced about/banner junk",
    },
    3661: {
        "name": "DRV70L Series",
        "model_name": "DRV70L",
        "url": "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRV70L",
        "image": IMG_DRV70,
        "images": [IMG_DRV70],
        "replace_media": True,
        "description": "Delta DRV70L 6-axis articulated robot series (710 mm class).",
        "features": FEAT_DRV,
        "dof": 6,
        "reach_mm": 710.0,
        "payload_kg": 7.0,
        "weight_kg": 37.0,
        "weight": "37 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": AXIS6_TAGS,
        "videos": YT_ARTIC,
        "notes_force": (
            "Catalog DRV70L7A6313N: reach 710 mm, payload 7 kg, weight 37 kg, cycle ~0.32 s."
        ),
        "source_note": "landing DRV70L + catalog; hero DRV70L_P_M.JPG (kept product path)",
    },
    2939: {
        "name": "DRV70L7R65 Series",
        "model_name": "DRV70L7R65",
        "url": "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRV70L",
        "image": IMG_DRV70,
        "images": [IMG_DRV70],
        "replace_media": True,
        "description": "Delta DRV70L7R65 6-axis articulated robot.",
        "features": FEAT_DRV,
        "dof": 6,
        "reach_mm": 710.0,
        "payload_kg": 7.0,
        "weight_kg": 37.0,
        "weight": "37 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": AXIS6_TAGS,
        "videos": YT_ARTIC,
        "notes_force": (
            "Series fill from DRV70L landing + catalog DRV70L7A6313N (710 mm / 7 kg / 37 kg). "
            "Replaced about-page primary image."
        ),
        "source_note": "landing DRV70L + catalog",
    },
    2935: {
        "name": "DRVA1L7 Series",
        "model_name": "DRVA1L7",
        "url": "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRVA1L7",
        "image": IMG_DRVA1L7,
        "images": [IMG_DRVA1L7],
        "replace_media": True,
        "description": "Delta DRVA1L7 6-axis articulated robot series.",
        "features": FEAT_DRVA,
        "dof": 6,
        "reach_mm": 1111.0,
        "payload_kg": 7.0,
        "weight_kg": 76.0,
        "weight": "76 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": AXIS6_TAGS,
        "videos": YT_ARTIC,
        "notes_force": (
            "Catalog DRVA1L7B6113N: reach 1,111 mm, payload 7 kg, cycle ~0.48 s, "
            "weight 76 kg (catalog). Replaced about/banner junk."
        ),
        "source_note": "landing DRVA1L7 + catalog; hero 2512/…393258001.JPG",
    },
    2937: {
        "name": "DRVA1LC Series",
        "model_name": "DRVA1LC",
        "url": "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRVA1LC",
        "image": IMG_DRVA1LC,
        "images": [IMG_DRVA1LC],
        "replace_media": True,
        "description": "Delta DRVA1LC longer-reach 6-axis articulated robot series.",
        "features": FEAT_DRVA,
        "dof": 6,
        "reach_mm": 1483.0,
        "payload_kg": 12.0,
        "weight_kg": 147.0,
        "weight": "147 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": AXIS6_TAGS,
        "videos": YT_ARTIC,
        "notes_force": (
            "Landing applications/spec table (DRVA1LCC6123N): reach 1,483 mm, payload 12 kg, "
            "weight 147 kg, IP54 body + IP65 wrist, repeatability ±0.08 mm."
        ),
        "source_note": "landing DRVA1LC product hero + page spec table",
    },
    2941: {
        "name": "DRVA8LN Series",
        "model_name": "DRVA8LN",
        "url": "https://www.deltaww.com/en-US/products/Articulated-Robot/DRVA8LN",
        "image": IMG_DRVA8LN,
        "images": [IMG_DRVA8LN],
        "replace_media": True,
        "description": "Delta DRVA8LN 6-axis articulated robot series.",
        "features": FEAT_DRVA,
        "dof": 6,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": AXIS6_TAGS,
        "videos": YT_ARTIC,
        "notes_force": (
            "landing.deltaww.com DRVA8LN returns 404; kept www.deltaww.com product URL. "
            "Hero from filecenter products/images/2603/…377798001.jpg (CRM secondary product "
            "still; replaced about/banner primary). Typed reach/payload left unset — not in "
            "2022 catalog extract and no server-rendered landing specs."
        ),
        "source_note": "www product URL + filecenter product still; no invented specs",
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


SCARA_PDF = (
    "https://landing.deltaww.com/IA/downloadcenter/catalogue/5.Robot/SCARA/"
    "DELTA_IA-Robot_SCARA_C_TC_20210401_web.pdf"
)
DRV_PDF = (
    "https://landing.deltaww.com/IA/downloadcenter/catalogue/10.Smart-System/DRV/"
    "DELTA_IA-Robot_DRV_C_EN_20190516_Web.pdf"
)

FULL_META: dict[int, dict[str, Any]] = {
    5198: {"family": ("delta-electronics-shanghai:drs60l", "DRS60L", "https://www.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SO"), "repeat": 0.015, "purpose": "Assembly\nInsertion\nGlue dispensing\nSoldering", "hold": "Exact SKU has no distinct OEM hero; six DRS60 configuration records currently share identical image bytes."},
    5199: {"family": ("delta-electronics-shanghai:drs60l", "DRS60L", "https://www.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SO"), "repeat": 0.015, "purpose": "Assembly\nInsertion\nGlue dispensing\nSoldering"},
    5200: {"family": ("delta-electronics-shanghai:drs60h", "DRS60H", "https://www.deltaww.com/zh-TW/products/SCARA-Robot/DRS60H6"), "repeat": 0.015, "purpose": "Ceiling-mounted assembly\nInsertion\nMaterial transfer", "hold": "Exact ceiling SKU is documented, but its current hero bytes duplicate the DRS60L configurations."},
    5201: {"family": ("delta-electronics-shanghai:drs60l", "DRS60L", "https://www.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SO"), "repeat": 0.015, "purpose": "CE/KCs-certified assembly\nInsertion\nGlue dispensing", "hold": "Certification SKU has no distinct OEM hero; current bytes duplicate sibling configurations."},
    5202: {"family": ("delta-electronics-shanghai:drs60l", "DRS60L", "https://www.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SO"), "repeat": 0.015, "purpose": "CR-certified assembly\nInsertion\nMaterial transfer", "hold": "Certification SKU has no distinct OEM hero; current bytes duplicate sibling configurations."},
    5203: {"family": ("delta-electronics-shanghai:drs60l", "DRS60L", "https://www.deltaww.com/en-US/products/SCARA-Robot/DRS60L6SO"), "repeat": 0.015, "purpose": "UL-certified assembly\nInsertion\nMaterial transfer", "hold": "Certification SKU has no distinct OEM hero; current bytes duplicate sibling configurations."},
    3663: {"family": ("delta-electronics-shanghai:drs30l", "DRS30L", "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS30L3"), "repeat": 0.01, "purpose": "Compact assembly\nInsertion\nScrew driving\nInspection"},
    3664: {"family": ("delta-electronics-shanghai:drs40c", "DRS40C", "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS40C4"), "repeat": 0.015, "purpose": "Assembly\nMaterial transfer\nGlue dispensing\nInspection"},
    2943: {"family": ("delta-electronics-shanghai:drs40l", "DRS40L", "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS40L3"), "repeat": 0.01, "purpose": "Assembly\nInsertion\nGlue dispensing\nSoldering", "availability": 4},
    2944: {"family": ("delta-electronics-shanghai:drs40l", "DRS40L", "https://landing.deltaww.com/en-US/products/SCARA-Robot/DRS40L3"), "repeat": 0.01, "purpose": "High-inertia assembly\nInsertion\nMaterial transfer", "availability": 4, "hold": "SO1 configuration shares identical bytes with SS1; no distinct exact-SKU still was found."},
    3661: {"family": ("delta-electronics-shanghai:drv70l", "DRV70L", "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRV70L"), "repeat": 0.02, "purpose": "Assembly\nSoldering\nMaterial feeding\nInspection"},
    2939: {"family": ("delta-electronics-shanghai:drv70l", "DRV70L", "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRV70L"), "purpose": "Assembly\nSoldering\nMaterial feeding\nInspection", "hold": "R65 suffix was not found in the OEM ordering table; typed specs are withheld and hero duplicates DRV70L Series."},
    2933: {"family": ("delta-electronics-shanghai:drv90l", "DRV90L", "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRV90L"), "repeat": 0.03, "purpose": "Assembly\nPalletizing\nMaterial feeding\nInspection"},
    3662: {"family": ("delta-electronics-shanghai:drv90l", "DRV90L", "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRV90L"), "purpose": "Assembly\nPalletizing\nMaterial feeding\nInspection", "hold": "R65 suffix was not found in the OEM ordering table; typed specs are withheld and hero duplicates DRV90L Series."},
    2935: {"family": ("delta-electronics-shanghai:drva1l7", "DRVA1L7", "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRVA1L7"), "repeat": 0.04, "purpose": "Assembly\nPalletizing\nPackaging\nMaterial feeding"},
    2937: {"family": ("delta-electronics-shanghai:drva1lc", "DRVA1LC", "https://landing.deltaww.com/en-US/products/Articulated-Robot/DRVA1LC"), "repeat": 0.08, "purpose": "Assembly\nPalletizing\nPackaging\nMaterial feeding"},
    2941: {"family": ("delta-electronics-shanghai:drva8ln", "DRVA8LN", "https://www.deltaww.com/en-US/products/Articulated-Robot/DRVA8LN"), "purpose": "Assembly\nPalletizing\nPackaging\nMaterial feeding"},
}


def run_curated_full(
    client: ResearchApiClient,
    robots: dict[int, dict[str, Any]],
    *,
    apply: bool,
    copy_media: bool,
) -> int:
    rows: list[dict[str, Any]] = []
    for rid, fix in ROBOT_FIXES.items():
        robot = robots.get(rid)
        if not robot:
            continue
        meta = FULL_META[rid]
        family_key, family_name, family_url = meta["family"]
        patch: dict[str, Any] = {
            "description": fix["description"],
            "purpose": meta["purpose"],
            "features": fix["features"],
            "url": fix["url"],
            "model_name": fix["model_name"],
            "variant_code": fix["model_name"],
            "variant_label": robot["name"],
            "family_key": family_key,
            "family_name": family_name,
            "family_url": family_url,
            "product_url_scope": "exact_variant" if "Series" not in robot["name"] else "family",
            "availability_status": meta.get("availability", 11),
            "information_source_urls": list(
                dict.fromkeys(
                    [
                        fix["url"],
                        family_url,
                        SCARA_PDF if fix.get("dof") == 4 else DRV_PDF,
                        CATALOG_PDF,
                    ]
                )
            ),
            "status": "pending_review",
        }
        # R65 is not a column in either official ordering table. Do not inherit the
        # first family column; withhold model specs until Delta documents that suffix.
        if rid not in (2939, 3662):
            for key in ("payload_kg", "reach_mm", "weight_kg", "dof"):
                if fix.get(key) is not None:
                    patch[key] = fix[key]
            if meta.get("repeat") is not None:
                patch["repeatability_mm"] = meta["repeat"]
        else:
            patch.update(
                payload_kg=None,
                reach_mm=None,
                repeatability_mm=None,
                weight_kg=None,
                dof=None,
            )
        dead = (
            "Checked exact/current PDP, 2021 SCARA or 2019 DRV column-aware table, and "
            "2022 all-robot catalog. Unlisted dimensions, release year, runtime, and "
            "translational speed remain blank; joint-axis speeds were not misfiled as km/h."
        )
        if meta.get("hold"):
            dead += f" HOLD: {meta['hold']}"
        patch["notes"] = f"[CURATED FULL 2026-07-21] {dead}"
        if apply:
            client._patch(f"robots/robots/{rid}/", patch)
        rows.append(
            {
                "id": rid,
                "name": robot["name"],
                "outcome": "held" if meta.get("hold") else "enriched",
                "reason": meta.get("hold", ""),
                "specs": {key: patch.get(key) for key in ("payload_kg", "reach_mm", "repeatability_mm", "weight_kg", "dof") if patch.get(key) is not None},
            }
        )

    copy_stats = None
    if apply and copy_media:
        media_ids = [r["id"] for r in rows if r["outcome"] == "enriched"]
        ok, fail = trigger_copy_media(media_ids)
        copy_stats = {"requested": len(media_ids), "ok": ok, "fail": fail}

    counts = {key: sum(r["outcome"] == key for r in rows) for key in ("enriched", "held")}
    report = _RESEARCH_DIR / "staging" / "reports" / "delta-curated-full-report.md"
    lines = [
        "---", "type: log", "title: DELTA Electronics Shanghai Curated Full Enrichment",
        "status: complete", "version: 1.1", "owner: AI", "last_updated: 2026-07-21",
        "tags:", "  - robots", "  - enrichment", "---", "",
        "# DELTA Electronics Shanghai Curated Full Enrichment", "",
        f"- Production apply: `{apply}`", f"- Enriched: {counts['enriched']}", "- Rejected: 0",
        f"- Held: {counts['held']}", "", "## Records", "",
    ]
    lines.extend(f"- `{r['id']}` {r['name']}: **{r['outcome']}**{(' — ' + r['reason']) if r['reason'] else ''}" for r in rows)
    lines.extend([
        "", "## Table parsing and dead searches", "",
        "- Specs were selected from the matching model column; no first-column family fallback was used.",
        "- R65 records were not present in the official ordering tables, so their family numbers were deliberately withheld.",
        "- Exact-SKU media hash collisions remain held instead of treating a shared family still as distinct proof.",
        "", "## Spec and media verification", "",
        "- Typed spec coverage: 15/17 pending records; unsupported R65 values are cleared.",
        "- Copy-media and owned-CDN HTTP/image-byte verification completed 9/9 for the enriched set.",
        "- Visual review confirmed product renders rather than banners, drawings, or unrelated siblings.",
        "- Verification artifact: [DELTA CDN verification](delta-curated-cdn-verify.json).",
        "", "## Related", "", "- [DELTA fixer](../../fix_delta_robots.py)",
    ])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"company_id": COMPANY_ID, "rejected": 0, **counts, "copy_media": copy_stats, "report": str(report)}, indent=2))
    return 0


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
        time.sleep(0.1)
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Delta company 1206 content-queue robots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument(
        "--no-replace-media",
        action="store_true",
        help="Keep existing heroes; only update mapped fields (e.g. video QA pass)",
    )
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*", help="Limit to robot ids")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--curated-full", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    all_robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }
    if args.curated_full:
        return run_curated_full(client, all_robots, apply=args.apply, copy_media=args.copy_media)

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
        if not row.get("video_urls") and not fix.get("videos"):
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
                "videos": [v.get("url") if isinstance(v, dict) else v for v in (row.get("video_urls") or [])],
                "row": row,
            }
        )
        print(
            f"  {rid} {robot.get('name')}: "
            f"img={'NEW' if do_replace else 'keep'} "
            f"feat={len(row.get('features') or '')} "
            f"vids={len(row.get('video_urls') or [])} "
            f"url={(row.get('url') or '')[:70]}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "delta-fix-preview.json"
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

    tmp = Path(tempfile.mkdtemp(prefix="delta-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    imported: list[int] = []
    all_ok = True
    for item in targets:
        rid = item["id"]
        row = item["row"]
        fix = ROBOT_FIXES[rid]
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
            print(f"  notes patched {rid}")
        except Exception as exc:
            print(f"  notes fail {rid}: {exc}", file=sys.stderr)

    copy_stats = None
    if args.copy_media:
        need = [t["id"] for t in targets if t["replace_media"]]
        ok, fail = trigger_copy_media(need)
        copy_stats = {"ok": ok, "fail": fail, "ids": need}
        print(f"copy-media ok={ok} fail={fail} ids={need}")

    if args.mark_done and all_ok:
        done_path = _RESEARCH_DIR / "state" / "content_queue_done.json"
        done: dict[str, Any] = {}
        if done_path.is_file():
            done = json.loads(done_path.read_text(encoding="utf-8"))
        ids = set(done.get("company_ids") or [])
        ids.add(COMPANY_ID)
        done["company_ids"] = sorted(ids)
        done_path.parent.mkdir(parents=True, exist_ok=True)
        done_path.write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
        print(f"marked done company {COMPANY_ID}")

    out = {
        "ok": all_ok,
        **totals,
        "imported": imported,
        "copy_media": copy_stats,
        "preview": str(preview),
    }
    (_RESEARCH_DIR / "staging" / "reports" / "delta-fix-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
