"""Backfill Ecovacs DEEBOT robot vacuums (company 32) — greenfield pending_review.

Curated fixer modeled on ``fix_irobot_robots.py`` (company 342, the closest
consumer robot-vacuum analog). Each target is a blank pending_review record; we
gap-fill photo (>=4), features, cited specs, release_year (with citation), price,
tags, and a title-verified official/review video.

Sourcing policy (per run brief + coordinator clarification):
- Hard specs (suction Pa / battery mAh / airflow) come from Ecovacs product pages.
- release_year, price, availability corroborated by reputable tech press
  (Vacuum Wars, The Verge, PCMag, eftm, prnewswire/CES-IFA coverage).
- Every OEM + third-party source rides in ``sources`` so the server upserts
  RobotInformationSource and stamps ``enriched_at``.
- Never invent specs: runtime/weight/dimensions left blank where not cleanly cited.

Only the 6 ids in ROBOT_DATA are touched (exact pk patch). Published records
(X5 OMNI 1937, X9 PRO OMNI 1939, ...) are never in scope. Leaves status
pending_review.

    python fix_ecovacs_robots.py                     # dry-run preview
    python fix_ecovacs_robots.py --apply --copy-media
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
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

COMPANY_ID = 32
COMPANY_SLUG = "ecovacs-robotics"
COMPANY_NAME = "Ecovacs Robotics"
IMG = "https://site-static.ecovacs.com/upload"
SKIP_STATUSES = {"published", "approved"}

# TagCatalog-exact names, per product family. Do NOT reuse vacuum tags on the
# mower / window / commercial records — GOAT is a lawn mower, WINBOT a
# window-cleaning robot, and K1/M1 are B2B floor care.
TAGS_VACUUM = "Robot Vacuum|Home Cleaning|Cleaning|Smart Home|AI|Autonomous|Wheeled|Ground|Navigation|Consumer"
TAGS_MOWER = "Outdoor|All-Terrain|Autonomous|AI|Navigation|Wheeled|Ground|Smart Home|Consumer"
TAGS_WINDOW = "Cleaning|Home Cleaning|Smart Home|AI|Autonomous|Navigation|Consumer|Indoor"
TAGS_COMMERCIAL_VAC = (
    "Robot Vacuum|Cleaning|Commercial|Professional|Service Robot|"
    "Autonomous Mobile Robot|AI|Navigation|Wheeled|Ground|Indoor"
)
TAGS_COMMERCIAL_SCRUB = (
    "Cleaning|Commercial|Professional|Service Robot|"
    "Autonomous Mobile Robot|AI|Navigation|Wheeled|Ground|Indoor"
)

# Curated, verified data keyed by DB robot id (exact pk patch — no name collision).
# image[0] = hero (visually confirmed device-in-frame via download+Read).
ROBOT_DATA: dict[int, dict[str, Any]] = {
    4720: {
        "name": "DEEBOT mini 2",
        "url": "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-mini-2-white",
        "description": (
            "Compact all-in-one robotic vacuum and mop with a mini OMNI Station, "
            "10,000Pa suction, ZeroTangle 4.0 anti-tangle, OZMO Turbo 2.0 mopping, "
            "and TrueMapping 2.0 + TrueDetect 3D navigation."
        ),
        "features": (
            "10,000Pa powerful suction | ZeroTangle 4.0 anti-tangle system | "
            "OZMO Turbo 2.0 intensive mopping | TrueMapping 2.0 laser mapping and "
            "TrueDetect 3D obstacle avoidance | Ultra-compact body for extreme "
            "mobility in small spaces | Space-saving all-in-one mini OMNI Station | "
            "Superior noise control (~55dB) | Up to 189 minutes runtime on a "
            "3,200mAh battery"
        ),
        "suction_pa": "10,000Pa",
        "battery_wh": None,
        "battery_capacity": "3200mAh",
        "runtime_minutes": 189,
        "release_year": 2026,
        "year_cite": (
            "release_year=2026: Introduced by ECOVACS in 2026 (site (c) 2026; "
            "SG launch Mar 2026; showcased at CES 2026, Las Vegas)."
        ),
        "video_ids": ["fLih5mPlHKc"],
        "sources": [
            {"url": "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-mini-2-white",
             "type": "website", "title": "DEEBOT mini 2 — ECOVACS Global (specs)"},
            {"url": "https://www.prnewswire.com/news-releases/ecovacs-showcases-its-acceleration-towards-full-scenario-service-robotics-at-ces-2026-302653595.html",
             "type": "press", "title": "ECOVACS at CES 2026 (PR Newswire)"},
        ],
        "images": [
            f"{IMG}/image/product/2026/04/14/021100_2373$mini2-01_compressed.jpeg",
            f"{IMG}/image/product/2026/04/14/021114_3873$mini2-03_compressed.jpeg",
            f"{IMG}/image/product/2026/04/14/021125_5325$mini2-04_compressed.jpeg",
            f"{IMG}/image/product/2026/04/14/021138_4750$mini2-05_compressed.jpeg",
            f"{IMG}/image/product/2026/04/14/021153_4370$mini2-07_compressed.jpeg",
            f"{IMG}/image/product/2026/04/14/021217_8305$mini2-10_compressed.jpeg",
        ],
    },
    4717: {
        "name": "DEEBOT T80 OMNI BLACK",
        "url": "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-t80-omni-black",
        "description": (
            "Flagship robotic vacuum and mop (black) with OZMO ROLLER self-cleaning "
            "mopping, ZeroTangle 3.0 anti-tangle, TruEdge 2.0 edge cleaning, and "
            "18,000Pa suction, paired with a compact OMNI Station with 45C hot-air "
            "mop drying."
        ),
        "features": (
            "OZMO ROLLER mopping technology with high-speed scrubbing and rinsing | "
            "18,000Pa suction power | ZeroTangle 3.0 tangle-free system | "
            "TruEdge 2.0 adaptive edge and corner cleaning | AI Instant Re-Mop 2.0 "
            "for tough stains | Real-time path planning obstacle avoidance | "
            "OMNI Station with 45C hot-air drying and 150-day maintenance-free mop "
            "washing tray"
        ),
        "suction_pa": "18,000Pa",
        "battery_capacity": "",
        "runtime_minutes": None,
        "release_year": 2025,
        "year_cite": (
            "release_year=2025: Ecovacs announced the T80 OMNI (with X9 PRO OMNI) "
            "for a mid-May 2025 release (Vacuum Wars)."
        ),
        "video_ids": ["7slMEZWIbTw"],
        "sources": [
            {"url": "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-t80-omni-black",
             "type": "website", "title": "DEEBOT T80 OMNI BLACK — ECOVACS Global (specs)"},
            {"url": "https://vacuumwars.com/ecovacs-expands-deebot-lineup-with-two-new-ozmo-roller-models/",
             "type": "review", "title": "Ecovacs Expands Deebot Lineup with OZMO Roller Models (Vacuum Wars)"},
        ],
        "images": [
            f"{IMG}/image/product/2025/04/09/105423_9671$T8003.jpg",
            f"{IMG}/image/product/2025/04/09/105344_7236$T8004.jpg",
            f"{IMG}/image/product/2025/04/09/105353_1540$T8006.jpg",
            f"{IMG}/image/product/2025/04/09/105158_9726$T8008.jpg",
            f"{IMG}/image/product/2025/04/09/105219_5526$T8010.jpg",
            f"{IMG}/image/product/2025/04/09/105529_9485$T8018.jpg",
        ],
    },
    4718: {
        "name": "DEEBOT T50 MAX PRO OMNI BLACK",
        "url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-t50-max-pro-omni",
        "description": (
            "Robotic vacuum and mop (black) featuring BLAST large-airflow suction "
            "(34.5 CFM x 18,500Pa) driven by a 100W high-torque motor and an "
            "EV-grade pouch battery, TruEdge 2.0 edge cleaning, and a 12-in-1 "
            "OMNI Station with hot-water mop washing and drying."
        ),
        "features": (
            "BLAST large-airflow suction: 34.5 CFM airflow x 18,500Pa | "
            "100W high-performance motor with improved aerodynamic design | "
            "Industry-first EV-grade pouch battery (2.4x lifespan) | "
            "78% increase in carpet cleaning efficacy; 100% large-particle pickup | "
            "TruEdge 2.0 complete edge and corner cleaning | dToF LiDAR navigation "
            "with obstacle avoidance | 12-in-1 OMNI Station: hot-water mop wash, "
            "drying, auto-empty and refill | Up to ~200 min runtime (6,400mAh battery)"
        ),
        "suction_pa": "18,500Pa",
        "battery_capacity": "6400mAh",
        "runtime_minutes": 200,
        "release_year": 2025,
        "year_cite": (
            "release_year=2025: DEEBOT T50 Series unveiled at CES 2025 "
            "(Jan 6, 2025) per ECOVACS/PR Newswire; reviewed 2025 (Vacuum Wars)."
        ),
        "video_ids": ["HLDfHNUwqG4"],
        "sources": [
            {"url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-t50-max-pro-omni",
             "type": "website", "title": "DEEBOT T50 MAX PRO OMNI — ECOVACS US (specs)"},
            {"url": "https://vacuumwars.com/t50-max-pro-omni-and-t50-pro/",
             "type": "review", "title": "Ecovacs T50 Max Pro Omni vs T50 Pro Omni — official specs (Vacuum Wars)"},
            {"url": "https://www.prnewswire.com/news-releases/ecovacs-unveils-next-gen-smart-home-robotic-vacuum-cleaners-and-beyond-at-ces-2025-302342025.html",
             "type": "press", "title": "ECOVACS unveils next-gen robot vacuums at CES 2025 (PR Newswire)"},
        ],
        "images": [
            f"{IMG}/us/image/product/2025/09/16/075219_7694$id-t50-max-pro-omni-black-920x920.png",
            f"{IMG}/us/image/product/2025/05/29/031504_8701$us-2t50-max-pro-omni-black-1280x1280.jpg",
            f"{IMG}/us/image/product/2025/04/22/051309_2004$3DEEBOT-T50-MAX-PRO-OMNI-Black-1280x1280.jpg",
            f"{IMG}/us/image/product/2025/04/22/051322_5705$4DEEBOT-T50-MAX-PRO-OMNI-Black-1280x1280.jpg",
            f"{IMG}/us/image/product/2025/04/22/051328_9100$5DEEBOT-T50-MAX-PRO-OMNI-Black-1280x1280.jpg",
            f"{IMG}/us/image/product/2025/04/22/051336_5356$6DEEBOT-T50-MAX-PRO-OMNI-Black-1280x1280.jpg",
        ],
    },
    4719: {
        "name": "DEEBOT T50 OMNI Black",
        "url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-t50-omni",
        "description": (
            "Ultra-thin (3.19 in / 81mm) robotic vacuum and mop (black) with "
            "15,000Pa suction, ZeroTangle 2.0 anti-tangle, TruEdge 2.0 adaptive "
            "edge cleaning, OZMO Turbo 2.0 mopping, TrueMapping 2.0 navigation, and "
            "the YIKO-GPT AI voice assistant, paired with a self-cleaning OMNI Station."
        ),
        "features": (
            "3.19-inch ultra-thin body reaches under low furniture | "
            "15,000Pa powerful suction | ZeroTangle 2.0 anti-tangle technology | "
            "TruEdge 2.0 adaptive edge cleaning | OZMO Turbo 2.0 mopping with "
            "auto-lift and carpet cleaning strategy | TrueMapping 2.0 precise "
            "navigation | YIKO-GPT AI voice assistant | OMNI Station with automatic "
            "self-cleaning, hot-wash and drying"
        ),
        "suction_pa": "15,000Pa",
        "battery_capacity": "",
        "runtime_minutes": None,
        "release_year": 2025,
        "year_cite": (
            "release_year=2025: DEEBOT T50 Series unveiled at CES 2025 "
            "(Jan 6, 2025); T50 OMNI reviewed/launched 2025 (eftm)."
        ),
        "video_ids": ["gOvg3w5K2kM"],
        "sources": [
            {"url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-t50-omni",
             "type": "website", "title": "DEEBOT T50 OMNI — ECOVACS US (specs)"},
            {"url": "https://www.prnewswire.com/news-releases/ecovacs-unveils-next-gen-smart-home-robotic-vacuum-cleaners-and-beyond-at-ces-2025-302342025.html",
             "type": "press", "title": "ECOVACS unveils next-gen robot vacuums at CES 2025 (PR Newswire)"},
        ],
        "images": [
            f"{IMG}/us/image/product/2025/09/18/055640_2492$id-t50-omni-black-920x920.png",
            f"{IMG}/us/image/product/2025/04/22/050921_6116$02DEEBOT-T50-OMNI-Black-1280x1280.jpg",
            f"{IMG}/us/image/product/2025/04/22/050926_3240$03DEEBOT-T50-OMNI-Black-1280x1280.jpg",
            f"{IMG}/us/image/product/2025/04/22/050931_9697$04DEEBOT-T50-OMNI-Black-1280x1280.jpg",
            f"{IMG}/us/image/product/2025/04/22/050936_1710$05DEEBOT-T50-OMNI-Black-1280x1280.jpg",
            f"{IMG}/us/image/product/2025/05/29/033541_6522$us-06deebot-t50-omni-black-1280x1280.jpg",
        ],
    },
    4681: {
        "name": "DEEBOT X11 OmniCyclone",
        "url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-x11-omnicyclone",
        "description": (
            "Bagless flagship robotic vacuum and mop with 38 CFM airflow and "
            "19,500Pa BLAST suction, PowerBoost fast charging, OZMO ROLLER 2.0 "
            "self-washing mop, and AI stain detection, paired with the world-first "
            "OmniCyclone bagless self-emptying station."
        ),
        "features": (
            "High airflow (38 CFM) x 19,500Pa BLAST suction | PowerBoost fast-charge "
            "technology (restores 6% in 3 min for nonstop cleaning) | OZMO ROLLER 2.0 "
            "edge-to-edge streak-free mopping with Triple Lift System | "
            "TruEdge 3.0 extreme edge cleaning | AI stain detection | ZeroTangle 3.0 "
            "anti-tangle | World's first OmniCyclone bagless station (no bags, no "
            "extra costs) with hot-water soak washing | 6,400mAh battery"
        ),
        "suction_pa": "19,500Pa",
        "battery_capacity": "6400mAh",
        "runtime_minutes": None,
        "release_year": 2025,
        "year_cite": (
            "release_year=2025: DEEBOT X11 OmniCyclone unveiled at IFA 2025, "
            "Berlin (Sept 2025) per Vacuum Wars / Android Headlines; Ecovacs says "
            "released late 2025 (Gizmodo)."
        ),
        "price_max": 1099.99,
        "price_currency": "USD",
        "price_notes": "US MSRP $1,099.99 (ECOVACS US regular price).",
        "video_ids": ["HLHfzR8shvw", "lo6mZiaUfnI"],
        "sources": [
            {"url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-x11-omnicyclone",
             "type": "website", "title": "DEEBOT X11 OmniCyclone — ECOVACS US (specs + price)"},
            {"url": "https://vacuumwars.com/ecovacs-deebot-x11-omnicyclone-ifa2025/",
             "type": "review", "title": "Ecovacs Unveils Deebot X11 OmniCyclone at IFA 2025 (Vacuum Wars)"},
            {"url": "https://www.androidheadlines.com/best-of-ifa-2025-ecovacs-deebot-x11-omnicyclone",
             "type": "review", "title": "Best of IFA 2025: Ecovacs Deebot X11 Omnicyclone (Android Headlines)"},
        ],
        "images": [
            f"{IMG}/us/image/product/2025/09/15/071438_3338$deebot-x11-omnicyclone-new-arrival-920x920-3.png",
            f"{IMG}/us/image/product/2025/08/21/014801_4490$2.jpg",
            f"{IMG}/us/image/product/2025/08/21/014849_5898$3.jpg",
            f"{IMG}/us/image/product/2025/08/21/015002_1666$4.jpg",
            f"{IMG}/us/image/product/2025/08/21/015038_3530$5.jpg",
            f"{IMG}/us/image/product/2025/08/21/015119_1694$6.jpg",
        ],
    },
    4676: {
        "name": "DEEBOT X12 OmniCyclone",
        "url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-x12-omnicyclone",
        "description": (
            "Bagless flagship robotic vacuum and mop, the first with FocusJet "
            "pre-treatment technology, delivering BLAST suction up to 22,000Pa "
            "(22L/s airflow), OZMO ROLLER 3.0 self-washing mop with smart cover and "
            "lifting, ZeroTangle 4.0 anti-tangle, PowerBoost Charging Plus, and the "
            "OmniCyclone bagless station."
        ),
        "features": (
            "First robotic vacuum with FocusJet pre-treatment technology | "
            "BLAST suction up to 22,000Pa with 22L/s airflow | OZMO ROLLER 3.0 mop "
            "with smart cover and roller lifting | TruEdge 3.0 edge cleaning with "
            "TruePass agile mobility | ZeroTangle 4.0 anti-tangle | PowerBoost "
            "Charging Plus (restores 13% in 3 min) | AIVI 3D obstacle avoidance | "
            "OmniCyclone bagless station with fresh-flow power washing and dirty-water "
            "box auto-cleaning | 4,000mAh battery"
        ),
        "suction_pa": "22,000Pa",
        "battery_capacity": "4000mAh",
        "runtime_minutes": None,
        "release_year": 2026,
        "year_cite": (
            "release_year=2026: DEEBOT X12 OmniCyclone shown at CES 2026 and "
            "released Mar 31, 2026 (ECOVACS support listing); reviewed Apr 2026 "
            "(PCMag, The Verge)."
        ),
        "price_max": 1499.99,
        "price_currency": "USD",
        "price_notes": "US MSRP $1,499.99 (ECOVACS US / Best Buy / Target regular price; PCMag street $1,499).",
        "video_ids": ["vqyAzuY_-6A"],
        "sources": [
            {"url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-x12-omnicyclone",
             "type": "website", "title": "DEEBOT X12 OmniCyclone — ECOVACS US (specs + price)"},
            {"url": "https://www.theverge.com/tech/910298/ecovacs-deebot-x12-omnicyclone-robot-vacuum-mop-pretreat-ai",
             "type": "review", "title": "Ecovacs' new robovac spots and pretreats stains (The Verge)"},
            {"url": "https://me.pcmag.com/en/robot-vacuums/36560/ecovacs-deebot-x12-omnicyclone",
             "type": "review", "title": "Ecovacs Deebot X12 OmniCyclone Review 2026 (PCMag)"},
            {"url": "https://vacuumwars.com/ecovacs-x12-review/",
             "type": "review", "title": "Ecovacs X12 OmniCyclone Review: New Flagship Tested (Vacuum Wars)"},
        ],
        "images": [
            f"{IMG}/us/image/product/2026/04/09/073137_2213$deebot-x12-omnicyclone-2-920x920.png",
            f"{IMG}/image/product/2026/03/23/031017_6177$X12-OC_listingpage_01.jpg",
            f"{IMG}/image/product/2026/03/23/031100_8216$X12-OC_listingpage_02.jpg",
            f"{IMG}/image/product/2026/03/23/031251_9912$X12-OC_listingpage_03.jpg",
            f"{IMG}/image/product/2026/03/23/031412_6591$X12-OC_listingpage_04.jpg",
            f"{IMG}/image/product/2026/03/23/031437_1565$X12-OC_listingpage_05.jpg",
        ],
    },
    # ---------------- batch 2 ----------------
    4716: {
        "name": "DEEBOT T90 OMNI BLACK",
        "url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-t90-omni",
        "description": (
            "Robotic vacuum and mop (black) with 30,000Pa BLAST suction, OZMO ROLLER 3.0 "
            "instant self-cleaning roller mop, ZeroTangle 4.0 anti-tangle, TruEdge 3.0 "
            "edge cleaning, AIVI 3D 4.0 obstacle avoidance and a TruePass adaptive "
            "4-wheel-drive climbing system, paired with a self-maintaining OMNI Station."
        ),
        "purpose": (
            "Automates everyday floor cleaning in the home — vacuuming and mopping hard "
            "floors and carpets, then self-emptying, washing and drying its own mop at "
            "the OMNI Station so the user does not handle dust or dirty water."
        ),
        "features": (
            "30,000Pa BLAST suction | OZMO ROLLER 3.0 instant self-cleaning roller mop | "
            "ZeroTangle 4.0 anti-tangle system | TruEdge 3.0 edge and corner cleaning | "
            "AIVI 3D 4.0 AI obstacle avoidance | TruePass adaptive 4-wheel-drive climbing "
            "system for thresholds | All-dimensional noise reduction | Self-maintaining "
            "OMNI Station (auto-empty, hot-water mop wash and drying)"
        ),
        "suction_pa": "30,000Pa",
        "release_year": 2026,
        "year_cite": (
            "release_year=2026: DEEBOT T90 family unveiled at CES 2026 (Jan 6-9, 2026; "
            "PR Newswire + ECOVACS CES 2026 highlights page). Family-level citation - the "
            "CES release names the T90 PRO OMNI; the T90 OMNI US listing and product "
            "assets are dated 2026."
        ),
        "tags": TAGS_VACUUM,
        "video_ids": ["zGd273-Gk6A"],
        "sources": [
            {"url": "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-t90-omni",
             "type": "website", "title": "DEEBOT T90 OMNI - ECOVACS US (specs, 30,000Pa)"},
            {"url": "https://www.ecovacs.com/global/campaign/ces-deebot",
             "type": "website", "title": "ECOVACS CES 2026 Highlights - DEEBOT"},
            {"url": "https://www.prnewswire.com/news-releases/ecovacs-showcases-its-acceleration-towards-full-scenario-service-robotics-at-ces-2026-302653595.html",
             "type": "press", "title": "ECOVACS at CES 2026 (PR Newswire)"},
        ],
        "images": [
            f"{IMG}/us/image/product/2026/07/16/033310_4782$deebot-t90-black-920x920.png",
            f"{IMG}/image/product/2026/02/09/020655_5418$1.jpg",
            f"{IMG}/image/product/2026/02/09/020808_6545$2.jpg",
            f"{IMG}/image/product/2026/02/09/020908_4046$3.jpg",
            f"{IMG}/image/product/2026/02/09/020953_7971$4.jpg",
            f"{IMG}/image/product/2026/02/09/021226_5383$5.jpg",
        ],
    },
    4715: {
        "name": "DEEBOT X9 PRO OMNI BLACK",
        "url": "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-x9-pro-omni-black",
        "description": (
            "Dual-powered flagship robotic vacuum and mop (black) combining BLAST "
            "large-airflow suction (16,600Pa) with OZMO ROLLER self-washing mopping, "
            "TruEdge 2.0 plus a 3D edge sensor, AIVI 3D 3.0 omni-approach obstacle "
            "avoidance and AI Stain Detection 2.0."
        ),
        "purpose": (
            "Flagship whole-home floor care — vacuums and wet-mops in a single pass, "
            "detects and re-cleans stains, and handles its own emptying, mop washing "
            "and drying at the OMNI Station for hands-free daily cleaning."
        ),
        "features": (
            "BLAST solution delivering 16,600Pa suction | OZMO ROLLER self-washing "
            "mopping technology | TruEdge 2.0 with 3D edge sensor for perfect edge "
            "cleaning | Triple Lift with precision dry-wet separation | AIVI 3D 3.0 "
            "omni-approach obstacle avoidance | AI Stain Detection 2.0 | Real-time path "
            "planning | Dedicated carpet care | 6,400mAh battery"
        ),
        "suction_pa": "16,600Pa",
        "battery_capacity": "6400mAh",
        "release_year": 2025,
        "year_cite": (
            "release_year=2025: Ecovacs announced the X9 PRO OMNI (with the T80 OMNI) "
            "for a mid-May 2025 release (Vacuum Wars)."
        ),
        "tags": TAGS_VACUUM,
        "video_ids": ["18x7YoVazF8"],
        "sources": [
            {"url": "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-x9-pro-omni-black",
             "type": "website", "title": "DEEBOT X9 PRO OMNI BLACK - ECOVACS Global (specs)"},
            {"url": "https://vacuumwars.com/ecovacs-expands-deebot-lineup-with-two-new-ozmo-roller-models/",
             "type": "review", "title": "Ecovacs Expands Deebot Lineup with OZMO Roller Models - mid-May 2025 (Vacuum Wars)"},
        ],
        "images": [
            f"{IMG}/us/image/product/2025/09/10/074643_3821$id-x9-pro-omni-black-920x920.png",
            f"{IMG}/image/product/2025/04/24/022221_9944$02.jpg",
            f"{IMG}/image/product/2025/04/24/022500_1353$03.jpg",
            f"{IMG}/image/product/2025/04/24/023500_2679$04.jpg",
            f"{IMG}/image/product/2025/04/24/023721_4064$05.jpg",
            f"{IMG}/image/product/2025/04/24/023818_1885$06.jpg",
        ],
    },
    4680: {
        "name": "GOAT A3000 LiDAR PRO",
        "url": "https://www.ecovacs.com/us/shop/goat-robotic-lawn-mower/goat-a3000-lidar-pro",
        "description": (
            "Wire-free robotic lawn mower with HoloScope 360 dual-LiDAR navigation and "
            "AIVI 3D obstacle avoidance. ECOVACS' first trimmer-integrated mower, it "
            "runs a 32V platform with dual blade-discs, a 33cm cutting path and "
            "TrueEdge precision edge cutting."
        ),
        "purpose": (
            "Autonomously mows and edge-trims a domestic lawn without boundary wires - "
            "maps the garden with dual LiDAR, plans efficient routes, cuts right to the "
            "edge, avoids obstacles and returns to its station to recharge."
        ),
        "features": (
            "HoloScope 360 dual-LiDAR navigation, wire-free setup | ECOVACS' first "
            "trimmer-integrated robotic lawn mower with TrueEdge precision edge cutting | "
            "32V platform with dual blade-discs, 3,000rpm cutting motor | 33cm cutting "
            "width; mowing efficiency 250-400 m2/h at up to 0.7 m/s | Electric cutting "
            "height adjustable 30-90mm (1.18-3.54 in) | AIVI 3D obstacle avoidance | "
            "Slope climbing up to 50% (27 degrees) | 7,500mAh battery with 189W fast "
            "charging (full in 70 min) | IPX6 rated body; 62 dBA main body noise"
        ),
        "suction_pa": "",
        "battery_capacity": "7500mAh",
        "charging_time_minutes": 70,
        "weight_kg": 18.3,
        "dimensions_mm": "680x540x336",
        "length_mm": 680.0,
        "width_mm": 540.0,
        "height_mm": 336.0,
        "ip_rating": "IPX6",
        "speed_ms": 0.7,
        "voltage": "32V",
        "release_year": 2026,
        "year_cite": (
            "release_year=2026: GOAT A3000 LiDAR PRO is the 2026 GOAT lineup refresh - "
            "OEM listing and product assets dated Jan-Feb 2026; 2026 pricing coverage "
            "(9to5toys, Jun 2026) and 2026 review coverage. The non-PRO A3000 LiDAR is "
            "the earlier 2025 model."
        ),
        "tags": TAGS_MOWER,
        "movement": "wheeled",
        "video_ids": ["35EDv8EUp_8"],
        "sources": [
            {"url": "https://www.ecovacs.com/us/shop/goat-robotic-lawn-mower/goat-a3000-lidar-pro",
             "type": "website", "title": "GOAT A3000 LiDAR PRO - ECOVACS US (full spec table)"},
            {"url": "https://9to5toys.com/2026/06/23/ecovacs-goat-lidar-pro-robot-lawn-mowers-prime-day-from-1000/",
             "type": "press", "title": "ECOVACS Goat LiDAR Pro robot lawn mowers - 2026 pricing (9to5toys)"},
        ],
        "images": [
            f"{IMG}/us/image/product/2026/02/10/010750_6791$id-goat-a3000-lidar-pro-920x920-1.png",
            f"{IMG}/image/product/2026/01/26/062352_3818$1.jpg",
            f"{IMG}/image/product/2026/01/26/062442_8593$2.jpg",
            f"{IMG}/image/product/2026/01/26/063314_3976$3.jpg",
            f"{IMG}/image/product/2026/01/26/063344_5901$4.jpg",
            f"{IMG}/image/product/2026/01/26/063414_7072$5.jpg",
        ],
    },
    4677: {
        "name": "WINBOT W3 OMNI",
        "url": "https://www.ecovacs.com/us/shop/winbot-window-cleaning-robot/winbot-w3-omni",
        "description": (
            "Window-cleaning robot with a multi-functional station featuring Vortex "
            "Wash - the industry's first contact-free wiping-pad washing. Uses WIN-SLAM "
            "5.0 navigation, 10,000Pa adsorption, TruEdge edge-to-edge cleaning, dual "
            "power modes and an anti-dropping safety mechanism."
        ),
        "purpose": (
            "Cleans household windows and glass surfaces automatically - adheres to the "
            "glass, maps and covers the pane edge to edge, and returns to its station to "
            "wash and dry its own wiping pad, removing the need to clean windows by hand "
            "or at height."
        ),
        "features": (
            "Vortex Wash - industry's first contact-free wiping pad washing | Station "
            "self-cleaning, always ready | 10,000Pa adsorption power | WIN-SLAM 5.0 "
            "intelligent navigation | TruEdge edge-to-edge cleaning without "
            "cross-contamination | Dual power modes (corded and battery) for flexibility | "
            "Two-in-one compound cable with safety and power cords | Anti-dropping "
            "protection mechanism | Up to 110 minutes of battery operation"
        ),
        "suction_pa": "10,000Pa",
        "runtime_minutes": 110,
        "release_year": 2026,
        "year_cite": (
            "release_year=2026: WINBOT W3 OMNI reviewed in 2026 (Gizmodo, 'Ecovacs "
            "Winbot W3 Omni Review'); OEM US listing and product assets dated Jan 2026."
        ),
        "price_max": 699.99,
        "price_currency": "USD",
        "price_notes": "US MSRP $699.99 (ECOVACS US regular price; Gizmodo review cites ~$700).",
        "tags": TAGS_WINDOW,
        # Glass-adhering climbing robot - not a ground/wheeled platform.
        "movement": "other",
        "video_ids": ["lQFuYnfe8Vw"],
        "sources": [
            {"url": "https://www.ecovacs.com/us/shop/winbot-window-cleaning-robot/winbot-w3-omni",
             "type": "website", "title": "WINBOT W3 OMNI - ECOVACS US (specs + price)"},
            {"url": "https://gizmodo.com/ecovacs-winbot-w3-omni-review-window-cleaning-robots-have-a-long-way-to-go-2000735555",
             "type": "review", "title": "Ecovacs Winbot W3 Omni Review (Gizmodo)"},
        ],
        "images": [
            f"{IMG}/image/product/2026/01/26/034208_3138$5-1.jpg",
            f"{IMG}/image/product/2026/01/26/034236_9217$6-1.jpg",
            f"{IMG}/image/product/2026/01/26/034145_1124$9-1.jpg",
            f"{IMG}/image/product/2026/01/26/034227_4128$13-1.jpg",
            f"{IMG}/image/product/2026/01/26/034313_3119$32-1.jpg",
        ],
    },
    4678: {
        "name": "ECOVACS Commercial Robot Vacuum DEEBOT PRO K1 VAC",
        "url": "https://www.ecovacscommercial.com/ecovacs-commercial-robot-vacuum-deebot-pro-k1-vac",
        "description": (
            "Commercial 3-in-1 autonomous robot vacuum for B2B facilities. Combines "
            "vacuuming, sweeping and dust-mopping with 20kPa direct suction, a 10L "
            "dustbin and a narrow 42cm body, delivering up to 4 hours of vacuuming or "
            "8 hours of dust-mopping per charge."
        ),
        "purpose": (
            "Automates large-area floor and carpet cleaning in commercial buildings - "
            "hotels, offices, cinemas, stadiums, convention centres and places of "
            "worship - vacuuming, sweeping and dust-mopping unattended so cleaning staff "
            "are freed from repetitive coverage work."
        ),
        "features": (
            "3-in-1: vacuum, sweep and dust-mop in one robot | 20kPa powerful direct "
            "suction | 10L large-capacity dustbin for reduced emptying | Narrow 42cm "
            "compact body navigates hotel aisles and tight spaces | Up to 4h vacuuming / "
            "8h dust-mopping runtime; 1.5h charging | Side brush for true edge cleaning "
            "into corners | Anti-tangle design | Max cleaning efficiency 700 m2/h at up "
            "to 1.2 m/s | Certified to CQC, CB, CE and KC standards"
        ),
        "suction_pa": "20,000Pa (20kPa)",
        "runtime_minutes": 240,
        "charging_time_minutes": 90,
        "weight_kg": 46.0,
        "dimensions_mm": "558x420x592",
        "length_mm": 558.0,
        "width_mm": 420.0,
        "height_mm": 592.0,
        "speed_ms": 1.2,
        "release_year": 2025,
        "year_cite": (
            "release_year=2025: DEEBOT PRO K1 VAC 'Released on: 31 March 2025' per the "
            "Interclean Amsterdam official exhibitor product listing for ECOVACS "
            "Commercial Robotics."
        ),
        "tags": TAGS_COMMERCIAL_VAC,
        "video_ids": ["Q8hCOowYmvc"],
        "sources": [
            {"url": "https://www.ecovacscommercial.com/ecovacs-commercial-robot-vacuum-deebot-pro-k1-vac",
             "type": "website", "title": "DEEBOT PRO K1 VAC - ECOVACS Commercial (official spec table)"},
            {"url": "https://www.intercleanshow.com/products-and-services/ecovacs-commercial-robotics/products/deebot-pro-k1-vac",
             "type": "press", "title": "DEEBOT PRO K1 VAC - Interclean exhibitor listing (release date 31 Mar 2025)"},
            {"url": "https://www.ecovacs.com/global/campaign/k1",
             "type": "website", "title": "DEEBOT PRO K1 VAC - ECOVACS Global campaign"},
        ],
        "images": [
            "https://shopcdnalpha.grainajz.com/category/433863/3365/973e37c126efcc3fc3ae9f2c6acccaef/%E4%B8%BB%E5%9B%BE1.png",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/cfe475ae37f07f98ccfcb92d1e20e4c1/%E4%B8%BB%E5%9B%BE2.jpg",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/98ae52124e72a406a530b2fdaeb66a8e/%E4%B8%BB%E5%9B%BE3.png",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/0fd340f1698063eea816f3936fa7da29/%E4%B8%BB%E5%9B%BE4.jpg",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/564cbbed47811fc5cf1dd355ac06931a/%E4%B8%BB%E5%9B%BE5.jpg",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/7e47132c09275fc695d6dab82553f8e8/k1vac.jpg",
        ],
    },
    4679: {
        "name": "ECOVACS Commercial Robotic Floor Scrubber DEEBOT PRO M1",
        "url": "https://www.ecovacscommercial.com/ecovacs-commercial-robotic-floor-scrubber-deebot-pro-m1",
        "description": (
            "Commercial autonomous floor scrubber that integrates scrubbing, sweeping "
            "and dust-mopping in one unit. Covers up to 4,200 m2 scrubbing or 9,600 m2 "
            "dust-mopping per charge, with automatic detergent dosing, a self-cleaning "
            "sewage tank, auto water refill/drain and AI obstacle avoidance."
        ),
        "purpose": (
            "Replaces manual scrubbing rounds in large commercial and public buildings - "
            "offices, universities, libraries, hospitals, malls, stations and airports - "
            "by autonomously scrubbing, sweeping and dust-mopping hard floors, recovering "
            "water for instantly walkable results, and refilling, draining and recharging "
            "itself between shifts."
        ),
        "features": (
            "All-in-one: scrub, sweep and dust-mop in a single unit | Up to 4,200 m2 "
            "scrubbing or 9,600 m2 dust-mopping per charge | Up to 3.5h scrubbing / 8h "
            "dust-mopping runtime | Multi-stage pass: sweep, spray, scrub, squeegee, then "
            "high-power suction dry for near-zero residue - instantly walkable floors | "
            "Automatic detergent mixing and dosing (2L detergent cleans 5+ tankfuls) | "
            "Roller brush options for 10+ floor types (marble, tile, PVC, epoxy) | "
            "Self-cleaning sewage tank with triple-sealed, anti-corrosion construction | "
            "Auto-recharge (2.5h), auto water refill and drain (<=10 min) | IoT-enabled: "
            "autonomous elevator riding and security gate/door access | Smart re-cleaning "
            "of temporarily blocked areas | Certified to CB, CE, TELEC, KC, CQC and NCC"
        ),
        "suction_pa": "",
        "runtime_minutes": 210,
        "charging_time_minutes": 150,
        "release_year": 2023,
        "year_cite": (
            "release_year=2023: DEEBOT PRO M1 'Released on: 31 March 2023' per the "
            "Interclean Amsterdam official exhibitor product listing; the DEEBOT PRO "
            "K1/M1 series debuted at the 2023 CCE Cleaning Exhibition (ECOVACS Group)."
        ),
        "tags": TAGS_COMMERCIAL_SCRUB,
        "video_ids": ["dMCQBVmmTCI"],
        "sources": [
            {"url": "https://www.ecovacscommercial.com/ecovacs-commercial-robotic-floor-scrubber-deebot-pro-m1",
             "type": "website", "title": "DEEBOT PRO M1 - ECOVACS Commercial (official product page)"},
            {"url": "https://www.intercleanshow.com/products-and-services/ecovacs-commercial-robotics/products/deebot-pro-m1",
             "type": "press", "title": "DEEBOT PRO M1 - Interclean exhibitor listing (release date 31 Mar 2023)"},
            {"url": "https://www.ecovacsgroup.com/en/service/commercial-robot",
             "type": "website", "title": "ECOVACS Group - DEEBOT PRO K1/M1 debut at 2023 CCE Cleaning Exhibition"},
        ],
        "images": [
            "https://shopcdnalpha.grainajz.com/category/433863/3365/f5fa7fc8bd9614b56046acc35984ff4a/M1.jpg",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/8cee8bacdadd544f3ca0ecb6c6308eda/%E4%B8%BB%E5%9B%BE1.jpg",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/392f6ccf349c5993b28b43fc904da939/%E4%B8%BB%E5%9B%BE2.jpg",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/6ff519c4b972cd382a946879c94f79ec/%E4%B8%BB%E5%9B%BE3.jpg",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/c6d34dd3145ceccdcabbe29ed12e1173/%E4%B8%BB%E5%9B%BE4.jpg",
            "https://shopcdnalpha.grainajz.com/category/433863/3365/66c5d57ff89c03f19cd181a2fdc5b39d/%E4%B8%BB%E5%9B%BE5.jpg",
        ],
    },
}

# Optional typed spec fields copied straight through to the staging row when set.
_SPEC_PASSTHROUGH = (
    "battery_capacity", "runtime_minutes", "charging_time_minutes", "weight_kg",
    "dimensions_mm", "width_mm", "length_mm", "height_mm", "ip_rating",
    "speed_ms", "voltage",
)


def build_row(rid: int, data: dict[str, Any]) -> dict[str, Any]:
    name = data["name"]
    videos = enrich_video_list([f"https://www.youtube.com/watch?v={v}" for v in data.get("video_ids", [])])
    spec_lines: list[str] = []
    if data.get("suction_pa"):
        spec_lines.append(f"suction={data['suction_pa']}")
    for key in ("battery_capacity", "runtime_minutes", "charging_time_minutes",
                "weight_kg", "dimensions_mm", "ip_rating", "speed_ms"):
        if data.get(key):
            spec_lines.append(f"{key}={data[key]}")
    research_notes = (
        f"Curated Ecovacs backfill. {data['year_cite']} "
        f"Specs (OEM): {', '.join(spec_lines) if spec_lines else 'none typed'}."
    )
    row: dict[str, Any] = {
        "id": rid,
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CN",
        "description": data["description"],
        # `purpose` is a distinct, explicitly curated statement of what the robot
        # is for — not a copy of the description (falls back only for batch 1).
        "purpose": data.get("purpose") or data["description"],
        "features": data["features"],
        "url": data["url"],
        "image": data["images"][0],
        "images": data["images"],
        "video_urls": videos,
        "movement_type_keys": data.get("movement") or "wheeled",
        "sub_category_slug": "cleaning-facilities",
        "category_slugs": "service-robots",
        "availability_status_key": "released",
        "tags": data.get("tags") or TAGS_VACUUM,
        "release_year": data.get("release_year"),
        "sources": data["sources"],
        "research_notes": research_notes,
    }
    for key in _SPEC_PASSTHROUGH:
        if data.get(key) is not None and data.get(key) != "":
            row[key] = data[key]
    if data.get("price_max") is not None:
        row["price_max"] = data["price_max"]
        row["price_currency"] = data.get("price_currency") or "USD"
        row["price_notes"] = data.get("price_notes") or ""
    return {k: v for k, v in row.items() if v is not None and v != "" and v != []}


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("copy-media skipped: missing INTERNAL_API_SECRET or IMPORT_SYNC_API_BASE_URL")
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        copy_url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(copy_url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.3)
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Ecovacs DEEBOT robots (company 32)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--robot-ids", type=str, default="", help="Comma-separated subset of ROBOT_DATA ids")
    args = parser.parse_args()

    ids = list(ROBOT_DATA)
    if args.robot_ids.strip():
        want = {int(x) for x in args.robot_ids.split(",") if x.strip().isdigit()}
        ids = [i for i in ids if i in want]

    client = ResearchApiClient()
    live = {r["id"]: r for r in client.list_robots_for_company(COMPANY_ID)}

    plan: list[dict[str, Any]] = []
    rows_by_id: dict[int, dict[str, Any]] = {}
    for rid in ids:
        cur = live.get(rid)
        if cur is None:
            print(f"SKIP {rid}: not found under company {COMPANY_ID}", file=sys.stderr)
            continue
        status = (cur.get("status") or "").lower()
        if status in SKIP_STATUSES:
            print(f"SKIP {rid} {cur.get('name')}: status={status} (never touch published/approved)", file=sys.stderr)
            continue
        if status != "pending_review":
            print(f"SKIP {rid} {cur.get('name')}: status={status} (only pending_review)", file=sys.stderr)
            continue
        row = build_row(rid, ROBOT_DATA[rid])
        rows_by_id[rid] = row
        plan.append({
            "id": rid, "name": row["name"], "status": status,
            "image": row["image"], "n_images": len(row["images"]),
            "features_len": len(row["features"]), "videos": len(row.get("video_urls") or []),
            "release_year": row.get("release_year"), "price": row.get("price_max"),
            "n_sources": len(row["sources"]),
        })
        print(f"{rid} {row['name']}: imgs={len(row['images'])} feat={len(row['features'])} "
              f"year={row.get('release_year')} price={row.get('price_max')} "
              f"videos={len(row.get('video_urls') or [])} sources={len(row['sources'])}")

    preview = _RESEARCH_DIR / "staging" / "reports" / "ecovacs-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"\nDry-run preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="ecovacs-fix-"))
    imported_ids: list[int] = []
    totals = {"updated_count": 0, "created_count": 0, "skipped_count": 0, "error_count": 0}
    all_ok = True
    for rid in [p["id"] for p in plan]:
        row = rows_by_id[rid]
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = import_staging(
            fpath,
            patch=True,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=True,
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid} {row['name']}: {result.get('errors')}", file=sys.stderr)
            continue
        if result.get("created_count"):
            all_ok = False
            print(f"WARNING {rid}: created_count>0 — expected patch-only!", file=sys.stderr)
        imported_ids.append(rid)
        for k in totals:
            totals[k] += result.get(k, 0) or 0

    print(json.dumps({"ok": all_ok, **totals}, indent=2))

    if args.copy_media and imported_ids:
        ok, fail = trigger_copy_media(imported_ids)
        print(f"copy-media ok={ok} fail={fail}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
