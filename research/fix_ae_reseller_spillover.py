#!/usr/bin/env python3
"""Enrich the 8 third-party models reassigned out of the AE Robotics (1375) reseller
queue into their real manufacturers (FANUC 189, AUBO 769, YOUIBOT 802).

Context
-------
AE Robotics (automationar.com) is a one-stop *distributor*; every product page names
the real maker in a ``Brand:`` field. 17 of its 23 to-review robots were other OEMs'
products. 9 duplicated better records under the real manufacturer and were rejected
(``duplicate`` + ``wrong_company``); these 8 are genuinely new models and were moved to
the correct company. This script gives them a real enrichment pass at their new home.

Sourcing rules honoured
-----------------------
* Every typed spec below is read off the manufacturer's own page or brochure, and the
  citation is recorded in ``information_source_urls``.
* Rule 11 (family tables): the Trans 500 brochure documents **DCM500 *and* DCM1000**.
  Specs are taken from the DCM500 row of the page-5 "Order Information" model table,
  never from a shared/first column.
* Rule 9c (fail closed on media): AUBO publishes no per-model photo of the FB
  explosion-proof arms (only a launch-event group photo and a 4-up family banner), and
  YOUIBOT's live site has no standalone Trans/Corgi render — those SKUs left their
  catalogue. Those six robots get **no** hero plus an actionable ``[IMAGE TO-DO]``
  note; no sibling render or family banner is substituted.
* Rule 4a: source URLs go to ``information_source_urls``, never into prose fields.
* Uncited ``release_year`` values inherited from the reseller listing are nulled;
  years are only set where the manufacturer states them.

Usage
-----
    python fix_ae_reseller_spillover.py                 # dry run (default)
    python fix_ae_reseller_spillover.py --apply
    python fix_ae_reseller_spillover.py --apply --copy-media
    python fix_ae_reseller_spillover.py --only 4822,4824
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()

import requests

from api_client import ResearchApiClient

REPORT_DIR = _HERE / "staging" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT = REPORT_DIR / "ae-reseller-spillover.json"

FANUC_CDN = "https://cdn.craft.cloud/6166486b-1eb4-43d5-990c-ea573de4e750"
FANUC_R2000_SERIES = "https://www.fanucamerica.com/products/robots/series/r-2000"

# ---------------------------------------------------------------------------
# Shared prose. `purpose` is the OEM application list, ONE PER LINE, and must never
# restate `description` (hard rule 0z/4b).
# ---------------------------------------------------------------------------

FANUC_R2000_FEATURES_TAIL = (
    "Controller: FANUC R-30iB Plus\n"
    "Mounting: floor\n"
    "Protection: IP54 body standard (IP56 optional); IP67 wrist and J3 arm\n"
    "Average power consumption: 3 kW\n"
    "Motion range: J1 370 deg, J2 136 deg, J3 301 deg, J4 720 deg, J5 250 deg, J6 720 deg"
)

AUBO_FB_NOTE = (
    "[IMAGE TO-DO - no hero, deliberate]\n"
    "AUBO publishes no per-model photograph of the FB explosion-proof arms. Checked "
    "aubo-cobot.com (current nav is i / C / iV / iF series only - iF is the FORCE-CONTROL "
    "line, not explosion-proof), aubo-usa.com (i and iS series only), "
    "developer.aubo-robotics.cn spec downloads (i3/i5/i7/i10/i12/i20 only), and the "
    "explosion-proof launch announcement aubo-cobot.com/public/jumcase?xwid=4. The only "
    "explosion-proof imagery there is (a) a launch-event stage photo dominated by nine "
    "people and (b) a 4-up family lineup banner - neither is a valid per-model hero "
    "(rules 9a/9c). aubo-robots.com and auborobots.com are dead domains.\n"
    "Previously in the slot: nothing (the reseller record never had an image).\n"
    "ACTION FOR TEAM: request a per-model product render from AUBO for this exact SKU, "
    "or source a licensed photo. Distributor listings (made-in-china, troysupply, "
    "roboct) do carry photos but are rights-restricted (rule 9d).\n"
    "Do NOT substitute a base i-series render, the family lineup banner, or the launch photo.\n"
    "---\n"
)


def youibot_note(model: str, brochure: str, page: str) -> str:
    return (
        "[IMAGE TO-DO - no hero, deliberate]\n"
        f"{model} left YOUIBOT's catalogue: the live site lists only the Lifting "
        "(L300-smart/L600/L1000-CE/L1500), Platform (B150/B300/B600/P200-CE/P300), Roller "
        "Conveyor, Operation, ATS, Automatic Trolley and ARIS series - no Trans and no "
        "Corgi. en.youibot.com has no standalone render for it (the only Trans/Corgi "
        "artwork on-site is a 3-up comparison graphic, and the news-page asset is a 4 KB "
        "placeholder).\n"
        f"A clean white-background product render DOES exist inside the official brochure: "
        f"{brochure} ({page}). It is embedded with a separate stencil mask, so it must be "
        "rasterised from the page rather than extracted as an image, then cropped.\n"
        "Previously in the slot: nothing (the reseller record never had an image).\n"
        "ACTION FOR TEAM: rasterise that brochure page, crop the product view, upload it "
        "as this robot's hero. Everything else about this record is already OEM-cited.\n"
        "Do NOT substitute a current L-/B-/P-series render - those are different models.\n"
        "---\n"
    )


# ---------------------------------------------------------------------------
# ROBOT_DATA - one curated entry per robot.
#   patch  : fields written through client._patch (wipe-safe; NOT update-data)
#   media  : external OEM image URLs, primary first (attached via bulk-import)
#   note   : text prepended to Robot.notes, existing text preserved
# ---------------------------------------------------------------------------

ROBOT_DATA: dict[int, dict[str, Any]] = {
    # ================= FANUC (company 189) =================
    4822: {
        "company_ref": 189,
        "label": "FANUC R-2000iC/125L",
        "patch": {
            "name": "R-2000iC/125L",
            "url": f"{FANUC_R2000_SERIES}/r-2000ic-125l",
            "product_url_scope": "exact_variant",
            "family_key": "fanuc:r-2000",
            "family_name": "R-2000",
            "family_url": FANUC_R2000_SERIES,
            "model_name": "R-2000iC/125L",
            "variant_code": "R-2000iC/125L",
            "variant_label": "125L",
            "description": (
                "The FANUC R-2000iC/125L is a six-axis heavy-payload industrial robot from "
                "the R-2000 series, built around an extended arm that trades none of the "
                "series' rigidity for a 3100 mm reach. It handles 125 kg anywhere in that "
                "envelope at +/-0.05 mm repeatability, and its slim, floor-mounted design "
                "is intended to drop into crowded cells where a shorter-armed robot would "
                "need repositioning equipment."
            ),
            "purpose": (
                "Assembly\nMaterial Handling\nSpot Welding\nMaterial Removal\n"
                "Dispensing & Sealing\nPicking & Packaging"
            ),
            "features": (
                "Six-axis articulated arm with 3100 mm reach and 125 kg maximum payload\n"
                "Repeatability of +/-0.05 mm across the full work envelope\n"
                "Mechanical weight 1115 kg\n"
                "Extended-reach variant of the R-2000 series for large work envelopes\n"
                "Axis speeds: J1 130 deg/s, J2 115 deg/s, J3 125 deg/s, J4 180 deg/s, "
                "J5 180 deg/s, J6 260 deg/s\n"
                "Wrist load moment / inertia: J4 710 Nm / 72 kgm2, J5 710 Nm / 72 kgm2, "
                "J6 355 Nm / 40 kgm2\n" + FANUC_R2000_FEATURES_TAIL
            ),
            "payload_kg": 125.0,
            "reach_mm": 3100.0,
            "repeatability_mm": 0.05,
            "weight_kg": 1115.0,
            "dof": 6,
            "availability_status": 11,       # Available
            "release_year": None,            # reseller's "2023" was uncited
            "categories": ["Industrial-Robot"],
            "uses": [21, 32, 42, 36, 34],    # assembly, material-handling, spot-welding,
                                             # machine-tending, dispensing
            "industries": [26, 12, 50],      # automotive, manufacturing, industrial
            "movement_types": [10],          # stationary
            "tags": ["6-Axis", "Industrial Robot", "Industrial", "Material Handling",
                     "Heavy-Duty", "Factory Automation", "Assembly"],
            "mounting_options": "Floor mount",
            "deployment_context": (
                "Floor-mounted in industrial production cells; slimline design suits "
                "crowded factory layouts requiring a long reach."
            ),
            "programming_interface": "FANUC R-30iB Plus controller with iRVision support",
            "information_source_urls": [
                f"{FANUC_R2000_SERIES}/r-2000ic-125l",
                FANUC_R2000_SERIES,
            ],
        },
        "media": [
            f"{FANUC_CDN}/assets/images/fea-ro-pr-r2000125l-l-1.jpg",
            f"{FANUC_CDN}/assets/case-studies/how-one-company-doubled-output-and-improved-"
            f"employee-satisfaction-through-automation/r-2000ic-125l-material-handling.jpg",
            f"{FANUC_CDN}/assets/images/fea-ro-ia-r2000-vis-pick-1.jpg",
            f"{FANUC_CDN}/assets/images/fea-ro-ia-r2000-spotweld-1.jpg",
        ],
    },
    4824: {
        "company_ref": 189,
        "label": "FANUC R-2000iC/210L",
        "patch": {
            "name": "R-2000iC/210L",
            "url": f"{FANUC_R2000_SERIES}/r-2000ic-210l",
            "product_url_scope": "exact_variant",
            "family_key": "fanuc:r-2000",
            "family_name": "R-2000",
            "family_url": FANUC_R2000_SERIES,
            "model_name": "R-2000iC/210L",
            "variant_code": "R-2000iC/210L",
            "variant_label": "210L",
            "description": (
                "The FANUC R-2000iC/210L is the long-arm, 210 kg member of the R-2000 "
                "series and the successor to the R-2000iB/185L, lifting an extra 25 kg "
                "while adding rigidity and wrist load moment. A 3100 mm reach paired with "
                "a compact footprint and a small wrist with tight dressout makes it a "
                "mainstay of automotive spot-welding lines."
            ),
            "purpose": (
                "Spot Welding\nWelding\nAssembly\nMaterial Removal\nPalletizing\n"
                "Picking & Packaging"
            ),
            "features": (
                "Six-axis articulated arm with 3100 mm reach and 210 kg maximum payload\n"
                "Repeatability of +/-0.05 mm\n"
                "Mechanical weight 1350 kg\n"
                "Successor to the R-2000iB/185L with 25 kg more payload plus improved "
                "rigidity, wrist load moment and inertia\n"
                "Compact dressout package and small wrist suited to automotive spot welding\n"
                "Axis speeds: J1 105 deg/s, J2 136 deg/s, J3 85 deg/s, J4 120 deg/s, "
                "J5 120 deg/s, J6 200 deg/s\n"
                "Wrist load moment / inertia: J4 1700 Nm / 320 kgm2, J5 1700 Nm / 320 kgm2, "
                "J6 900 Nm / 230 kgm2\n" + FANUC_R2000_FEATURES_TAIL
            ),
            "payload_kg": 210.0,
            "reach_mm": 3100.0,
            "repeatability_mm": 0.05,
            "weight_kg": 1350.0,
            "dof": 6,
            "availability_status": 11,
            "release_year": None,
            "categories": ["Industrial-Robot"],
            "uses": [42, 21, 25, 32, 36],    # spot-welding, assembly, palletizing,
                                             # material-handling, machine-tending
            "industries": [26, 12, 50],
            "movement_types": [10],
            "tags": ["6-Axis", "Industrial Robot", "Industrial", "Welding",
                     "Heavy-Duty", "Factory Automation", "Material Handling"],
            "mounting_options": "Floor mount",
            "deployment_context": (
                "Automotive body shops and other high-throughput spot-welding lines; "
                "compact footprint fits crowded factory environments."
            ),
            "programming_interface": "FANUC R-30iB Plus controller with iRVision support",
            "information_source_urls": [
                f"{FANUC_R2000_SERIES}/r-2000ic-210l",
                FANUC_R2000_SERIES,
            ],
        },
        "media": [
            f"{FANUC_CDN}/assets/products/r-2000ic-210l/R-2000iC_210L-Beauty-Shot-Right.png",
            f"{FANUC_CDN}/assets/products/r-2000ic-210l/R-2000iC_210L-Beauty-Shot-Left.png",
            f"{FANUC_CDN}/assets/images/fea-ro-pr-r2000210l-r-1.jpg",
            f"{FANUC_CDN}/assets/images/fea-ro-pr-r2000210l-l-3.jpg",
            f"{FANUC_CDN}/assets/images/fea-ro-pr-r2000210l-r-7.jpg",
        ],
    },
}

# ================= AUBO explosion-proof (company 769) =================
# The FB arms are the explosion-proof line AUBO debuted 2019-03-10 in Changzhou
# (aubo-cobot.com/public/jumcase?xwid=4). Note: AUBO's "iF" series is FORCE CONTROL,
# a different product line - do not conflate. Payload comes from the model
# designation, which AUBO uses consistently across the i-series it is built on; no
# further FB-specific numbers are published, so nothing else is asserted.
AUBO_DEBUT = "https://www.aubo-cobot.com/public/jumcase?xwid=4"

_AUBO_COMMON: dict[str, Any] = {
    "family_key": "aubo:fb-explosion-proof",
    "family_name": "FB Explosion-Proof",
    "family_url": AUBO_DEBUT,
    "product_url_scope": "exact_variant",
    "availability_status": 3,          # Released - no discontinuation notice published
    "release_year": None,              # reseller years were uncited; only the LINE
                                       # debut (2019) is documented, not per model
    "categories": ["Collaborative-Robot"],
    "movement_types": [10],
    "dof": 6,
    "mounting_options": "Floor, wall or ceiling mount (any angle)",
}

for _rid, _model, _payload, _kind in (
    (3529, "AUBO-i5FB", 5.0, "general"),
    (4810, "AUBO-i3FB", 3.0, "painting"),
    (4811, "AUBO-i10FB", 10.0, "painting"),
):
    _is_paint = _kind == "painting"
    ROBOT_DATA[_rid] = {
        "company_ref": 769,
        "label": _model,
        "note": AUBO_FB_NOTE,
        "media": [],  # fail closed - rule 9c
        "patch": {
            **_AUBO_COMMON,
            "name": _model,
            "model_name": _model,
            "variant_code": _model,
            "variant_label": _model.replace("AUBO-", ""),
            "url": AUBO_DEBUT,
            "payload_kg": _payload,
            "description": (
                f"The {_model} is the explosion-protected member of AUBO's six-axis "
                f"collaborative range, rated for a {_payload:.0f} kg payload. It belongs to "
                "the explosion-proof cobot line AUBO launched in Changzhou in March 2019, "
                "which the company presented as the smallest and lightest explosion-proof "
                "robot of its kind, with protection reaching IP65 so it can work in "
                + ("paint booths and other " if _is_paint else "")
                + "atmospheres where flammable vapour or dust rules out a standard arm."
            ),
            "purpose": (
                "Spray painting in hazardous atmospheres\nCoating and finishing\n"
                "Assembly in explosion-risk areas"
                if _is_paint
                else "Handling in explosion-risk areas\nAssembly in hazardous atmospheres\n"
                     "Machine tending in flammable environments"
            ),
            "features": (
                f"Six-axis explosion-protected collaborative arm, {_payload:.0f} kg payload\n"
                "Protection level up to IP65\n"
                "Part of the explosion-proof cobot line AUBO debuted on 10 March 2019 in "
                "Changzhou, Jiangsu, presented by AUBO as the smallest and lightest "
                "explosion-proof robot in its class\n"
                + (
                    "Intended for spray painting and coating duty inside booths where "
                    "solvent vapour is present\n"
                    if _is_paint
                    else "Intended for handling and assembly duty in flammable or "
                         "dust-laden atmospheres\n"
                )
                + "AUBO publishes no FB-specific dimensional, reach, repeatability or mass "
                "figures; those fields are deliberately left blank rather than inherited "
                "from the standard i-series arm this model is based on."
            ),
            "uses": ([39, 80, 68, 21] if _is_paint else [46, 21, 36]),
            "industries": [25, 33, 26, 12],   # chemical, oil-gas, automotive, manufacturing
            "tags": (
                ["Cobot", "Collaborative Robot", "Industrial", "6-Axis", "Painting",
                 "Industrial Environment"]
                if _is_paint
                else ["Cobot", "Collaborative Robot", "Industrial", "6-Axis",
                      "Industrial Environment"]
            ),
            "safety_fencing": (
                "Collaborative operation; explosion-protected enclosure rated to IP65 for "
                "use in hazardous-atmosphere zones."
            ),
            "deployment_context": (
                "Hazardous-area production cells - paint booths, solvent handling, "
                "chemical and oil-and-gas plant - where a standard cobot is not permitted."
                if _is_paint
                else "Hazardous-area production cells in chemical, oil-and-gas and "
                     "automotive plants where flammable vapour or dust is present."
            ),
            "information_source_urls": [AUBO_DEBUT],
        },
    }

# ================= YOUIBOT legacy AMRs (company 802) =================
# Specs from the official YOUIBOT product brochures. Trans 500's brochure covers
# DCM500 AND DCM1000: the payload/size below come from the DCM500 row of the page-5
# "Order Information" model table (rule 11), not a shared column.
YB_MATRIX = "https://en.youibot.com/news/youai-zhihe-robot-full-matrix-heavy-release.html"
YB_TRANS200_PDF = (
    "https://www.aiconrobot.com/wp-content/uploads/2021/06/DCM200Trans-200-product-brochure.pdf"
)
YB_TRANS500_PDF = (
    "https://www.aiconrobot.com/wp-content/uploads/2021/06/"
    "DCM500_1000Trans-500_1000-Product-Brochure.pdf"
)
YB_CORGI_PDF = (
    "https://www.aiconrobot.com/wp-content/uploads/2021/07/FCP150Corgi-100-Product-Brochure.pdf"
)

_YB_COMMON: dict[str, Any] = {
    "availability_status": 4,   # Discontinued - absent from YOUIBOT's current series
                               # listing (Lifting / Platform / Roller / Operation / ATS /
                               # Trolley / ARIS) as of 2026-07-26; superseded by B/P series
    "release_year": 2018,      # "In 2018, we launched our flagship industrial AMR
                               # product, the Trans Corgi" - YOUIBOT, en.youibot.com
    "categories": ["Mobile-Robots"],
    "movement_types": [4, 17],  # wheeled, mobile
    "voltage": 51.2,
    "speed": 5.4,               # 1.5 m/s -> km/h (FloatField is km/h, rule 0a)
    "repeatability_mm": 5.0,    # +/-5 mm repeatable indoor positioning
    "industries": [45, 12, 11, 50],  # warehousing, manufacturing, logistics, industrial
}

_YB_FEATURE_TAIL = (
    "Hybrid laser-SLAM and QR-code navigation, no reflectors required\n"
    "Repeatable indoor positioning of +/-5 mm and +/-1 deg docking angle\n"
    "Cold-rolled-steel body, IP20, rated for Class 100 cleanliness\n"
    "Lithium battery with automatic charging, manual charging and ~30 s hot-swap for "
    "24/7 operation\n"
    "YOUIFLEET fleet management dispatches up to 100 robots at once\n"
    "Ambient range 0-40 C, 10-90% RH; requires flat dry floor (min flatness FF25)"
)

ROBOT_DATA[4817] = {
    "company_ref": 802,
    "label": "YOUIBOT Trans 200 (DCM200)",
    "note": youibot_note("Trans 200 (DCM200)", YB_TRANS200_PDF, "page 3, top-left 3/4 view"),
    "media": [],
    "patch": {
        **_YB_COMMON,
        "name": "Trans 200 (DCM200)",
        "model_name": "DCM200",
        "variant_code": "DCM200",
        "variant_label": "Trans 200",
        "family_key": "youibot:trans",
        "family_name": "Trans",
        "family_url": YB_MATRIX,
        "product_url_scope": "exact_variant",
        "url": YB_MATRIX,
        "description": (
            "The YOUIBOT Trans 200, model code DCM200, is a medium-duty indoor autonomous "
            "mobile robot for moving material between stations inside factories and "
            "warehouses. A 190 mm-tall chassis carries 200 kg and accepts more than ten "
            "interchangeable top modules - rollers, lifting and rotating decks, conveyors - "
            "so one platform covers transport, machine feeding and inspection rounds."
        ),
        "purpose": (
            "Internal material transport in manufacturing\nWarehouse logistics\n"
            "Security inspection rounds\nMachine feeding and unloading"
        ),
        "features": (
            "Maximum payload 200 kg\n"
            "Chassis 1002 x 638 x 190 mm with a 1105 mm turning diameter; 190 mm height "
            "suits low-clearance applications\n"
            "Vehicle mass 100 kg\n"
            "Top speed 1.5 m/s (5.4 km/h) and 180 deg/s rotation\n"
            "Accepts 10+ top modules (rollers, lifting and rotating deck, conveyor)\n"
            "Two diagonally mounted safety lidars give 360 deg coverage, 30 m range, "
            "270 deg each; 360 deg collision detection and two emergency stops\n"
            "LiFePO4 battery, 51.2 V / 30.4 Ah, 8 h run time, recharge in 2 h or less, "
            "cycle life 2000+\n"
            "Climbs 5 mm steps, crosses 30 mm gaps, handles 3 deg slopes on 125 mm "
            "polyurethane drive wheels\n" + _YB_FEATURE_TAIL
        ),
        "payload_kg": 200.0,
        "weight_kg": 100.0,
        "length_mm": 1002.0,
        "width_mm": 638.0,
        "height_mm": 190.0,
        "runtime_minutes": 480,
        "charging_time_minutes": 120,
        "battery_wh": 1556.5,          # 51.2 V x 30.4 Ah
        "uses": [104, 74, 62, 32, 60],  # material-transport, intralogistics, logistics,
                                        # material-handling, security
        "tags": ["AMR", "Autonomous Mobile Robot", "AGV", "Autonomous",
                 "Indoor Logistics", "Cleanroom", "Industrial"],
        "ecosystem_compatibility": (
            "YOUIFLEET fleet manager; integrates with MES/WMS via standard interfaces; "
            "10+ interchangeable top modules."
        ),
        "deployment_context": (
            "Indoor manufacturing, warehouse logistics and inspection routes; Class 100 "
            "cleanroom capable; needs a flat dry floor."
        ),
        "programming_interface": "YOUIFLEET fleet management system; MES/WMS interfaces",
        "information_source_urls": [YB_TRANS200_PDF, YB_MATRIX],
    },
}

ROBOT_DATA[4816] = {
    "company_ref": 802,
    "label": "YOUIBOT Trans 500 (DCM500)",
    "note": youibot_note("Trans 500 (DCM500)", YB_TRANS500_PDF, "page 3, top-left 3/4 view"),
    "media": [],
    "patch": {
        **_YB_COMMON,
        "name": "Trans 500 (DCM500)",
        "model_name": "DCM500",
        "variant_code": "DCM500",
        "variant_label": "Trans 500",
        "family_key": "youibot:trans",
        "family_name": "Trans",
        "family_url": YB_MATRIX,
        "product_url_scope": "exact_variant",
        "url": YB_MATRIX,
        "description": (
            "The YOUIBOT Trans 500, model code DCM500, is the 500 kg member of the Trans "
            "family of indoor autonomous mobile robots. It keeps the family's laser-SLAM "
            "navigation and +/-5 mm docking accuracy on a heavier 1060 x 838 mm chassis, "
            "and can be ordered as the DCM500-RL500 with an integrated lifting and "
            "rotating deck for pallet and trolley work."
        ),
        "purpose": (
            "Heavy internal material transport in manufacturing\nWarehouse logistics\n"
            "Pallet and trolley movement\nSecurity inspection rounds"
        ),
        "features": (
            "Maximum payload 500 kg\n"
            "Chassis 1060 x 838 x 265 mm (290 mm with the lifting and rotating module) "
            "and a 1260 mm turning diameter\n"
            "Vehicle mass 310 kg\n"
            "Top speed 1.5 m/s (5.4 km/h) and 45 deg/s rotation\n"
            "Optional lifting and rotating module: 60 mm lift, 360 deg rotation "
            "(DCM500-RL500)\n"
            "Two diagonally mounted safety lidars give 360 deg coverage, 30 m range, "
            "270 deg each; optional 3D vision sensor for obstacle avoidance\n"
            "LiFePO4 battery, 51.2 V / 30.4 Ah, 10 h run time, recharge in 2 h or less, "
            "cycle life 2000+\n"
            "Climbs 5 mm steps, crosses 30 mm gaps, handles 2.5 deg slopes on 150 mm "
            "polyurethane drive wheels\n" + _YB_FEATURE_TAIL
        ),
        "payload_kg": 500.0,
        "weight_kg": 310.0,
        "length_mm": 1060.0,
        "width_mm": 838.0,
        "height_mm": 265.0,
        "runtime_minutes": 600,
        "charging_time_minutes": 120,
        "battery_wh": 1556.5,
        "uses": [104, 74, 62, 32, 54],  # + pallet-transportation
        "tags": ["AMR", "Autonomous Mobile Robot", "AGV", "Autonomous",
                 "Indoor Logistics", "Heavy-Duty", "Industrial"],
        "ecosystem_compatibility": (
            "YOUIFLEET fleet manager; MES/WMS interfaces; optional lifting and rotating "
            "module (DCM500-RL500)."
        ),
        "deployment_context": (
            "Indoor manufacturing and warehouse logistics moving heavy loads, pallets and "
            "trolleys; Class 100 cleanroom capable."
        ),
        "programming_interface": "YOUIFLEET fleet management system; MES/WMS interfaces",
        "information_source_urls": [YB_TRANS500_PDF, YB_MATRIX],
    },
}

ROBOT_DATA[4818] = {
    "company_ref": 802,
    "label": "YOUIBOT Corgi (FCP150)",
    "note": (
        "[SPEC CORRECTION 2026-07-26] The reseller listing this record came from "
        "(automationar.com, AE Robotics) advertised a 50 kg working load. YOUIBOT's own "
        "FCP150 Corgi-100 brochure states a maximum payload of 100 kg, so payload_kg now "
        "carries the manufacturer figure. The 50 kg number was never OEM-documented.\n"
        "---\n"
    )
    + youibot_note("Corgi (FCP150)", YB_CORGI_PDF, "page 1 cover render / page 3 views"),
    "media": [],
    "patch": {
        **_YB_COMMON,
        "name": "Corgi (FCP150)",
        "model_name": "FCP150",
        "variant_code": "FCP150",
        "variant_label": "Corgi",
        "family_key": "youibot:corgi",
        "family_name": "Corgi",
        "family_url": YB_MATRIX,
        "product_url_scope": "exact_variant",
        "url": YB_MATRIX,
        "description": (
            "The YOUIBOT Corgi, model code FCP150, is a light-duty indoor autonomous "
            "mobile robot built narrow on purpose: under 500 mm wide, it threads 600 mm "
            "aisles that a full-size AMR cannot enter. It carries up to 100 kg, navigates "
            "by laser SLAM with QR-code inertial backup, and takes the same family of top "
            "modules as its larger Trans siblings, which made it YOUIBOT's answer for "
            "cramped electronics and semiconductor plants."
        ),
        "purpose": (
            "Internal material transport in confined spaces\nWarehouse logistics\n"
            "Security and equipment inspection rounds\nCleanroom material movement"
        ),
        "features": (
            "Maximum payload 100 kg\n"
            "Chassis 568 x 560 x 287 mm with a 653 mm rotation diameter; under 500 mm wide "
            "so it passes 600-660 mm aisles\n"
            "Vehicle mass 75 kg\n"
            "Top speed 1.5 m/s (5.4 km/h) and 180 deg/s rotation\n"
            "Accepts 10+ top modules (lifting and rotating deck, roller conveyor, robot "
            "arm, pan-tilt camera, gas sensor)\n"
            "One forward safety lidar, 30 m range, 270 deg; 360 deg collision detection, "
            "two emergency stops, optional 3D vision\n"
            "Ternary lithium battery, 51.2 V / 18 Ah, 8 h run time, recharge in 1.5 h or "
            "less, cycle life 2000+\n"
            "Climbs 5 mm steps, crosses 20 mm gaps, handles 2 deg slopes on 150 x 35 mm "
            "polyurethane drive wheels\n"
            "Hybrid laser-SLAM and QR-code inertial navigation, no reflectors required\n"
            "Repeatable indoor positioning of +/-5 mm and +/-1 deg docking angle\n"
            "Cold-rolled-steel and plastic body, IP20\n"
            "Ambient range 5-40 C, 5-95% RH; requires flat dry floor (min flatness FF25)\n"
            "YOUIFLEET fleet management dispatches up to 100 robots at once"
        ),
        "payload_kg": 100.0,
        "weight_kg": 75.0,
        "length_mm": 568.0,
        "width_mm": 560.0,
        "height_mm": 287.0,
        "runtime_minutes": 480,
        "charging_time_minutes": 90,
        "battery_wh": 921.6,           # 51.2 V x 18 Ah
        "uses": [104, 74, 62, 7, 60],  # + inspection, security
        "tags": ["AMR", "Autonomous Mobile Robot", "AGV", "Autonomous",
                 "Indoor Logistics", "Cleanroom", "Compact"],
        "ecosystem_compatibility": (
            "YOUIFLEET fleet manager; MES/WMS interfaces; 10+ interchangeable top modules "
            "including robot arms, pan-tilt cameras and gas sensors."
        ),
        "deployment_context": (
            "Narrow-aisle indoor logistics in electronics, semiconductor and cleanroom "
            "plants; also inspection rounds."
        ),
        "programming_interface": "YOUIFLEET fleet management system; MES/WMS interfaces",
        "information_source_urls": [YB_CORGI_PDF, YB_MATRIX],
    },
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF", b"GIF8")


def head_ok(url: str) -> tuple[bool, str]:
    """Rule 9b: validate by MAGIC BYTES, not Content-Type (CDNs lie)."""
    try:
        r = requests.get(url, headers=UA, timeout=45, stream=True)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        head = r.raw.read(32) or b""
        r.close()
        if not any(head.startswith(m) for m in MAGIC) and head[4:12] != b"ftypavif":
            return False, "not an image (magic bytes)"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def resolve_tags(client: ResearchApiClient, names: list[str]) -> tuple[list[str], list[str]]:
    """Rule 8: exact TagCatalog names only. Returns (kept, missing)."""
    catalog = {(t.get("name") or "").strip() for t in client.list_tags(page_size=500)}
    kept = [n for n in names if n in catalog]
    missing = [n for n in names if n not in catalog]
    return kept, missing


def copy_media(rid: int) -> tuple[bool, str]:
    base = os.environ.get("ADMIN_BASE", "https://ragadmin.robotaigeek.com").rstrip("/")
    secret = os.environ.get("INTERNAL_API_SECRET", "")
    url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    try:
        r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
        return r.status_code == 200, f"HTTP {r.status_code} {r.text[:160]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--only", help="comma-separated robot ids")
    args = ap.parse_args()
    tag = "APPLY" if args.apply else "DRY-RUN"

    targets = sorted(ROBOT_DATA)
    if args.only:
        keep = {int(x) for x in args.only.split(",") if x.strip()}
        targets = [r for r in targets if r in keep]

    client = ResearchApiClient()
    log: dict[str, Any] = {"mode": tag, "robots": [], "errors": []}

    print(f"=== {tag}: enrich {len(targets)} reassigned third-party models ===\n")

    for rid in targets:
        spec = ROBOT_DATA[rid]
        patch = dict(spec["patch"])
        media = list(spec.get("media") or [])
        row: dict[str, Any] = {"id": rid, "label": spec["label"]}
        print(f"--- {rid}  {spec['label']}")

        try:
            before = client._get(f"robots/robots/{rid}/")
        except Exception as exc:  # noqa: BLE001
            print(f"    FETCH FAILED: {exc}")
            log["errors"].append({"id": rid, "error": str(exc)})
            continue

        # Robot.company_ref is documented as "kept in sync with company_owners", so
        # patching company_ref ALONE silently snaps back to whatever owns the robot via
        # the M2M (that is how 4810/4824 reverted to AE on the first pass). Always write
        # company_owner_ids too, with the real manufacturer as the sole owner - otherwise
        # the display name renders as "AE Robotics Co., Ltd. / FANUC".
        cur_company = (before.get("company_ref") or {}).get("id")
        cur_owners = sorted(o.get("id") for o in (before.get("company_owners") or []))
        want = spec["company_ref"]
        if cur_company != want or cur_owners != [want]:
            print(f"    company_ref={cur_company} owners={cur_owners} -> {want} (sole owner)")
            patch["company_ref"] = want
            patch["company_owner_ids"] = [want]
        if before.get("status") == "published":
            print("    SKIP: published (rule 9)")
            log["errors"].append({"id": rid, "skip": "published"})
            continue

        # tags: exact catalog names only
        if patch.get("tags"):
            kept, missing = resolve_tags(client, patch["tags"])
            if missing:
                print(f"    tags not in catalog, dropped: {missing}")
            patch["tags"] = kept
            row["tags"] = kept
            row["tags_dropped"] = missing

        # notes: prepend, never clobber. Every one of these 8 records was created from a
        # distributor storefront, so the provenance is worth recording on the record
        # itself - the next agent should not have to re-derive why it moved company.
        provenance = (
            "[PROVENANCE 2026-07-26] This record was originally filed under AE Robotics "
            "Co., Ltd. (company 1375), a Chinese one-stop robot distributor whose "
            "automationar.com product page for this item names "
            f"Brand: {spec['label'].split()[0]}. AE is the reseller, not the maker, so the "
            f"robot was moved to its real manufacturer (company {spec['company_ref']}) and "
            "enriched from that manufacturer's own material. The AE product URL is kept in "
            "information_source_urls only as provenance, never as a spec citation.\n"
            "---\n"
        )
        note_text = provenance + (spec.get("note") or "")
        existing = before.get("notes") or ""
        if "[PROVENANCE 2026-07-26]" not in existing:
            patch["notes"] = note_text + existing
        else:
            print("    provenance note already present, leaving notes alone")

        # media pre-flight: magic-byte verify every candidate before attaching
        good: list[str] = []
        for u in media:
            ok, why = head_ok(u)
            print(f"    media {'OK  ' if ok else 'FAIL'}  {why:<28} {u[-70:]}")
            if ok:
                good.append(u)
        row["media_ok"] = good
        if media and not good:
            print("    WARNING: every media candidate failed - leaving hero empty")
        if not media:
            print("    media: none by design (fail closed, note written)")

        # completeness gate: what are we actually writing?
        typed = [k for k in ("payload_kg", "reach_mm", "repeatability_mm", "weight_kg",
                             "length_mm", "width_mm", "height_mm", "speed", "dof",
                             "runtime_minutes", "charging_time_minutes", "battery_wh",
                             "voltage") if patch.get(k) is not None]
        print(f"    typed specs: {', '.join(typed) or 'NONE'}")
        print(f"    family_key={patch.get('family_key')!r} "
              f"avail={patch.get('availability_status')} year={patch.get('release_year')}")
        row["typed_specs"] = typed
        row["patch_keys"] = sorted(patch)

        if not args.apply:
            print()
            log["robots"].append(row)
            continue

        try:
            client._patch(f"robots/robots/{rid}/", patch)
        except Exception as exc:  # noqa: BLE001
            print(f"    PATCH FAILED: {exc}")
            log["errors"].append({"id": rid, "error": f"patch: {exc}"})
            continue

        # media via bulk-import: needs BOTH update_existing and patch_existing
        if good:
            payload = {
                "name": patch.get("name") or before.get("name"),
                "company": (before.get("company_ref") or {}).get("name"),
                "image": good[0],
                "images": good,
                "url": patch.get("url") or before.get("url"),
            }
            try:
                resp = client.bulk_import_robots(
                    [payload],
                    update_existing=True,
                    patch_existing=True,
                    status="pending_review",
                    skip_company_update=True,
                    replace_media=True,
                )
                counts = {k: v for k, v in resp.items() if k.endswith("_count")}
                print(f"    bulk-import: {counts}")
                row["import"] = counts
            except Exception as exc:  # noqa: BLE001
                print(f"    IMPORT FAILED: {exc}")
                log["errors"].append({"id": rid, "error": f"import: {exc}"})

            if args.copy_media:
                ok, msg = copy_media(rid)
                print(f"    copy-media: {'OK' if ok else 'FAIL'} {msg[:90]}")
                row["copy_media"] = ok

        after = client._get(f"robots/robots/{rid}/")
        row["after"] = {
            "company": (after.get("company_ref") or {}).get("id"),
            "name": after.get("name"),
            "payload_kg": after.get("payload_kg"),
            "family_key": after.get("family_key"),
            "purpose_lines": len((after.get("purpose") or "").splitlines()),
            "photos": len(after.get("photos") or []),
            "image": bool(after.get("s3_image") or after.get("image")),
            "availability": (after.get("availability_status") or {}).get("key"),
            "release_year": after.get("release_year"),
        }
        print(f"    -> {json.dumps(row['after'], ensure_ascii=False)}")
        print()
        log["robots"].append(row)
        time.sleep(0.4)

    REPORT.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"robots={len(log['robots'])} errors={len(log['errors'])}")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
