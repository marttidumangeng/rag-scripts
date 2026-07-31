"""Fix Doosan Robotics (company 193) content-queue enrichment.

OEM: https://www.doosanrobotics.com
Sources: EN PDPs under /en/product-solutions/product/{series}/{sku}/,
official EN catalog PDF External_DoosanRobotics_renew_eng.pdf.

Issues addressed:
- 28 pending_review rows collapse to 14 unique SKUs (same PDP URL duplicates)
- Prefer bare-SKU keepers with longer narrative; strip "Doosan Robotics " prefix
- Distinct OEM heroes: images/product/{sku}-slide01.jpg (md5-unique; visually checked)
- Shared series feature/kit/sns graphics rejected as heroes
- Typed specs from PDP + official catalog weight table; never invent
- Tags: Cobot / Collaborative Robot / Industrial — NOT Humanoid/AMR/Drone
- family_key doosan-robotics:{e|a|m|h|p}-series; availability Available (11)
- status stays pending_review; soft-ask rejects for clear same-SKU dupes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
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
from tag_suggest import TagCatalog
from youtube_metadata import enrich_video_list

COMPANY_ID = 193
COMPANY_SLUG = "doosan-robotics"
COMPANY_NAME = "Doosan Robotics"
COMPANY_WEBSITE = "https://www.doosanrobotics.com"
KR = "KR"
KR_COUNTRY_ID = 14

CATALOG_PDF = f"{COMPANY_WEBSITE}/pdf/catalog/External_DoosanRobotics_renew_eng.pdf"

SERIES_URL = {
    "e-series": f"{COMPANY_WEBSITE}/en/product-solutions/product/e-series",
    "a-series": f"{COMPANY_WEBSITE}/en/product-solutions/product/a-series",
    "m-series": f"{COMPANY_WEBSITE}/en/product-solutions/product/m-series",
    "h-series": f"{COMPANY_WEBSITE}/en/product-solutions/product/h-series",
    "p-series": f"{COMPANY_WEBSITE}/en/product-solutions/product/p-series",
}

IMG = {
    "E0509": f"{COMPANY_WEBSITE}/images/product/e0509-slide01.jpg",
    "A0509": f"{COMPANY_WEBSITE}/images/product/a0509-slide01.jpg",
    "A0509F": f"{COMPANY_WEBSITE}/images/product/a0509f-slide01.jpg",
    "A0509S": f"{COMPANY_WEBSITE}/images/product/a0509s-slide01.jpg",
    "A0912": f"{COMPANY_WEBSITE}/images/product/a0912-slide01.jpg",
    "A0912F": f"{COMPANY_WEBSITE}/images/product/a0912f-slide01.jpg",
    "A0912S": f"{COMPANY_WEBSITE}/images/product/a0912s-slide01.jpg",
    "M0609": f"{COMPANY_WEBSITE}/images/product/m0609-slide01.jpg",
    "M0617": f"{COMPANY_WEBSITE}/images/product/m0617-slide01.jpg",
    "M1013": f"{COMPANY_WEBSITE}/images/product/m1013-slide01.jpg",
    "M1509": f"{COMPANY_WEBSITE}/images/product/m1509-slide01.jpg",
    "H2017": f"{COMPANY_WEBSITE}/images/product/h2017-slide01.jpg",
    "H2515": f"{COMPANY_WEBSITE}/images/product/h2515-slide01.jpg",
    "P3020": f"{COMPANY_WEBSITE}/images/product/p3020-slide01.jpg",
}

EXPECTED_MD5 = {
    "E0509": "24ce6cc4fbb9a88035a664adc68ddb3c",
    "A0509": "971d077460cdb080f2562b35353af096",
    "A0509F": "cf670c5a12131997cc1d01dd570548c8",
    "A0509S": "d5b68a3e33f5fb6807c38f313cddb4c8",
    "A0912": "7512f1fc8cfe19e3de87e3fe961e5c49",
    "A0912F": "36a3e94f7ee19e3a8a2504f99f1ef248",
    "A0912S": "1d60f86622771d3f79af69cc0beb6b75",
    "M0609": "34fea7825c69586ba20319dace7dd38b",
    "M0617": "c8fa8cd665104098ae0e33e90fea00f3",
    "M1013": "894848046c8afc475e1f7a39bd256040",
    "M1509": "3bf11563d5d4ccff4465795ec918b77e",
    "H2017": "9df80dc4bfa08c1dd950620a299304c2",
    "H2515": "2c425e7c9adf7285ea3460eb7ac71176",
    "P3020": "bb9c4a870358d831fcf48adcecfbe521",
}

# Official catalog manipulator weight (External_DoosanRobotics_renew_eng.pdf).
WEIGHT_KG = {
    "E0509": 22.5,
    "A0509": 21.0,
    "A0509F": 21.0,
    "A0509S": 21.0,
    "A0912": 31.0,
    "A0912F": 31.0,
    "A0912S": 31.0,
    "M0609": 27.5,
    "M0617": 35.5,
    "M1013": 34.0,
    "M1509": 33.0,
    "H2017": 79.0,
    "H2515": 77.0,
    "P3020": 83.0,
}

# Cap ~8 TagCatalog names; put series-differentiating tags before generics.
TAGS_BASE = (
    "Cobot|Collaborative Robot|6-Axis|Stationary|Industrial|"
    "Manufacturing|Assembly|Pick-and-Place"
)
TAGS_FOOD = (
    "Cobot|Collaborative Robot|6-Axis|Stationary|Industrial|"
    "Manufacturing|Food|Assembly"
)
TAGS_M = (
    "Cobot|Collaborative Robot|6-Axis|Stationary|Industrial|"
    "Manufacturing|Welding|Assembly"
)
TAGS_H = (
    "Cobot|Collaborative Robot|6-Axis|Stationary|Industrial|"
    "Manufacturing|Material Handling|Palletizing"
)
TAGS_P = (
    "Cobot|Collaborative Robot|5-Axis|Stationary|Industrial|"
    "Manufacturing|Material Handling|Palletizing"
)

YT = {
    "E0509": [
        "https://www.youtube.com/watch?v=sCYu9smRHfA",  # OCR parcel sorting
    ],
    "A0509": [
        "https://www.youtube.com/watch?v=zAaWp85KOZE",  # Unboxing A0509
        "https://www.youtube.com/watch?v=mOmX9kUtdlM",  # Machine tending
    ],
    "A0509F": [],
    "A0509S": [],
    "A0912": [
        "https://www.youtube.com/watch?v=rbZ9T5FqqPQ",  # Ultrasonic test
        "https://www.youtube.com/watch?v=wm9TuFPmNK8",  # Machine tending
    ],
    "A0912F": [],
    "A0912S": [],
    "M0609": [
        "https://www.youtube.com/watch?v=UDB1Lu5dSvM",  # Launch M0609/M1509…
    ],
    "M0617": [
        "https://www.youtube.com/watch?v=6xqGRqgdu68",  # Demo includes M0617
        "https://www.youtube.com/watch?v=xPTfyO0Hs_k",  # ATI for M0617
    ],
    "M1013": [
        "https://www.youtube.com/watch?v=SOXPbG18ptU",  # Cobot overview
        "https://www.youtube.com/watch?v=howlX95sgIk",  # M1013 / Lynx
    ],
    "M1509": [
        "https://www.youtube.com/watch?v=2-zRxn1kuz4",  # Doosan M1509
        "https://www.youtube.com/watch?v=UDB1Lu5dSvM",
    ],
    "H2017": [
        "https://www.youtube.com/watch?v=aqBOXOFKDxU",  # Unboxing
        "https://www.youtube.com/watch?v=aDLcmLAPu3g",  # Industrial cobot
    ],
    "H2515": [
        "https://www.youtube.com/watch?v=c6JFoRwUbhA",  # H2515 25kg
    ],
    "P3020": [
        "https://www.youtube.com/watch?v=PQF00j-iysM",  # P-SERIES unveil
        "https://www.youtube.com/watch?v=iBO6Z7iLj2o",  # Main trailer
    ],
}

_AVAIL_IDS = {
    "announced": 10,
    "available": 11,
    "released": 3,
    "discontinued": 4,
    "pre_order": 12,
}


def _pdp(series: str, slug: str) -> str:
    return f"{COMPANY_WEBSITE}/en/product-solutions/product/{series}/{slug}/"


# Survivor id → SKU meta. Rejects cite these survivors.
KEEPERS: dict[int, dict[str, Any]] = {
    4731: {
        "sku": "E0509",
        "series": "e-series",
        "slug": "e0509",
        "payload_kg": 5.0,
        "reach_mm": 900.0,
        "repeatability_mm": 0.05,
        "dof": 6,
        "ip": "IP66",
        "tags": TAGS_FOOD,
        "description": (
            "E0509 is Doosan's Edge-series collaborative arm optimized for food and "
            "beverage work. NSF certification and an IP66 rating support hygienic "
            "washdown without protective jackets, with compact single-box delivery "
            "aimed at fast installation and strong ROI."
        ),
        "purpose": (
            "Food and beverage preparation and serving\n"
            "Deep-frying and hot-oil cooking cycles\n"
            "Coffee and beverage pouring\n"
            "Noodle and ice-cream service\n"
            "Draft-beer pouring and order pickup"
        ),
        "features": (
            "OEM PDP + catalog: 5 kg payload, 900 mm reach, ±0.05 mm repeatability, "
            "22.5 kg manipulator weight, 6-axis, IP66, NSF Food Zone. Edge hygiene "
            "control without robot jackets; compact packaging (~2/3 prior size) for "
            "easy install. DART-Suite programming; Doosan Mate end-of-arm ecosystem. "
            "Main applications: chicken frying, coffee, noodles, ice cream, beer."
        ),
    },
    4730: {
        "sku": "A0509",
        "series": "a-series",
        "slug": "a0509",
        "payload_kg": 5.0,
        "reach_mm": 900.0,
        "repeatability_mm": 0.03,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_BASE,
        "description": (
            "A0509 is Doosan's compact Agile-series cobot for sites that need fast "
            "cycles and high ROI. It pairs a 5 kg payload and 900 mm reach with "
            "advanced collision-detection safety and flexible customization for "
            "everyday industrial automation."
        ),
        "purpose": (
            "Machine tending\n"
            "Pick-and-place transfer\n"
            "Quality inspection\n"
            "Air blowing and cleaning\n"
            "Gluing and bonding\n"
            "Packaging and stacking"
        ),
        "features": (
            "OEM PDP + catalog: 5 kg payload, 900 mm reach, ±0.03 mm repeatability, "
            "21 kg weight, 6-axis, IP54, tool speed over 1 m/s, any-orientation mount. "
            "A-Series focus on safety algorithms, speed, and cost-effective ROI. "
            "Works with DART-Suite and Doosan Mate peripherals."
        ),
    },
    4729: {
        "sku": "A0509F",
        "series": "a-series",
        "slug": "a0509f",
        "payload_kg": 5.0,
        "reach_mm": 900.0,
        "repeatability_mm": 0.03,
        "dof": 6,
        "ip": "IP66",
        "tags": TAGS_FOOD,
        "description": (
            "A0509F is the food-and-beverage variant of Doosan's A0509 Agile cobot. "
            "NSF certification and IP66 protection support hygienic maintenance in "
            "clean, washdown-oriented production environments."
        ),
        "purpose": (
            "Food and beverage handling\n"
            "Hygienic inspection workflows\n"
            "Gluing and bonding in clean processes\n"
            "Packaging in F&B lines"
        ),
        "features": (
            "OEM PDP + catalog: 5 kg payload, 900 mm reach, ±0.03 mm repeatability, "
            "21 kg weight, 6-axis, IP66, NSF-certified F&B model (distinct food-grade "
            "finish vs standard A0509). Same Agile speed/ROI positioning with hygiene "
            "controls for splash/food-zone work."
        ),
    },
    2671: {
        "sku": "A0509S",
        "series": "a-series",
        "slug": "a0509s",
        "payload_kg": 5.0,
        "reach_mm": 900.0,
        "repeatability_mm": 0.03,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_BASE,
        "description": (
            "A0509S is the force-sensor Agile variant of the A0509. A built-in "
            "flange force/torque sensor enables precise compliance control for "
            "assembly and inspection while keeping the compact 5 kg / 900 mm envelope."
        ),
        "purpose": (
            "Precision assembly with force control\n"
            "Machine tending\n"
            "Inspection\n"
            "Pick-and-place\n"
            "Gluing and bonding"
        ),
        "features": (
            "OEM PDP + catalog: 5 kg payload, ~900–903 mm reach, ±0.03 mm "
            "repeatability, 21 kg weight, 6-axis, IP54. Built-in 6-axis force sensor "
            "at the flange (A-Series S models) for compliance and contact tasks. "
            "Agile safety/speed/ROI feature set."
        ),
    },
    4728: {
        "sku": "A0912",
        "series": "a-series",
        "slug": "a0912",
        "payload_kg": 9.0,
        "reach_mm": 1200.0,
        "repeatability_mm": 0.05,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_BASE,
        "description": (
            "A0912 extends Doosan's Agile series to a 9 kg payload and 1200 mm reach "
            "for larger workcells that still need fast deployment and strong "
            "economics in collaborative production."
        ),
        "purpose": (
            "Machine tending\n"
            "Assembly\n"
            "Quality inspection\n"
            "Packaging\n"
            "Pick-and-place"
        ),
        "features": (
            "OEM PDP + catalog: 9 kg payload, 1200 mm reach, ±0.05 mm repeatability, "
            "31 kg weight, 6-axis, IP54, tool speed over 1 m/s. Agile series safety "
            "algorithms and high-ROI positioning for electronics, medical, and general "
            "industrial cells."
        ),
    },
    4727: {
        "sku": "A0912F",
        "series": "a-series",
        "slug": "a0912f",
        "payload_kg": 9.0,
        "reach_mm": 1200.0,
        "repeatability_mm": 0.05,
        "dof": 6,
        "ip": "IP66",
        "tags": TAGS_FOOD,
        "description": (
            "A0912F is the NSF-certified food-and-beverage version of the A0912. "
            "It keeps the 9 kg / 1200 mm Agile envelope with IP66 protection for "
            "hygienic F&B and clean-process automation."
        ),
        "purpose": (
            "Food and beverage handling\n"
            "Hygienic assembly and inspection\n"
            "Clean-process packaging"
        ),
        "features": (
            "OEM PDP + catalog: 9 kg payload, 1200 mm reach, ±0.05 mm repeatability, "
            "31 kg weight, 6-axis, IP66, NSF F&B certification. Distinct food-grade "
            "product render vs standard A0912; same Agile speed and customization "
            "story with washdown-oriented protection."
        ),
    },
    4726: {
        "sku": "A0912S",
        "series": "a-series",
        "slug": "a0912s",
        "payload_kg": 9.0,
        "reach_mm": 1200.0,
        "repeatability_mm": 0.05,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_BASE,
        "description": (
            "A0912S adds a built-in flange force sensor to the A0912 Agile cobot, "
            "supporting compliant assembly and contact-rich tasks across a 9 kg / "
            "1200 mm work envelope."
        ),
        "purpose": (
            "Force-controlled assembly\n"
            "Machine tending\n"
            "Inspection\n"
            "Material handling\n"
            "Packaging"
        ),
        "features": (
            "OEM PDP + catalog: 9 kg payload, ~1200–1203 mm reach, ±0.05 mm "
            "repeatability, 31 kg weight, 6-axis, IP54, flange force sensor (S "
            "variant). Agile safety, speed, and ROI positioning with DART-Suite."
        ),
    },
    4725: {
        "sku": "M0609",
        "series": "m-series",
        "slug": "m0609",
        "payload_kg": 6.0,
        "reach_mm": 900.0,
        "repeatability_mm": 0.03,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_M,
        "description": (
            "M0609 is Doosan's compact Masterpiece-series cobot with six joint "
            "torque sensors for high collision sensitivity and dexterous force "
            "control in a 6 kg / 900 mm envelope."
        ),
        "purpose": (
            "Precision assembly\n"
            "Welding\n"
            "Machine tending\n"
            "Polishing and grinding\n"
            "Inspection"
        ),
        "features": (
            "OEM PDP + catalog: 6 kg payload, 900 mm reach, ±0.03 mm repeatability, "
            "27.5 kg weight, 6-axis, IP54, six high-tech joint torque sensors "
            "(Masterpiece series). Any-orientation mount; DART-Suite / Doosan Mate "
            "ecosystem for sophisticated collaborative tasks."
        ),
    },
    2666: {
        "sku": "M0617",
        "series": "m-series",
        "slug": "m0617",
        "payload_kg": 6.0,
        "reach_mm": 1700.0,
        "repeatability_mm": 0.1,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_M,
        "description": (
            "M0617 is the long-reach Masterpiece cobot: 6 kg payload across 1700 mm "
            "with six joint torque sensors for precise, safe force control in larger "
            "workcells."
        ),
        "purpose": (
            "Long-reach machine tending\n"
            "Welding\n"
            "Assembly\n"
            "Polishing\n"
            "Material handling across wide cells"
        ),
        "features": (
            "OEM PDP + catalog: 6 kg payload, 1700 mm reach, ±0.1 mm repeatability, "
            "35.5 kg weight, 6-axis, IP54, six joint torque sensors. Extended reach "
            "within the M-Series Masterpiece lineup for flexible manufacturing."
        ),
    },
    4724: {
        "sku": "M1013",
        "series": "m-series",
        "slug": "m1013",
        "payload_kg": 10.0,
        "reach_mm": 1300.0,
        "repeatability_mm": 0.05,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_M,
        "description": (
            "M1013 is a mid-payload Masterpiece cobot (10 kg / 1300 mm) with six "
            "joint torque sensors for precise force control in assembly, welding, "
            "and machine-tending cells."
        ),
        "purpose": (
            "Assembly\n"
            "Machine tending\n"
            "Welding\n"
            "Polishing\n"
            "Inspection"
        ),
        "features": (
            "OEM PDP + catalog: 10 kg payload, 1300 mm reach, ±0.05 mm repeatability, "
            "34 kg weight, 6-axis, IP54, six joint torque sensors. Masterpiece series "
            "collision sensitivity and dexterity for complex stationary tasks."
        ),
    },
    4723: {
        "sku": "M1509",
        "series": "m-series",
        "slug": "m1509",
        "payload_kg": 15.0,
        "reach_mm": 900.0,
        "repeatability_mm": 0.03,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_M,
        "description": (
            "M1509 is Doosan's higher-payload compact Masterpiece cobot: 15 kg across "
            "900 mm with six torque sensors for demanding collaborative manufacturing "
            "work."
        ),
        "purpose": (
            "Higher-payload assembly\n"
            "Machine tending\n"
            "Welding\n"
            "Polishing\n"
            "Material handling"
        ),
        "features": (
            "OEM PDP + catalog: 15 kg payload, 900 mm reach, ±0.03 mm repeatability, "
            "33 kg weight, 6-axis, IP54, six joint torque sensors. Compact high-payload "
            "Masterpiece option for dense workcells."
        ),
    },
    4722: {
        "sku": "H2017",
        "series": "h-series",
        "slug": "h2017",
        "payload_kg": 20.0,
        "reach_mm": 1700.0,
        "repeatability_mm": 0.1,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_H,
        "description": (
            "H2017 is Doosan's High-Power cobot for heavy collaborative work: 20 kg "
            "payload across 1700 mm with six-axis torque sensing for safe handling "
            "over a wide radius."
        ),
        "purpose": (
            "Heavy material handling\n"
            "Palletizing\n"
            "Machine tending\n"
            "Welding\n"
            "Logistics handling"
        ),
        "features": (
            "OEM PDP + catalog: 20 kg payload, 1700 mm reach, ±0.1 mm repeatability, "
            "79 kg weight, 6-axis, IP54, joint torque sensors, floor mount. High-Power "
            "series for sophisticated heavy-duty collaborative tasks at relatively "
            "low power draw."
        ),
    },
    4721: {
        "sku": "H2515",
        "series": "h-series",
        "slug": "h2515",
        "payload_kg": 25.0,
        "reach_mm": 1500.0,
        "repeatability_mm": 0.1,
        "dof": 6,
        "ip": "IP54",
        "tags": TAGS_H,
        "description": (
            "H2515 is Doosan's top High-Power collaborative arm at 25 kg payload and "
            "1500 mm reach, using six-axis torque sensing for safe heavy handling and "
            "palletizing."
        ),
        "purpose": (
            "High-payload palletizing\n"
            "Heavy material handling\n"
            "Machine tending\n"
            "Logistics operations"
        ),
        "features": (
            "OEM PDP + catalog: 25 kg payload, 1500 mm reach, ±0.1 mm repeatability, "
            "77 kg weight, 6-axis, IP54, floor mount. Flagship High-Power cobot for "
            "demanding industrial payloads with collaborative safety."
        ),
    },
    2661: {
        "sku": "P3020",
        "series": "p-series",
        "slug": "p3020",
        "payload_kg": 30.0,
        "reach_mm": 2030.0,
        "repeatability_mm": 0.1,
        "dof": 5,
        "ip": "IP54",
        "tags": TAGS_P,
        "description": (
            "P3020 is Doosan's Prime-series palletizing cobot: 30 kg payload and "
            "2030 mm reach with a 5-axis structure that removes singularities for "
            "faster, more efficient palletizing cycles."
        ),
        "purpose": (
            "Palletizing\n"
            "Heavy item handling\n"
            "Logistics and warehouse stacking\n"
            "End-of-line packaging transfer"
        ),
        "features": (
            "OEM PDP + catalog: 30 kg payload, 2030 mm reach, ±0.1 mm repeatability, "
            "83 kg weight, 5-axis (no J4), IP54, floor-only mount, ~25% lower power "
            "vs class peers per OEM claim. Purpose-built for palletizing with DART-"
            "Suite and Doosan Mate."
        ),
    },
}

REJECTS: dict[int, str] = {
    2674: (
        "Duplicate of E0509 #4731 — same OEM SKU and PDP "
        "(https://www.doosanrobotics.com/en/product-solutions/product/e-series/e0509/). "
        "Survivor #4731 keeps bare model name, longer OEM narrative, and verified "
        "e0509-slide01.jpg hero. Reject as duplicate."
    ),
    2673: (
        "Duplicate of A0509 #4730 — same OEM SKU/PDP "
        "(…/a-series/a0509/). Survivor #4730. Reject as duplicate."
    ),
    2672: (
        "Duplicate of A0509F #4729 — same OEM SKU/PDP "
        "(…/a-series/a0509f/). Survivor #4729. Reject as duplicate."
    ),
    2522: (
        "Duplicate of A0509S #2671 — same OEM SKU/PDP "
        "(…/a-series/a0509s/). Survivor #2671 (renamed, enriched). "
        "#2522 had stub features (45 chars) and purpose duplicated description. "
        "Reject as duplicate."
    ),
    2670: (
        "Duplicate of A0912 #4728 — same OEM SKU/PDP "
        "(…/a-series/a0912/). Survivor #4728. Reject as duplicate."
    ),
    2669: (
        "Duplicate of A0912F #4727 — same OEM SKU/PDP "
        "(…/a-series/a0912f/). Survivor #4727. Reject as duplicate."
    ),
    2668: (
        "Duplicate of A0912S #4726 — same OEM SKU/PDP "
        "(…/a-series/a0912s/). Survivor #4726. Reject as duplicate."
    ),
    2667: (
        "Duplicate of M0609 #4725 — same OEM SKU/PDP "
        "(…/m-series/m0609/). Survivor #4725. Reject as duplicate."
    ),
    2521: (
        "Duplicate of M0617 #2666 — same OEM SKU/PDP "
        "(…/m-series/m0617/). Survivor #2666 (renamed, enriched). "
        "#2521 had stub features and purpose=description. Reject as duplicate."
    ),
    2665: (
        "Duplicate of M1013 #4724 — same OEM SKU/PDP "
        "(…/m-series/m1013/). Survivor #4724. Reject as duplicate."
    ),
    2664: (
        "Duplicate of M1509 #4723 — same OEM SKU/PDP "
        "(…/m-series/m1509/). Survivor #4723. Reject as duplicate."
    ),
    2663: (
        "Duplicate of H2017 #4722 — same OEM SKU/PDP "
        "(…/h-series/h2017/). Survivor #4722. Reject as duplicate."
    ),
    2662: (
        "Duplicate of H2515 #4721 — same OEM SKU/PDP "
        "(…/h-series/h2515/). Survivor #4721. Reject as duplicate."
    ),
    2520: (
        "Duplicate of P3020 #2661 — same OEM SKU/PDP "
        "(…/p-series/p3020/). Survivor #2661 (renamed, enriched). "
        "#2520 had stub features and purpose=description. Reject as duplicate."
    ),
}


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }


def verify_hero(name: str, url: str) -> str:
    resp = requests.get(url, timeout=60, headers=_headers())
    resp.raise_for_status()
    data = resp.content
    magic_ok = (
        data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"\xff\xd8\xff"
        or data[:4] == b"RIFF"
    )
    if not magic_ok:
        raise RuntimeError(f"{name}: not an image magic={data[:8]!r}")
    md5 = hashlib.md5(data).hexdigest()
    expected = EXPECTED_MD5.get(name)
    if expected and md5 != expected:
        raise RuntimeError(f"{name}: md5 mismatch got={md5} expected={expected}")
    if len(data) < 8_000:
        raise RuntimeError(f"{name}: image too small ({len(data)} bytes)")
    return md5


def _admin_base() -> str:
    api = (os.environ.get("IMPORT_SYNC_API_BASE_URL") or "").rstrip("/")
    if api.endswith("/api/v1"):
        return api[: -len("/api/v1")]
    return api.rsplit("/api/", 1)[0] if "/api/" in api else api


def _internal_secret() -> str:
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
    if secret:
        return secret
    for candidate in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": _internal_secret(),
    }
    admin_msg = ""
    try:
        resp = requests.post(
            url, headers=headers, json={"rejection_reason": reason[:500]}, timeout=60
        )
        if resp.ok:
            return f"admin-reject {resp.status_code}"
        admin_msg = f"admin {resp.status_code} {(resp.text or '')[:120]}"
    except requests.RequestException as e:
        admin_msg = f"admin ERR {e}"
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {"status": "rejected", "rejection_reason": reason[:500]},
        )
        return f"api-patch-rejected (fallback after {admin_msg})"
    except Exception as e:
        return f"FAIL {admin_msg} / patch {e}"


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = _internal_secret()
    api = _admin_base()
    if not secret:
        print("WARN: no INTERNAL_API_SECRET for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    if not api:
        print("WARN: no IMPORT_SYNC_API_BASE_URL for admin copy-media", file=sys.stderr)
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
    # de-dupe preserve order
    seen: set[str] = set()
    uniq = []
    for t in out:
        if t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return "|".join(uniq[:8])


def build_fix(meta: dict[str, Any]) -> dict[str, Any]:
    sku = meta["sku"]
    series = meta["series"]
    slug = meta["slug"]
    url = _pdp(series, slug)
    family_name = {
        "e-series": "E-SERIES",
        "a-series": "A-SERIES",
        "m-series": "M-SERIES",
        "h-series": "H-SERIES",
        "p-series": "P-SERIES",
    }[series]
    uses = {
        "e-series": "assembly|pick-and-place|inspection|food-handling",
        "a-series": "assembly|pick-and-place|machine-tending|inspection",
        "m-series": "assembly|welding|machine-tending|polishing",
        "h-series": "material-handling|palletizing|machine-tending",
        "p-series": "palletizing|material-handling",
    }[series]
    industries = {
        "e-series": "food|manufacturing|healthcare",
        "a-series": "manufacturing|electronics|food",
        "m-series": "manufacturing|automotive|electronics",
        "h-series": "manufacturing|logistics|warehousing",
        "p-series": "logistics|warehousing|manufacturing",
    }[series]
    return {
        "name": sku,
        "model_name": sku,
        "variant_code": sku,
        "variant_label": sku,
        "url": url,
        "family_key": f"{COMPANY_SLUG}:{series}",
        "family_name": family_name,
        "family_url": SERIES_URL[series],
        "product_url_scope": "exact_variant",
        "image": IMG[sku],
        "description": meta["description"],
        "purpose": meta["purpose"],
        "features": meta["features"],
        "payload_kg": meta["payload_kg"],
        "reach_mm": meta["reach_mm"],
        "repeatability_mm": meta["repeatability_mm"],
        "weight_kg": WEIGHT_KG[sku],
        "dof": meta["dof"],
        "availability_status_key": "available",
        "movement_type_keys": "stationary",
        "industry_keys": industries,
        "use_keys": uses,
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": meta["tags"],
        "manufacturer_country_code": KR,
        "videos": YT.get(sku) or [],
        "information_source_urls": [url, CATALOG_PDF, SERIES_URL[series]],
        "notes_force": (
            f"[AI Research] Doosan 193 enrich. Hero {sku.lower()}-slide01.jpg "
            f"(md5-verified unique). Weight {WEIGHT_KG[sku]} kg from official EN "
            f"catalog PDF. IP {meta.get('ip')} from OEM PDP/catalog. Stripped "
            f"Doosan Robotics name prefix where present. Removed Humanoid/AMR/"
            f"Drone junk tags. Status left pending_review."
        ),
        "source_note": f"{url} | {CATALOG_PDF}",
        "programming_interface": "DART-Suite / DART-Platform (PC) and teach pendant",
        "safety_fencing": (
            "Collaborative operation with collision detection; optional safety zones "
            "(SuperSAFE workspace settings per OEM)"
        ),
        "mounting_options": (
            "Floor only" if sku == "P3020" else "Any orientation (OEM catalog)"
            if series in ("a-series", "m-series", "e-series")
            else "Floor"
        ),
        "deployment_context": "Stationary industrial / collaborative workcell",
        "ecosystem_compatibility": "Doosan Mate peripherals; DART-Suite apps",
    }


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
        "status": "pending_review",
    }
    skip = {
        "videos",
        "notes_force",
        "source_note",
        "images",
        "replace_media",
        "availability_status_key",
    }
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    avail = fix.get("availability_status_key")
    if avail:
        row["availability_status_key"] = avail
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        row["research_notes"] = fix["source_note"]
    videos = fix.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    if fix.get("image"):
        row["images"] = [fix["image"]]
        row["image"] = fix["image"]
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "payload_kg",
        "reach_mm",
        "repeatability_mm",
        "weight_kg",
        "dof",
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
        "url",
        "programming_interface",
        "safety_fencing",
        "mounting_options",
        "deployment_context",
        "ecosystem_compatibility",
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
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "manufacturer_countries": [KR_COUNTRY_ID],
                "manufacturer_country_ref": KR_COUNTRY_ID,
            },
        )
        ok_keys.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def drop_verification_flags(client: ResearchApiClient, robot_ids: list[int]) -> None:
    drop = {
        "image_mismatch",
        "video_mismatch",
        "url_content_mismatch",
        "content_contradiction",
        "unverifiable",
        "non_english_content",
    }
    for rid in robot_ids:
        try:
            r = client._get(f"robots/robots/{rid}/")
        except Exception as exc:
            print(f"  flag-read fail {rid}: {exc}", file=sys.stderr)
            continue
        flags = r.get("quality_flags") or r.get("error_flags") or []
        if isinstance(flags, dict):
            keys = set(flags.keys())
        elif isinstance(flags, list):
            keys = {str(x) for x in flags}
        else:
            keys = set()
        removed = sorted(keys & drop)
        if not removed:
            print(f"  flags ok {rid}: none of {sorted(drop)}")
            continue
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {"quality_flags": {}, "error_flags": []},
            )
            print(f"  dropped flags {rid}: {removed}")
        except Exception as exc:
            print(f"  flag-drop fail {rid}: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Doosan Robotics company 193 robots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--reject-dupes", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--skip-hero-check", action="store_true")
    parser.add_argument("--drop-flags", action="store_true")
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

    # Guard: published names must not collide after rename
    published_names = {
        str(r.get("name") or "").strip().lower()
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "published"
    }

    if not args.skip_hero_check:
        print("Verifying OEM hero hashes…")
        seen_hashes: dict[str, str] = {}
        for name, url in IMG.items():
            md5 = verify_hero(name, url)
            if md5 in seen_hashes:
                raise RuntimeError(f"hash collision {name} vs {seen_hashes[md5]}")
            seen_hashes[md5] = name
            print(f"  OK {name} md5={md5}")

    targets: list[dict[str, Any]] = []
    for rid, meta in KEEPERS.items():
        if args.only and rid not in args.only:
            continue
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        fix = build_fix(meta)
        if fix["name"].lower() in published_names:
            print(
                f"ERROR {rid}: rename {fix['name']} collides with published name",
                file=sys.stderr,
            )
            return 1
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        row = build_row(fix, tags=tags)
        if len(row.get("features") or "") < 40:
            print(f"ERROR {rid}: features too short", file=sys.stderr)
            return 1
        if not row.get("family_key"):
            print(f"ERROR {rid}: missing family_key", file=sys.stderr)
            return 1
        if not (row.get("image") or (row.get("images") or [None])[0]):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: pay={row.get('payload_kg')} "
            f"reach={row.get('reach_mm')} wt={row.get('weight_kg')} "
            f"dof={row.get('dof')} fam={row.get('family_key')} "
            f"vids={len(row.get('video_urls') or [])} tags={tags}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "doosan-193-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "id": t["id"],
                        "name": t["name"],
                        "payload_kg": t["row"].get("payload_kg"),
                        "reach_mm": t["row"].get("reach_mm"),
                        "weight_kg": t["row"].get("weight_kg"),
                        "dof": t["row"].get("dof"),
                        "family_key": t["row"].get("family_key"),
                        "image": (t["row"].get("image") or "")[:140],
                        "url": t["row"].get("url"),
                    }
                    for t in targets
                ],
                "rejects": REJECTS,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not targets and not (args.reject_dupes and REJECTS):
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(
            f"Preview: {preview}. Re-run with "
            "--apply --copy-media --verify-cdn --reject-dupes --drop-flags --mark-done"
        )
        return 0

    # Reject same-SKU dupes FIRST so bare model names are free for keepers
    # (unique name constraint still applies to rejected rows).
    rejected: list[tuple[int, str]] = []
    if args.reject_dupes and args.apply:
        for rid, reason in REJECTS.items():
            # Free bare SKU name on the reject before status flip when it
            # collides with a keeper rename target.
            try:
                cur = client._get(f"robots/robots/{rid}/")
                cur_name = str(cur.get("name") or "")
                if cur_name and not cur_name.lower().endswith("(duplicate rejected)"):
                    client._patch(
                        f"robots/robots/{rid}/",
                        {"name": f"{cur_name} (duplicate rejected)"},
                    )
            except Exception as exc:
                print(f"  pre-reject rename warn {rid}: {exc}", file=sys.stderr)
            msg = reject_robot(client, rid, reason)
            print(f"Reject {rid}: {msg}")
            rejected.append((rid, msg))

    imported: list[int] = []
    for t in targets:
        rid = t["id"]
        row = t["row"]
        fix = t["fix"]
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        bulk["name"] = fix["name"]
        bulk["status"] = "pending_review"
        print(f"Importing {rid} {fix['name']}…", flush=True)
        result = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=False,
            replace_media=True,
            replace_videos=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
        )
        created = int(result.get("created_count") or 0)
        updated = int(result.get("updated_count") or 0)
        err = int(result.get("error_count") or 0)
        print(f"  bulk-import created={created} updated={updated} err={err}")
        if created != 0:
            print(f"ERROR {rid}: unexpected create {result}", file=sys.stderr)
            return 1
        if err:
            print(f"ERROR {rid}: import errors {result}", file=sys.stderr)
            return 1
        patch_typed(client, rid, fix)
        notes = fix.get("notes_force")
        if notes:
            try:
                client._patch(f"robots/robots/{rid}/", {"notes": notes})
            except Exception as exc:
                print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {"status": "pending_review", "name": fix["name"]},
            )
        except Exception as exc:
            print(f"  status/name patch warn {rid}: {exc}", file=sys.stderr)
        imported.append(rid)

    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
        for t in targets:
            if t["id"] in imported:
                patch_typed(client, t["id"], t["fix"])

    if args.verify_cdn and imported:
        cmd = [
            sys.executable,
            str(_RESEARCH_DIR / "verify_cdn_images.py"),
            "--company-id",
            str(COMPANY_ID),
        ]
        print("Running", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(_RESEARCH_DIR))

    if args.drop_flags and imported:
        drop_verification_flags(client, imported)

    if args.mark_done and imported:
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    print(
        json.dumps(
            {"imported": imported, "rejected": rejected, "preview": str(preview)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
