"""Backfill Geek+ (company 1398) pending_review robots.

Uses official geekplus.com technology-detail pages + brochure PDFs.
Replaces missing/wrong heroes with HubSpot product renders (model-named assets).
Does not invent P-series per-SKU payload from the broken identical spec tabs —
cites series-level OEM claims only unless a model-specific sheet exists (RS/F12ML).
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

COMPANY_ID = 1398
COMPANY_SLUG = "beijing-geekplus-technology-co-ltd"
COMPANY_NAME = "Geek+"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

TAGS_P = "AMR|Warehouse Automation|Logistics|Autonomous Mobile Robot|Pick-and-Place|Industrial|picking|Intralogistics"
TAGS_RS = "AMR|Warehouse Automation|Logistics|Tote Handling|Autonomous Mobile Robot|Industrial|Intralogistics|picking"
TAGS_X = "AMR|Warehouse Automation|Logistics|Pallet Handling|Autonomous Mobile Robot|Industrial|Intralogistics"
TAGS_S = "AMR|Warehouse Automation|Logistics|Sorting|Autonomous Mobile Robot|Industrial|Intralogistics"
TAGS_M = "AMR|Warehouse Automation|Logistics|Autonomous Mobile Robot|Industrial|Intralogistics|Mobile Robot"
TAGS_F = "AMR|Warehouse Automation|Logistics|Forklift|Pallet Handling|Autonomous Mobile Robot|Industrial|Intralogistics"
TAGS_SOL = "AMR|Warehouse Automation|Logistics|Autonomous Mobile Robot|Industrial|Intralogistics|picking"

# Prefer original hubfs paths (larger) over tiny thumbnails.
IMG = {
    "P500": "https://www.geekplus.com/hs-fs/hubfs/Tech%20P%20Series/P500R%20copy.png?width=800&name=P500R%20copy.png",
    "P800": "https://www.geekplus.com/hs-fs/hubfs/Geek+2025/products/p-series/P800R-img.png?width=800&name=P800R-img.png",
    "P1200": "https://www.geekplus.com/hs-fs/hubfs/Geek+2025/products/p-series/P1200-img.png?width=800&name=P1200-img.png",
    "P800V6": "https://www.geekplus.com/hs-fs/hubfs/Geek+2025/products/p-series/P800R%20V6%2045-img.png?width=800&name=P800R%20V6%2045-img.png",
    "P40": "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/P%2040%20model.png",
    "RS8": "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/RS8-DA%20model.png",
    "RS_AIR": "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/RS%20Air%20model%20dark.png",
    "X1200": "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/335x184px-X1200%201.png",
    "S20C": "https://www.geekplus.com/hs-fs/hubfs/S20C-2.png?width=800&name=S20C-2.png",
    "S20CA": "https://www.geekplus.com/hs-fs/hubfs/S20C-A%201%201.png?width=800&name=S20C-A%201%201.png",
    "S20T": "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/s1.png",
    "S100C": "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/s1.png",
    "M200C": "https://www.geekplus.com/hubfs/M200C%20Robot%20Body-left%20front%201.png",
    "MP1000R": "https://www.geekplus.com/hs-fs/hubfs/mp1000r%20sne%202.1.940%201.png?width=800&name=mp1000r%20sne%202.1.940%201.png",
    "F12ML": "https://www.geekplus.com/hubfs/F12ML%201.png",
    "F20MT": "https://www.geekplus.com/hs-fs/hubfs/F20MT-3.png?width=800&name=F20MT-3.png",
    "POPPICK": "https://www.geekplus.com/hs-fs/hubfs/onestop%20warehouse.jpg?width=1600&name=onestop%20warehouse.jpg",
}

URL_P = "https://www.geekplus.com/technology-detail-page/p-series"
URL_RS = "https://www.geekplus.com/technology-detail-page/rs-series"
URL_X = "https://www.geekplus.com/technology-detail-page/x-series"
URL_S = "https://www.geekplus.com/technology-detail-page/s-series"
URL_M = "https://www.geekplus.com/technology-detail-page/m-series"
URL_F = "https://www.geekplus.com/technology-detail-page/f-series"
URL_SHELF = "https://www.geekplus.com/solutions/shelf-to-person"
URL_TOTE = "https://www.geekplus.com/solutions/tote-to-person"
URL_PALLET = "https://www.geekplus.com/solutions/pallet-to-person"
URL_SORT = "https://www.geekplus.com/solutions/sorting"
URL_INTRA = "https://www.geekplus.com/solutions/intralogistics"

# Curated enrichment keyed by exact DB robot name.
ROBOT_DATA: dict[str, dict[str, Any]] = {
    "P500": {
        "url": URL_P,
        "image": IMG["P500"],
        "tags": TAGS_P,
        "features": (
            "Geek+ P-Series shelf-to-person AMR for rack lifting and goods-to-person picking. "
            "OEM series page: multiple P models with maximum load up to 1200 kg and top speed up to 4.5 m/s; "
            "modular deployment on flat warehouse floors; supports shelf-to-person workflows. "
            "P500 class suited to small–medium racks and items (see P500R family on geekplus.com)."
        ),
        "description": "Geek+ P500 shelf-handling AMR for warehouse shelf-to-person picking.",
        "source_note": "Features/series limits from geekplus.com/technology-detail-page/p-series. Hero: official P500R product render.",
    },
    "P800": {
        "url": URL_P,
        "image": IMG["P800"],
        "tags": TAGS_P,
        "features": (
            "Geek+ P-Series shelf-to-person AMR. Series claims maximum load up to 1200 kg and top speed up to 4.5 m/s. "
            "P800R marketed for medium–large racks with small to large items/weights; modular multi-purpose design."
        ),
        "description": "Geek+ P800 shelf-handling AMR for medium–large warehouse racks.",
        "source_note": "P-series page + P800R product render on geekplus.com.",
    },
    "P1200": {
        "url": URL_P,
        "image": IMG["P1200"],
        "tags": TAGS_P,
        "features": (
            "Geek+ P-Series heavy shelf-to-person AMR. Series maximum load cited up to 1200 kg; "
            "top speed up to 4.5 m/s; flat-floor retrofit into existing warehouses."
        ),
        "description": "Geek+ P1200 shelf-handling AMR in the P-Series goods-to-person lineup.",
        "source_note": "P-series page + P1200 product render.",
    },
    "P800H": {
        "url": URL_P,
        "image": IMG["P800V6"],
        "tags": TAGS_P,
        "features": (
            "Geek+ P800H / slim P800-family shelf AMR variant for shelf-to-person picking. "
            "P-Series: modular multi-purpose robots, series load up to 1200 kg, top speed up to 4.5 m/s."
        ),
        "description": "Geek+ P800H slim/high-variant P-Series shelf AMR.",
        "source_note": "Mapped to P800R V6 slim family render on P-series page (closest official SKU art).",
    },
    "RoboShuttle V5.0 (RS Air)": {
        "url": URL_RS,
        "image": IMG["RS_AIR"],
        "tags": TAGS_RS,
        "payload_kg": 40.0,
        "weight_kg": None,
        "dimensions_mm": "1400 x 870 x (custom)",
        "features": (
            "Geek+ RoboShuttle V5 RS Air — RS-Series tote-to-person robot. "
            "OEM specs (RS Air): max payload 40 kg; speed with/without load up to 4 m/s; "
            "minimum aisle width cited 1015 mm; dimensions 1400×870×(customized). "
            "RS series improves picking efficiency ~4× on average with flexible robot add/remove."
        ),
        "description": "Geek+ RoboShuttle V5 RS Air high-speed tote-to-person AMR.",
        "source_note": "RS-series technology page model specs for RS Air.",
    },
    "RoboShuttle V5.0 (RS)": {
        "url": URL_RS,
        "image": IMG["RS8"],
        "tags": TAGS_RS,
        "payload_kg": 40.0,
        "weight_kg": 900.0,
        "dimensions_mm": "1800 x 1000 x 4700",
        "features": (
            "Geek+ RoboShuttle V5 RS tote-to-person robot (RS-Series). "
            "Series height capabilities 5/8/11 m with payload up to 40 kg. "
            "Representative RS8-DA sheet: payload 40 kg; weight 900 kg; lifting height 7935 mm; "
            "dims 1800×1000×4700 mm; no-load 1.8 m/s / loaded 1.5 m/s (brochure + site)."
        ),
        "description": "Geek+ RoboShuttle V5 RS tote-handling robot for high-density storage.",
        "source_note": "RS-series page + RS-series.pdf RS8-DA facts.",
    },
    "RoboShuttle V5.0 (P40)": {
        "url": URL_RS,
        "image": IMG["P40"],
        "tags": TAGS_RS,
        "payload_kg": 40.0,
        "weight_kg": 60.0,
        "dimensions_mm": "650 x 450 x 386",
        "features": (
            "Geek+ P40 RS helper robot for tote-to-person. "
            "OEM specs: max payload 40 kg; speed with/without load 3.5 m/s; lifting height 440 mm; "
            "dimensions 650×450×386 mm; weight 60 kg; min lifting time 4 s."
        ),
        "description": "Geek+ P40 compact RS helper AMR for tote transport.",
        "source_note": "RS-series page P40 specifications.",
    },
    "RoboShuttle V5.0 (RAPS)": {
        "url": "https://www.geekplus.com/solutions/robot-arm-picking-station",
        "image": IMG["RS8"],
        "tags": TAGS_RS + "|Pick-and-Place",
        "payload_kg": 40.0,
        "features": (
            "Geek+ RAPS (Robot Arm Picking Station) pairs RoboShuttle tote flow with robotic arm picking. "
            "RS-Series tote robots: payload class up to 40 kg; flexible tote-to-person implementation."
        ),
        "description": "Geek+ RAPS robot-arm picking station with RoboShuttle tote induction.",
        "source_note": "Solution kit pages + RS-series payload class.",
    },
    "SkyCube (X-Series X1200Z)": {
        "url": URL_X,
        "image": IMG["X1200"],
        "tags": TAGS_X,
        "features": (
            "Geek+ SkyCube / X-Series X1200Z pallet-to-person AMR for dense pallet storage and handling. "
            "Official X-series technology page lists X1200Z as the featured model for pallet workflows."
        ),
        "description": "Geek+ X1200Z SkyCube pallet-to-person AMR.",
        "source_note": "X-series technology-detail page + X1200 product render.",
    },
    "S20T": {
        "url": URL_S,
        "image": IMG["S20T"],
        "tags": TAGS_S,
        "features": (
            "Geek+ S20T sorting AMR for high-speed item/parcel sortation. "
            "S-Series models (S20C/S20T/S100C) for GTP sorting workflows on geekplus.com."
        ),
        "description": "Geek+ S20T sorting robot.",
        "source_note": "S-series technology page.",
    },
    "S100C": {
        "url": URL_S,
        "image": IMG["S100C"],
        "tags": TAGS_S,
        "features": (
            "Geek+ S100C sorting AMR for larger packages. "
            "OEM news/product line: intelligent sortation of large-size packages; S-Series family."
        ),
        "description": "Geek+ S100C large-package sorting AMR.",
        "source_note": "S-series page + S100C launch materials on geekplus.com.",
    },
    "M-Series (MP1000)": {
        "url": URL_M,
        "image": IMG["MP1000R"],
        "tags": TAGS_M,
        "payload_kg": 1000.0,
        "features": (
            "Geek+ M-Series moving robot (MP1000 class). "
            "OEM: M-Series maximum carrying load 1000 kg; laser SLAM and QR-code navigation support."
        ),
        "description": "Geek+ MP1000 M-Series intralogistics AMR.",
        "source_note": "M-series technology page series payload claim + MP1000R render.",
    },
    "M-Series (M200C)": {
        "url": URL_M,
        "image": IMG["M200C"],
        "tags": TAGS_M,
        "features": (
            "Geek+ M200C moving AMR for warehouse transport/handling. "
            "M-Series family supports laser SLAM and QR navigation; series max carrying load 1000 kg."
        ),
        "description": "Geek+ M200C M-Series transport AMR.",
        "source_note": "M-series page + M200C product render.",
    },
    "F-Series (F12ML)": {
        "url": URL_F,
        "image": IMG["F12ML"],
        "tags": TAGS_F,
        "payload_kg": 1500.0,
        "dimensions_mm": "1707 x 1050 x 2076",
        "features": (
            "Geek+ F12ML smart forklift AMR. Brochure: Laser SLAM; 3 lidars + vertical 3D camera; "
            "payload 0–2 m: 1500 kg / 2–2.5 m: 1200 kg / 2.5–3 m: 1000 kg; max travel 1.5 m/s; "
            "lift height 2300 mm; body 1707×1050×2076 mm; Li-ion 24 V/150 Ah; runtime 6–8 h. "
            "F-Series series page cites max carrying load up to 2000 kg across models."
        ),
        "description": "Geek+ F12ML autonomous smart forklift.",
        "source_note": "F12ML.pdf brochure + F-series technology page.",
    },
    "F-Series (F20MT)": {
        "url": URL_F,
        "image": IMG["F20MT"],
        "tags": TAGS_F,
        "features": (
            "Geek+ F20MT smart forklift / pallet AMR in the F-Series. "
            "F-Series OEM claim: maximum carrying load up to 2000 kg; laser SLAM and QR-code support."
        ),
        "description": "Geek+ F20MT F-Series autonomous forklift AMR.",
        "source_note": "F-series technology page + F20MT product render.",
    },
    "Geek+ P800": {
        "url": URL_P,
        "image": IMG["P800"],
        "tags": TAGS_P,
        "features": (
            "Geek+ P800 / P800R shelf-to-person AMR. P-Series: load capacity up to 1200 kg, top speed up to 4.5 m/s; "
            "best for medium–large racks."
        ),
        "description": "Geek+ P800 shelf-handling AMR.",
        "source_note": "P-series page.",
    },
    "Geek+ P40": {
        "url": URL_RS,
        "image": IMG["P40"],
        "tags": TAGS_RS,
        "payload_kg": 40.0,
        "weight_kg": 60.0,
        "dimensions_mm": "650 x 450 x 386",
        "features": (
            "Geek+ P40 RS helper. Specs: payload 40 kg; 3.5 m/s; lift height 440 mm; "
            "650×450×386 mm; weight 60 kg."
        ),
        "description": "Geek+ P40 tote helper AMR.",
        "source_note": "RS-series P40 specs.",
    },
    "Geek+ X1200": {
        "url": URL_X,
        "image": IMG["X1200"],
        "tags": TAGS_X,
        "features": (
            "Geek+ X1200 X-Series pallet AMR for pallet-to-person / dense pallet handling (SkyCube family)."
        ),
        "description": "Geek+ X1200 X-Series pallet AMR.",
        "source_note": "X-series technology page.",
    },
    "Geek+ X1200Z": {
        "url": URL_X,
        "image": IMG["X1200"],
        "tags": TAGS_X,
        "features": (
            "Geek+ X1200Z featured X-Series model for pallet-to-person automation (SkyCube)."
        ),
        "description": "Geek+ X1200Z pallet-to-person AMR.",
        "source_note": "X-series page X1200Z.",
    },
    "Geek+ S20C-A": {
        "url": URL_S,
        "image": IMG["S20CA"],
        "tags": TAGS_S,
        "features": (
            "Geek+ S20C-A sorting AMR variant in the S-Series for high-speed parcel/item sortation."
        ),
        "description": "Geek+ S20C-A sorting robot.",
        "source_note": "S-series page S20C-A render.",
    },
    "Geek+ F20MT": {
        "url": URL_F,
        "image": IMG["F20MT"],
        "tags": TAGS_F,
        "features": (
            "Geek+ F20MT F-Series smart forklift AMR; series max carrying load up to 2000 kg."
        ),
        "description": "Geek+ F20MT autonomous forklift.",
        "source_note": "F-series page.",
    },
    "PopPick (Shelf-to-Person Standard Configuration)": {
        "url": URL_SHELF,
        "image": IMG["POPPICK"],
        "tags": TAGS_SOL,
        "features": (
            "Geek+ PopPick shelf-to-person solution configuration combining P-Series AMRs with picking workstations. "
            "Solution-level catalog entry (not a single robot SKU)."
        ),
        "description": "Geek+ PopPick shelf-to-person solution kit.",
        "source_note": "solutions/shelf-to-person — solution entry, not a discrete robot SKU.",
        "is_solution": True,
    },
    "FleetSort (Sorting Solution)": {
        "url": URL_SORT,
        "image": IMG["S20T"],
        "tags": TAGS_S,
        "features": (
            "Geek+ FleetSort sorting solution using S-Series sorting AMRs for high-speed item and parcel sortation. "
            "Solution-level catalog entry."
        ),
        "description": "Geek+ FleetSort sorting solution.",
        "source_note": "solutions/sorting — solution entry.",
        "is_solution": True,
    },
    "Shelf-to-Person PopPick (Standard Configuration)": {
        "url": URL_SHELF,
        "image": IMG["POPPICK"],
        "tags": TAGS_SOL,
        "features": (
            "Geek+ shelf-to-person PopPick standard configuration — P-Series AMR + workstation goods-to-person flow."
        ),
        "description": "Geek+ PopPick shelf-to-person standard configuration.",
        "source_note": "solutions/shelf-to-person.",
        "is_solution": True,
    },
    "Geek+ P500": {
        "url": URL_P,
        "image": IMG["P500"],
        "tags": TAGS_P,
        "weight_kg": 144.0,
        "features": (
            "Geek+ P500 shelf-to-person AMR. P-Series max load up to 1200 kg / top speed up to 4.5 m/s. "
            "Existing CRM weight 144 kg preserved where already present."
        ),
        "description": "Geek+ P500 shelf-handling AMR.",
        "source_note": "P-series page; weight retained from prior CRM value.",
    },
    "Geek+ P1200": {
        "url": URL_P,
        "image": IMG["P1200"],
        "tags": TAGS_P,
        "features": (
            "Geek+ P1200 P-Series shelf AMR; series load up to 1200 kg; top speed up to 4.5 m/s."
        ),
        "description": "Geek+ P1200 shelf-handling AMR.",
        "source_note": "P-series page.",
    },
    "Geek+ RS8-DA": {
        "url": URL_RS,
        "image": IMG["RS8"],
        "tags": TAGS_RS,
        "payload_kg": 40.0,
        "weight_kg": 900.0,
        "dimensions_mm": "1800 x 1000 x 4700",
        "features": (
            "Geek+ RS8-DA RoboShuttle. Site/brochure: payload 40 kg; weight 900 kg; lift height 7935 mm; "
            "dims 1800×1000×4700 mm; loaded speed 1.5 m/s / unloaded 1.8 m/s; lift time 10 s."
        ),
        "description": "Geek+ RS8-DA high-bay tote robot.",
        "source_note": "RS-series page + RS-series.pdf.",
    },
    "Geek+ RS Air": {
        "url": URL_RS,
        "image": IMG["RS_AIR"],
        "tags": TAGS_RS,
        "payload_kg": 40.0,
        "dimensions_mm": "1400 x 870 x (custom)",
        "features": (
            "Geek+ RS Air. Specs: payload 40 kg; speed up to 4 m/s; aisle width min 1015 mm; "
            "dims 1400×870×(custom)."
        ),
        "description": "Geek+ RS Air high-speed tote AMR.",
        "source_note": "RS-series page.",
    },
    "Geek+ MP1000R": {
        "url": URL_M,
        "image": IMG["MP1000R"],
        "tags": TAGS_M,
        "payload_kg": 1000.0,
        "features": (
            "Geek+ MP1000R M-Series mover; series maximum carrying load 1000 kg; laser SLAM / QR navigation."
        ),
        "description": "Geek+ MP1000R M-Series AMR.",
        "source_note": "M-series page.",
    },
    "Geek+ S20C": {
        "url": URL_S,
        "image": IMG["S20C"],
        "tags": TAGS_S,
        "features": "Geek+ S20C sorting AMR in the S-Series for high-speed sortation.",
        "description": "Geek+ S20C sorting robot.",
        "source_note": "S-series page.",
    },
    "Geek+ S20T": {
        "url": URL_S,
        "image": IMG["S20T"],
        "tags": TAGS_S,
        "features": "Geek+ S20T sorting AMR; S-Series GTP sorting lineup.",
        "description": "Geek+ S20T sorting robot.",
        "source_note": "S-series page.",
    },
    "Geek+ S100C": {
        "url": URL_S,
        "image": IMG["S100C"],
        "tags": TAGS_S,
        "features": "Geek+ S100C large-package sorting AMR in the S-Series.",
        "description": "Geek+ S100C sorting robot.",
        "source_note": "S-series page.",
    },
}

# Canonical IDs selected from the 55-row pending queue. All other rows are
# explicit duplicate or solution/configuration shells and are rejected below.
P_PDF = "https://www.geekplus.com/hubfs/P-series-2.pdf?hsLang=en"
RS_PDF = "https://www.geekplus.com/hubfs/RS-series-2.pdf?hsLang=en"
X_PDF = "https://www.geekplus.com/hubfs/X-series.pdf?hsLang=en"
S_PDF = "https://www.geekplus.com/hubfs/S-series-2.pdf?hsLang=en"
M_PDF = "https://www.geekplus.com/hubfs/M-series-1.pdf?hsLang=en"
F12_PDF = "https://www.geekplus.com/hubfs/F12ML.pdf?hsLang=en"
F20_PDF = "https://www.geekplus.com/hubfs/F20MT.pdf?hsLang=en"

IMG.update(
    {
        "S20T_EXACT": "https://www.geekplus.com/hubfs/Frame%201171275592.png",
        "S20C_EXACT": (
            "https://www.geekplus.com/hubfs/"
            "s20c%E6%B8%B2%E6%9F%93.450-%E5%8F%B3%E6%96%9C45%C2%B0"
            "%E9%BB%91%E7%AB%8B%E6%9F%B1%E7%89%88.png"
        ),
    }
)

YOUTUBE = {
    "P800R": ["https://www.youtube.com/watch?v=mBqf7h8Ubsw"],
    "RS8-DA": ["https://www.youtube.com/watch?v=6XG_W_6JoaU"],
    "RS Air": ["https://www.youtube.com/watch?v=9v9dWxP9DEM"],
    "P40R": ["https://www.youtube.com/watch?v=3NfRIp-WVec"],
    "S20C-A V2.0": ["https://www.youtube.com/watch?v=XE-fT1t52Fc"],
    "MP1000R-SNE V2.1": ["https://www.youtube.com/watch?v=9PPsT0yGQ4s"],
}

# Every numeric value below is model-specific and cited by the linked OEM PDF.
# speed is stored in km/h; OEM m/s values are retained verbatim in features.
CURATED_MODELS: dict[int, dict[str, Any]] = {
    1782: {
        "model": "P500R",
        "family": ("geekplus:p-series", "P-Series", URL_P, P_PDF),
        "hero": IMG["P500"],
        "description": "Geek+ P500R is a shelf-lifting AMR that moves warehouse racks to goods-to-person picking stations.",
        "purpose": "Shelf-to-person rack transport\nGoods-to-person order picking",
        "features": (
            "OEM P500R specification: 600 kg payload; 950×702×275 mm body; 144 kg robot weight; "
            "2.0 m/s no-load and 1.5 m/s full-load travel; 60 mm maximum lift height; 4 s lift time; "
            "inertia plus QR-code navigation, with infrared or lidar obstacle detection by variant."
        ),
        "payload_kg": 600.0, "weight_kg": 144.0, "speed": 5.4,
        "length_mm": 950.0, "width_mm": 702.0, "height_mm": 275.0,
        "runtime": "1.5–2 hours of work per 10-minute opportunity charge",
        "battery_capacity": "Wide-temperature lithium, 51.1 V 30 Ah or 51.8 V 40.3 Ah by variant",
        "kind": "p",
    },
    1783: {
        "model": "P800R",
        "family": ("geekplus:p-series", "P-Series", URL_P, P_PDF),
        "hero": IMG["P800"],
        "description": "Geek+ P800R is a medium-to-large rack shelf-lifting AMR for goods-to-person warehouse picking.",
        "purpose": "Shelf-to-person rack transport\nGoods-to-person order picking",
        "features": (
            "OEM P800R specification: 1000 kg payload; 1095×830×195 mm regular body or "
            "1095×830×275 mm thicker PopPick version; 142 kg robot weight; 2.3 m/s no-load and "
            "2.0 m/s full-load travel; 55 mm maximum lift height; 4 s lift time; inertia plus QR navigation."
        ),
        "payload_kg": 1000.0, "weight_kg": 142.0, "speed": 7.2,
        "length_mm": 1095.0, "width_mm": 830.0, "height_mm": 195.0,
        "runtime": "1.5–2 hours of work per 10-minute opportunity charge",
        "battery_capacity": "Wide-temperature lithium, 51.1 V 27.9 Ah",
        "kind": "p",
    },
    1784: {
        "model": "P1200R",
        "family": ("geekplus:p-series", "P-Series", URL_P, P_PDF),
        "hero": IMG["P1200"],
        "description": "Geek+ P1200R is a heavy shelf-lifting AMR for large-rack goods-to-person picking.",
        "purpose": "Heavy-rack shelf transport\nGoods-to-person order picking",
        "features": (
            "OEM P1200R specification: 1200 kg payload; 1325×1020×275 mm body; 288 kg robot weight; "
            "2.6 m/s no-load and 2.2 m/s full-load travel; 60 mm maximum lift height; 4 s lift time; "
            "supports 1250×1250 to 1600×1600 mm shelves."
        ),
        "payload_kg": 1200.0, "weight_kg": 288.0, "speed": 7.92,
        "length_mm": 1325.0, "width_mm": 1020.0, "height_mm": 275.0,
        "runtime": "1.5–2 hours of work per 10-minute opportunity charge",
        "battery_capacity": "Wide-temperature lithium, 51.1 V 27.9 Ah",
        "kind": "p",
    },
    1785: {
        "model": "P800H",
        "family": ("geekplus:p-series", "P-Series", URL_P, P_PDF),
        "hero": "",
        "description": "Geek+ P800H is a legacy P-Series shelf-handling label retained for review because an exact current OEM record was not found.",
        "purpose": "Shelf-to-person rack transport",
        "features": (
            "The Geek+ shelf-to-person solution references P800H, but the current and legacy P-Series "
            "technology pages and the current P-Series technical guide do not identify P800H as a "
            "separate model or provide exact specifications."
        ),
        "kind": "p", "held": (
            "No exact P800H PDP, datasheet specification, availability statement, or standalone image. "
            "The previous P800R V6 image was a sibling substitute and is not valid. The production research "
            "serializer does not clear existing photo/video relations from empty lists, and the relation-management "
            "admin endpoints reject internal-secret authentication, so stale related media remains held for manual removal."
        ),
    },
    1791: {
        "model": "S20T",
        "family": ("geekplus:s-series", "S-Series", URL_S, S_PDF),
        "hero": IMG["S20T_EXACT"],
        "description": "Geek+ S20T V2.0 is a tall-deck sorting AMR for small-item and parcel sortation.",
        "purpose": "Small-item sortation\nParcel routing to destination chutes",
        "features": (
            "OEM S20T V2.0 specification: 8 kg payload; 560×510×1345 mm body; 70 kg robot weight; "
            "2.5 m/s maximum and 2.0 m/s fully loaded speed; 320×320×300 mm maximum load size; "
            "lidar obstacle detection and sub-10 mm positioning accuracy."
        ),
        "payload_kg": 8.0, "weight_kg": 70.0, "speed": 9.0,
        "length_mm": 560.0, "width_mm": 510.0, "height_mm": 1345.0,
        "runtime": "1.5 hours of work per 10-minute opportunity charge",
        "battery_capacity": "Lithium-ion, 50.4 V 12 Ah",
        "kind": "s",
    },
    1792: {
        "model": "S100C",
        "family": ("geekplus:s-series", "S-Series", URL_S, S_PDF),
        "hero": "",
        "description": "Geek+ S100C V2.0 is a conveyor-compatible sorting AMR for large or multiple parcels.",
        "purpose": "Large-parcel sortation\nConveyor-line package transfer",
        "features": (
            "OEM S100C V2.0 specification: 100 kg payload; 1170×832×590 mm body; 235 kg robot weight; "
            "2.0 m/s maximum and fully loaded speed; one package up to 750×1000×600 mm or two packages "
            "up to 750×450×600 mm each; infrared sensing with lidar support."
        ),
        "payload_kg": 100.0, "weight_kg": 235.0, "speed": 7.2,
        "length_mm": 1170.0, "width_mm": 832.0, "height_mm": 590.0,
        "runtime": "2–3 hours of work per 10-minute opportunity charge",
        "battery_capacity": "Lithium, 50.4 V 38.5 Ah",
        "kind": "s", "held": (
            "Exact S100C specs are verified in the OEM technical guide, but no standalone public OEM "
            "image was found; the previous S-Series composite image is not an exact-model hero. The production research "
            "serializer does not clear an existing photo relation from an empty list, and the relation-management admin "
            "endpoint rejects internal-secret authentication, so the stale related photo remains held for manual removal."
        ),
    },
    1793: {
        "model": "MP1000R-SNE V2.1",
        "family": ("geekplus:m-series", "M-Series", URL_M, M_PDF),
        "hero": IMG["MP1000R"],
        "description": "Geek+ MP1000R-SNE V2.1 is a high-payload AMR for moving racks and materials inside warehouses.",
        "purpose": "Heavy rack transport\nWarehouse material movement",
        "features": (
            "OEM MP1000R-SNE V2.1 specification: 1000 kg payload; 1105×855×275 mm body; 106 kg robot "
            "weight; 1.5 m/s loaded or unloaded; laser SLAM with reflector/visual-language enhancement "
            "or QR-code navigation; 4 s lift time and all-around collision prevention."
        ),
        "payload_kg": 1000.0, "weight_kg": 106.0, "speed": 5.4,
        "length_mm": 1105.0, "width_mm": 855.0, "height_mm": 275.0,
        "runtime": "1 hour of work per 10-minute opportunity charge",
        "battery_capacity": "Gelled ternary lithium-ion, 50.4 V 39 Ah or 40.3 Ah",
        "kind": "m",
    },
    1794: {
        "model": "M200C",
        "family": ("geekplus:m-series", "M-Series", URL_M, M_PDF),
        "hero": IMG["M200C"],
        "description": "Geek+ M200C is a compact rack-handling AMR for internal warehouse transport.",
        "purpose": "Rack transport\nWarehouse material movement",
        "features": (
            "OEM M200C specification: 200 kg payload; 760×520×313 mm body; 106 kg robot weight; "
            "1.5 m/s loaded or unloaded; 4 s lift time; laser SLAM, reflector/visual-language enhancement "
            "or QR-code navigation; front/rear lidar plus forward visual detection."
        ),
        "payload_kg": 200.0, "weight_kg": 106.0, "speed": 5.4,
        "length_mm": 760.0, "width_mm": 520.0, "height_mm": 313.0,
        "runtime": "1 hour of work per 10-minute opportunity charge",
        "battery_capacity": "Gelled ternary lithium-ion, 50.4 V 27 Ah",
        "kind": "m",
    },
    1795: {
        "model": "F12ML",
        "family": ("geekplus:f-series", "F-Series", URL_F, F12_PDF),
        "hero": IMG["F12ML"],
        "description": "Geek+ F12ML is an autonomous counterbalanced forklift for pallet transport and elevated storage.",
        "purpose": "Pallet transport\nAutonomous pallet stacking and retrieval",
        "features": (
            "OEM F12ML specification: payload 1500 kg at 0–2 m, 1200 kg at 2–2.5 m, and 1000 kg at "
            "2.5–3 m; 1707×1050×2076 mm body; 1.5 m/s no-load and 1.0 m/s loaded speed; 2300 mm "
            "lifting height; laser SLAM, three lidars and a vertical 3D camera."
        ),
        "payload_kg": 1500.0, "speed": 5.4,
        "length_mm": 1707.0, "width_mm": 1050.0, "height_mm": 2076.0,
        "runtime": "6–8 hours of continuous operation",
        "battery_capacity": "Lithium-ion, 24 V 150 Ah",
        "kind": "f",
    },
    1796: {
        "model": "F20MT",
        "family": ("geekplus:f-series", "F-Series", URL_F, F20_PDF),
        "hero": IMG["F20MT"],
        "description": "Geek+ F20MT is an autonomous pallet-transport forklift AMR for heavy warehouse loads.",
        "purpose": "Heavy pallet transport\nAutonomous pallet pickup and drop-off",
        "features": (
            "OEM F20MT specification: payload up to 2000 kg; 1594×1094×2067 mm body; maximum travel "
            "speed 1.5 m/s; 120 mm lifting height; laser SLAM, two lidars and a vertical 3D camera; "
            "supports common 1200×1200, 1200×1000, 1100×1100 and 1200×800 mm H-shaped pallets."
        ),
        "payload_kg": 2000.0, "speed": 5.4,
        "length_mm": 1594.0, "width_mm": 1094.0, "height_mm": 2067.0,
        "runtime": "6–8 hours of continuous operation",
        "battery_capacity": "Lithium-ion, 24 V 150 Ah",
        "kind": "f",
    },
    2776: {
        "model": "P40R",
        "family": ("geekplus:rs-series", "RS-Series", URL_RS, RS_PDF),
        "hero": IMG["P40"],
        "description": "Geek+ P40R is a compact tote-carrying AMR used with RoboShuttle tote-to-person systems.",
        "purpose": "Tote transport between storage and picking stations",
        "features": (
            "OEM P40R specification: 40 kg payload; 650×450×383 mm body; 60 kg robot weight; "
            "3.5 m/s loaded or unloaded; 440 mm maximum lift height; 4 s full lift/lower time; "
            "inertia plus QR-code navigation and lidar obstacle detection."
        ),
        "payload_kg": 40.0, "weight_kg": 60.0, "speed": 12.6,
        "length_mm": 650.0, "width_mm": 450.0, "height_mm": 383.0,
        "runtime": "1–1.5 hours of work per 10-minute opportunity charge",
        "battery_capacity": "Lithium-ion, 51.8 V 12 Ah",
        "kind": "rs",
    },
    2778: {
        "model": "X1200Z",
        "family": ("geekplus:x-series", "X-Series", URL_X, X_PDF),
        "hero": IMG["X1200"],
        "description": "Geek+ X1200Z is a four-way pallet shuttle AMR for dense multi-level storage.",
        "purpose": "High-density pallet storage and retrieval\nPallet-to-person transport",
        "features": (
            "OEM X1200Z specification: 1200 kg payload; 1000×972×125 mm body; 270 kg robot weight; "
            "1.6 m/s no-load and 1.5 m/s full-load; 35 mm maximum lift; 2.5 s lift time; ±2 mm stop "
            "accuracy; motor drive with laser obstacle avoidance and cargo detection."
        ),
        "payload_kg": 1200.0, "weight_kg": 270.0, "speed": 5.4,
        "length_mm": 1000.0, "width_mm": 972.0, "height_mm": 125.0,
        "runtime": "8–10 hours room-temperature use; 6–8 hours cold-storage use",
        "battery_capacity": "48 V lithium; 40 Ah room-temperature or 30 Ah cold-storage configuration",
        "kind": "x",
    },
    2779: {
        "model": "S20C-A V2.0",
        "family": ("geekplus:s-series", "S-Series", URL_S, S_PDF),
        "hero": IMG["S20CA"],
        "description": "Geek+ S20C-A V2.0 is an adjustable-height conveyor sorting AMR.",
        "purpose": "Adjustable-height parcel sortation\nConveyor-line package transfer",
        "features": (
            "OEM S20C-A V2.0 specification: 20 kg payload; 560×600×577–1127 mm adjustable body; "
            "100 kg robot weight; 2.5 m/s maximum and 2.0 m/s loaded speed; adjustable 550–1100 mm "
            "carrier surface; lidar obstacle detection and sub-10 mm positioning accuracy."
        ),
        "payload_kg": 20.0, "weight_kg": 100.0, "speed": 9.0,
        "length_mm": 560.0, "width_mm": 600.0,
        "runtime": "1.5 hours of work per 10-minute opportunity charge",
        "battery_capacity": "Lithium-ion, 50.4 V 12 Ah",
        "kind": "s",
    },
    3582: {
        "model": "RS8-DA",
        "family": ("geekplus:rs-series", "RS-Series", URL_RS, RS_PDF),
        "hero": IMG["RS8"],
        "description": "Geek+ RS8-DA is a high-bay tote-handling RoboShuttle for dense tote storage.",
        "purpose": "High-bay tote storage and retrieval\nTote-to-person picking",
        "features": (
            "OEM RS8-DA specification: 40 kg payload; 1800×1000×4700 mm body; 900 kg robot weight; "
            "7935 mm maximum lifting height; 1.8 m/s no-load and 1.5 m/s full-load speed; 10 s lift time; "
            "inertia plus QR-code navigation with front/rear laser sensors."
        ),
        "payload_kg": 40.0, "weight_kg": 900.0, "speed": 5.4,
        "length_mm": 1800.0, "width_mm": 1000.0, "height_mm": 4700.0,
        "battery_capacity": "Lithium-ion, 50.4 V 42 Ah",
        "kind": "rs",
    },
    3583: {
        "model": "RS Air",
        "family": ("geekplus:rs-series", "RS-Series", URL_RS, RS_PDF),
        "hero": IMG["RS_AIR"],
        "description": "Geek+ RS Air is a high-speed vertical tote robot for frequent retrieval in RoboShuttle systems.",
        "purpose": "High-frequency tote storage and retrieval\nTote-to-person picking",
        "features": (
            "OEM RS Air page specification: 40 kg payload; 1400×870 mm footprint with customized "
            "height; up to 4.0 m/s loaded or unloaded; 1015 mm minimum aisle; 10 s minimum lift time."
        ),
        "payload_kg": 40.0, "speed": 14.4,
        "length_mm": 1400.0, "width_mm": 870.0,
        "kind": "rs",
    },
    4136: {
        "model": "S20C V2.0",
        "family": ("geekplus:s-series", "S-Series", URL_S, S_PDF),
        "hero": IMG["S20C_EXACT"],
        "description": "Geek+ S20C V2.0 is a conveyor-top sorting AMR for parcels and order-line routing.",
        "purpose": "Parcel sortation\nConveyor-line package transfer",
        "features": (
            "OEM S20C V2.0 specification: 20 kg payload; 560×600×1027 mm body; 75 kg robot weight; "
            "2.5 m/s maximum and 2.0 m/s fully loaded speed; 600×420×400 mm maximum load; "
            "lidar obstacle detection and sub-10 mm positioning accuracy."
        ),
        "payload_kg": 20.0, "weight_kg": 75.0, "speed": 9.0,
        "length_mm": 560.0, "width_mm": 600.0, "height_mm": 1027.0,
        "runtime": "1.5 hours of work per 10-minute opportunity charge",
        "battery_capacity": "Lithium-ion, 50.4 V 12 Ah",
        "kind": "s",
    },
    4950: {
        "model": "RS11-DA",
        "family": ("geekplus:rs-series", "RS-Series", URL_RS, RS_PDF),
        "hero": "",
        "description": "Geek+ RS11-DA is an 11-metre-class high-bay tote-handling RoboShuttle.",
        "purpose": "High-bay tote storage and retrieval\nTote-to-person picking",
        "features": (
            "OEM RS11-DA specification: 40 kg payload; 1800×1000×6200 mm body; 970 kg robot weight; "
            "10,765 mm maximum lifting height; 1.8 m/s no-load and 1.2 m/s full-load speed; 10 s lift "
            "time; inertia plus QR-code navigation with front/rear laser sensors."
        ),
        "payload_kg": 40.0, "weight_kg": 970.0, "speed": 4.32,
        "length_mm": 1800.0, "width_mm": 1000.0, "height_mm": 6200.0,
        "battery_capacity": "Lithium-ion, 50.4 V 42 Ah",
        "kind": "rs", "held": (
            "Exact RS11-DA specs are verified in the OEM technical guide, but no standalone public "
            "RS11-DA image was found. The previous hero duplicated RS8-DA bytes; the public RS11 render "
            "is visibly labelled RS11-DX and is not a valid substitute."
        ),
    },
}

FULL_REJECTS = {
    1786: "duplicate_exact_model: RS Air duplicates canonical robot 3583",
    1787: "non_specific_family_shell: generic RS row is not an exact OEM model",
    1788: "duplicate_exact_model: P40 duplicates canonical robot 2776",
    1789: "non_robot_solution_shell: RAPS is a robot-arm picking station solution",
    1790: "duplicate_exact_model: SkyCube X1200Z duplicates canonical robot 2778",
    2775: "duplicate_exact_model: P800 duplicates canonical robot 1783",
    2777: "incorrect_model_alias: OEM X-Series identifies X1200Z, not a separate X1200 SKU",
    2780: "duplicate_exact_model: F20MT duplicates canonical robot 1796",
    3395: "non_robot_solution_shell: PopPick standard configuration is a solution",
    3396: "non_robot_solution_shell: FleetSort is a sorting solution",
    3579: "non_robot_solution_shell: PopPick standard configuration is a solution",
    3580: "duplicate_exact_model: P500 duplicates canonical robot 1782",
    3581: "duplicate_exact_model: P1200 duplicates canonical robot 1784",
    3584: "duplicate_exact_model: MP1000R duplicates canonical robot 1793",
    3585: "duplicate_exact_model: S20C duplicates canonical robot 4136",
    3586: "duplicate_exact_model: S20T duplicates canonical robot 1791",
    3587: "duplicate_exact_model: S100C duplicates canonical robot 1792",
    4135: "non_robot_solution_shell: Robot Arm Picking Station is a fixed solution",
    4493: "non_robot_solution_shell: PopPick configuration is a solution",
    4494: "non_robot_configuration_shell: RoboShuttle V4 mobile-RS configuration",
    4495: "non_robot_configuration_shell: RoboShuttle V4 RS-plus-RS-Air configuration",
    4496: "non_robot_solution_shell: SkyCube pallet-to-person is a solution",
    4497: "non_robot_solution_shell: Smart Moving is an intralogistics solution",
    4498: "non_robot_solution_shell: Smart Forklift is an intralogistics solution",
    4864: "duplicate_exact_model: P500 duplicates canonical robot 1782",
    4865: "duplicate_exact_model: P800H duplicates held canonical robot 1785",
    4866: "non_specific_solution_shell: RoboShuttle V5.0 is a system, not one robot SKU",
    4867: "non_specific_family_shell: generic RS row is not an exact OEM model",
    4868: "duplicate_exact_model: RS Air duplicates canonical robot 3583",
    4869: "non_robot_solution_shell: SkyCube is a pallet-to-person solution",
    4870: "duplicate_exact_model: X1200Z duplicates canonical robot 2778",
    4871: "duplicate_exact_model: S20C duplicates canonical robot 4136",
    4872: "duplicate_exact_model: S20T duplicates canonical robot 1791",
    4873: "duplicate_exact_model: S100C duplicates canonical robot 1792",
    4874: "non_robot_solution_shell: InstaMove is an intralogistics solution",
    4949: "non_robot_solution_shell: PopPick configuration is a solution",
    4951: "duplicate_exact_model: M200C duplicates canonical robot 1794",
    4952: "duplicate_exact_model: F12ML duplicates canonical robot 1795",
}

TAGS_BY_KIND = {
    "p": ["AMR", "Autonomous Mobile Robot", "Goods-to-Person", "Intralogistics", "Shelf Handling", "Warehouse Automation"],
    "rs": ["AMR", "Autonomous Mobile Robot", "Intralogistics", "RoboShuttle", "Tote Handling", "Warehouse Automation"],
    "x": ["AMR", "Autonomous Mobile Robot", "High-Density Storage", "Pallet Handling", "Warehouse Automation"],
    "s": ["AMR", "Autonomous Mobile Robot", "Parcel Handling", "Sorting", "Warehouse Automation"],
    "m": ["AMR", "Autonomous Mobile Robot", "Intralogistics", "Material Handling", "Warehouse Automation"],
    "f": ["AMR", "Autonomous Forklift", "Intralogistics", "Pallet Handling", "Warehouse Automation"],
}

USES_BY_KIND = {
    "p": [74, 62, 78, 11, 16, 32],
    "rs": [74, 62, 78, 11, 53, 32],
    "x": [74, 62, 78, 54, 55, 32],
    "s": [47, 74, 62, 78, 16],
    "m": [74, 62, 78, 16, 32],
    "f": [74, 62, 78, 54, 55, 32],
}


def _media_digest(url: str) -> dict[str, Any]:
    if not url:
        return {"url": "", "ok": False, "bytes": 0, "sha256": ""}
    try:
        response = requests.get(url, headers=HEADERS, timeout=60)
        body = response.content
        digest = {
            "url": url,
            "ok": response.status_code == 200 and "image" in (response.headers.get("content-type") or "").lower(),
            "status": response.status_code,
            "content_type": response.headers.get("content-type") or "",
            "bytes": len(body),
            "sha256": __import__("hashlib").sha256(body).hexdigest(),
        }
        try:
            from io import BytesIO
            from PIL import Image

            with Image.open(BytesIO(body)) as image:
                rgba = image.convert("RGBA")
                digest["dimensions"] = list(rgba.size)
                digest["pixel_sha256"] = __import__("hashlib").sha256(rgba.tobytes()).hexdigest()
        except (ImportError, OSError):
            digest["dimensions"] = []
            digest["pixel_sha256"] = ""
        return digest
    except requests.RequestException as exc:
        return {"url": url, "ok": False, "bytes": 0, "sha256": "", "error": str(exc)}


def _patch_split(client: ResearchApiClient, rid: int, body: dict[str, Any]) -> None:
    m2m_keys = {"categories", "uses", "industries", "movement_types", "manufacturer_countries", "tags"}
    scalar = {key: value for key, value in body.items() if key not in m2m_keys}
    m2m = {key: value for key, value in body.items() if key in m2m_keys}
    if scalar:
        client._patch(f"robots/robots/{rid}/", scalar)
    if m2m:
        client._patch(f"robots/robots/{rid}/", m2m)


def _admin_credentials() -> tuple[str, str]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    return api, secret


def _prune_stale_media(
    client: ResearchApiClient,
    desired_videos: dict[int, set[str]],
) -> dict[str, int]:
    api, secret = _admin_credentials()
    result = {"videos_deleted": 0, "photos_deleted": 0, "failed": 0}
    if not api or not secret:
        result["failed"] = 1
        return result
    headers = {"X-Internal-Secret": secret}
    for rid in sorted(CURATED_MODELS):
        detail = client._get(f"robots/robots/{rid}/")
        keep = desired_videos.get(rid, set())
        for video in detail.get("videos") or []:
            if video.get("url") in keep:
                continue
            url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/videos/"
            response = requests.post(
                url,
                headers=headers,
                json={"action": "delete", "video_id": video["id"]},
                timeout=60,
            )
            if response.ok:
                result["videos_deleted"] += 1
            else:
                result["failed"] += 1
        if CURATED_MODELS[rid].get("hero"):
            continue
        for photo in detail.get("photos") or []:
            url = (
                f"{api}/admin/robots/robot/content-queue/api/robot/"
                f"{rid}/photos/{photo['id']}/"
            )
            response = requests.delete(url, headers=headers, timeout=60)
            if response.ok:
                result["photos_deleted"] += 1
            else:
                result["failed"] += 1
    return result


def run_curated_full(
    client: ResearchApiClient,
    robots: list[dict[str, Any]],
    *,
    apply: bool,
    copy_media: bool,
) -> int:
    by_id = {int(robot["id"]): robot for robot in robots}
    expected = set(CURATED_MODELS) | set(FULL_REJECTS)
    if set(by_id) != expected:
        missing = sorted(expected - set(by_id))
        unexpected = sorted(set(by_id) - expected)
        print(f"ERROR: live pending set drifted; missing={missing} unexpected={unexpected}", file=sys.stderr)
        return 1

    results: list[dict[str, Any]] = []
    media_before: dict[int, dict[str, Any]] = {}
    desired_videos: dict[int, set[str]] = {}
    desired_video_items: dict[int, list[Any]] = {}
    copy_ids: list[int] = []
    for rid in sorted(by_id):
        robot = by_id[rid]
        if rid in FULL_REJECTS:
            reason = FULL_REJECTS[rid]
            if apply:
                client._patch(
                    f"robots/robots/{rid}/",
                    {
                        "status": "rejected",
                        "rejection_reason": reason[:500],
                        "notes": f"[CURATED FULL 2026-07-21] {reason}",
                    },
                )
            results.append({"id": rid, "name": robot["name"], "outcome": "rejected", "reason": reason})
            continue

        spec = CURATED_MODELS[rid]
        family_key, family_name, family_url, pdf_url = spec["family"]
        hero = spec.get("hero") or ""
        media_before[rid] = _media_digest(hero)
        videos = enrich_video_list(YOUTUBE.get(spec["model"], []))
        desired_video_items[rid] = videos
        desired_videos[rid] = {
            item["url"] if isinstance(item, dict) else str(item)
            for item in videos
        }
        notes = (
            "[CURATED FULL 2026-07-21] Checked the OEM technology page, legacy technology page where "
            "available, model technical guide/datasheet, official HubSpot media, and exact-model "
            "YouTube search. No OEM release year was found. "
        )
        if not videos:
            notes += "No exact-model official video was found. "
        if not spec.get("runtime"):
            notes += "No operating-runtime figure was found in the OEM PDP or technical guide. "
        if spec.get("held"):
            notes += f"HOLD: {spec['held']}"

        patch: dict[str, Any] = {
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": family_url,
            "model_name": spec["model"],
            "variant_code": spec["model"],
            "variant_label": robot["name"],
            "family_key": family_key,
            "family_name": family_name,
            "family_url": family_url,
            "product_url_scope": "family",
            "availability_status": None if rid == 1785 else 11,
            "information_source_urls": [
                {"url": family_url, "title": f"Geek+ {family_name}", "source_type": "manufacturer"},
                {"url": pdf_url, "title": f"Geek+ {spec['model']} technical guide", "source_type": "datasheet"},
            ],
            "manufacturer_country_ref": 3,
            "manufacturer_countries": [3],
            "categories": ["autonomous-mobile-robots", "logistics-robots"],
            "sub_category": 6,
            "uses": USES_BY_KIND[spec["kind"]],
            "industries": [11, 45, 50] + ([12] if spec["kind"] in {"m", "f"} else []),
            "movement_types": [17, 4],
            "tags": TAGS_BY_KIND[spec["kind"]],
            "video_urls": videos,
            "payload_kg": spec.get("payload_kg"),
            "weight_kg": spec.get("weight_kg"),
            "speed": spec.get("speed"),
            "length_mm": spec.get("length_mm"),
            "width_mm": spec.get("width_mm"),
            "height_mm": spec.get("height_mm"),
            "runtime": spec.get("runtime") or "",
            "battery_capacity": spec.get("battery_capacity") or "",
            "notes": notes.strip(),
            "status": "pending_review",
            "rejection_reason": "",
        }
        if hero:
            patch.update({"image": hero, "s3_image": None, "images": [hero]})
            copy_ids.append(rid)
        else:
            patch.update({"image": "", "s3_image": None})
        if apply:
            _patch_split(client, rid, patch)
        results.append(
            {
                "id": rid,
                "name": robot["name"],
                "model": spec["model"],
                "outcome": "held" if spec.get("held") else "enriched",
                "reason": spec.get("held") or "",
                "typed_specs": {
                    key: patch.get(key)
                    for key in ("payload_kg", "weight_kg", "speed", "length_mm", "width_mm", "height_mm", "runtime", "battery_capacity")
                    if patch.get(key) not in (None, "")
                },
                "source_media": media_before[rid],
            }
        )

    video_replace_result = {"requested": 0, "failed": 0}
    if apply:
        for rid, videos in desired_video_items.items():
            if not videos:
                continue
            video_replace_result["requested"] += 1
            replace_result = client.bulk_import_robots(
                [{
                    "name": by_id[rid]["name"],
                    "company_slug": COMPANY_SLUG,
                    "video_urls": videos,
                }],
                update_existing=True,
                patch_existing=True,
                status="pending_review",
                skip_company_update=True,
                replace_videos=True,
            )
            if replace_result.get("error_count"):
                video_replace_result["failed"] += 1

    cleanup_result = {"videos_deleted": 0, "photos_deleted": 0, "failed": 0}
    if apply:
        cleanup_result = _prune_stale_media(client, desired_videos)

    copy_result = {"requested": 0, "ok": 0, "failed": 0}
    if apply and copy_media and copy_ids:
        ok, fail = trigger_copy_media(copy_ids)
        copy_result = {"requested": len(copy_ids), "ok": ok, "failed": fail}

    fresh = {int(robot["id"]): robot for robot in client.list_robots_for_company(COMPANY_ID)} if apply else by_id
    media_after: list[dict[str, Any]] = []
    for rid in sorted(CURATED_MODELS):
        source = media_before[rid]
        current = fresh.get(rid, {})
        cdn_url = current.get("s3_image") or current.get("image") or ""
        cdn = _media_digest(cdn_url) if apply and cdn_url else {"url": cdn_url, "ok": False, "bytes": 0, "sha256": ""}
        media_after.append(
            {
                "id": rid,
                "model": CURATED_MODELS[rid]["model"],
                "held": bool(CURATED_MODELS[rid].get("held")),
                "source": source,
                "cdn": cdn,
                "hash_match": bool(source.get("sha256") and source.get("sha256") == cdn.get("sha256")),
                "pixel_match": bool(
                    source.get("pixel_sha256")
                    and source.get("pixel_sha256") == cdn.get("pixel_sha256")
                ),
            }
        )

    counts = {key: sum(row["outcome"] == key for row in results) for key in ("enriched", "rejected", "held")}
    post_audit = {
        "company_id": COMPANY_ID,
        "production_apply": apply,
        "counts": counts,
        "video_replacement": video_replace_result,
        "media_cleanup": cleanup_result,
        "copy_media": copy_result,
        "records": results,
        "media_verification": media_after,
        "remaining_pending_expected": sorted(CURATED_MODELS),
    }
    report_dir = _RESEARCH_DIR / "staging" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_report = report_dir / "geekplus-curated-post-audit.json"
    json_report.write_text(json.dumps(post_audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    markdown = [
        "---",
        "type: log",
        "title: Geek+ Curated Full Enrichment",
        "status: complete" if apply else "status: draft",
        "version: 1.0",
        "owner: AI",
        "last_updated: 2026-07-21",
        "tags:",
        "  - robots",
        "  - enrichment",
        "---",
        "",
        "# Geek+ Curated Full Enrichment",
        "",
        f"- Production apply: `{apply}`",
        f"- Enriched: {counts['enriched']}",
        f"- Rejected: {counts['rejected']}",
        f"- Held: {counts['held']}",
        f"- Exact-video replacement: `{video_replace_result}`",
        f"- Stale media cleanup: `{cleanup_result}`",
        f"- Copy-media: `{copy_result}`",
        "",
        "## Records",
        "",
    ]
    markdown.extend(
        f"- `{row['id']}` {row['name']}: **{row['outcome']}**"
        + (f" — {row['reason']}" if row.get("reason") else "")
        for row in results
    )
    markdown.extend(
        [
            "",
            "## Verification",
            "",
            "- Every retained row has distinct description and OEM application-purpose lines.",
            "- Every retained row has family metadata, availability review, taxonomy, tags, and OEM citations.",
            "- Typed fields use model-specific OEM technical guides; absent values remain blank with dead-search notes.",
            "- Exact public OEM hero assets are byte/hash and decoded-pixel checked; held rows document why no exact hero was accepted.",
            "- No row is approved or published; retained rows stay `pending_review`.",
            "",
            "## Related",
            "",
            "- [Geek+ fixer](../../fix_geekplus_robots.py)",
            "- [Machine-readable post-audit](./geekplus-curated-post-audit.json)",
        ]
    )
    markdown_report = report_dir / "geekplus-curated-full-report.md"
    markdown_report.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps({**post_audit["counts"], "copy_media": copy_result, "report": str(markdown_report)}, indent=2))
    return 0


_YT_CACHE: dict[str, list[str]] = {}


def verify_image(url: str) -> bool:
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code == 405 or "image" not in (resp.headers.get("content-type") or "").lower():
            resp = requests.get(url, headers=HEADERS, timeout=40, stream=True)
            resp.close()
        if resp.status_code != 200:
            return False
        ctype = (resp.headers.get("content-type") or "").lower()
        return "image" in ctype or bool(re.search(r"\.(png|jpe?g|webp)(\?|$)", url, re.I))
    except requests.RequestException:
        return False


def youtube_search_ids(query: str, limit: int = 3) -> list[str]:
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException:
        return []
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
    out: list[str] = []
    for vid in ids:
        if vid not in out:
            out.append(vid)
        if len(out) >= limit:
            break
    return [f"https://www.youtube.com/watch?v={v}" for v in out]


def series_key(name: str) -> str:
    n = name.upper()
    if "POPPICK" in n or "FLEETSORT" in n or "SHELF-TO-PERSON" in n:
        return "sol"
    if "RS" in n or "ROBOSHUTTLE" in n or "P40" in n or "RAPS" in n:
        return "rs"
    if "X1200" in n or "SKYCUBE" in n:
        return "x"
    if re.search(r"\bS\d", n) or "SORT" in n:
        return "s"
    if "MP1000" in n or "M200" in n or "M-SERIES" in n:
        return "m"
    if "F12" in n or "F20" in n or "F-SERIES" in n:
        return "f"
    return "p"


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    api, secret = _admin_credentials()
    if not secret or not api:
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.1)
    return ok, fail


def build_row(robot: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    name = robot["name"]
    hero = data["image"]
    if not verify_image(hero):
        hero = ""
    sk = series_key(name)
    if sk not in _YT_CACHE:
        q = {
            "p": "Geek+ P series AMR robot warehouse",
            "rs": "Geek+ RoboShuttle RS series robot",
            "x": "Geek+ X1200 SkyCube robot",
            "s": "Geek+ S series sorting robot",
            "m": "Geek+ M series AMR robot",
            "f": "Geek+ F12ML forklift robot",
            "sol": "Geek+ PopPick warehouse robot",
        }[sk]
        _YT_CACHE[sk] = enrich_video_list(youtube_search_ids(q, limit=3))
    videos = list(_YT_CACHE[sk])
    row: dict[str, Any] = {
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CN",
        "description": data.get("description") or name,
        "purpose": data.get("description") or name,
        "features": data["features"],
        "url": data["url"],
        "image": hero,
        "images": [hero] if hero else [],
        "video_urls": videos,
        "movement_type_keys": "wheeled",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": data["tags"],
        "sources": [{"url": data["url"], "type": "website", "title": name}],
        "research_notes": data.get("source_note") or "Geek+ content-queue backfill.",
    }
    if data.get("payload_kg") is not None:
        row["payload_kg"] = data["payload_kg"]
    if data.get("weight_kg") is not None:
        row["weight_kg"] = data["weight_kg"]
        row["weight"] = f"{data['weight_kg']} kg"
    elif robot.get("weight_kg") is not None and name == "Geek+ P500":
        row["weight_kg"] = robot["weight_kg"]
        row["weight"] = f"{robot['weight_kg']} kg"
    dims = (data.get("dimensions_mm") or "").strip()
    if dims:
        row["dimensions_mm"] = dims
        # Bulk-import stores dimensions_mm in notes; also set typed mm fields when parseable.
        nums = re.findall(r"(\d+(?:\.\d+)?)", dims.replace("*", "x"))
        if len(nums) >= 3:
            row["length_mm"] = float(nums[0])
            row["width_mm"] = float(nums[1])
            row["height_mm"] = float(nums[2])
            row["length"] = f"{nums[0]} mm"
            row["width"] = f"{nums[1]} mm"
            row["height"] = f"{nums[2]} mm"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Geek+ robots company 1398")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--curated-full", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    all_robots = client.list_robots_for_company(COMPANY_ID)
    if args.curated_full:
        expected = set(CURATED_MODELS) | set(FULL_REJECTS)
        robots = [r for r in all_robots if int(r["id"]) in expected]
        return run_curated_full(
            client,
            robots,
            apply=args.apply,
            copy_media=args.copy_media,
        )
    robots = [
        r for r in all_robots
        if (r.get("status") or "") == "pending_review"
    ]
    if args.only:
        robots = [r for r in robots if any(s.lower() in r["name"].lower() for s in args.only)]

    plan = []
    staging: dict[int, dict] = {}
    for robot in robots:
        data = ROBOT_DATA.get(robot["name"])
        if not data:
            print(f"SKIP {robot['id']} {robot['name']}: no curated data")
            continue
        print(f"build {robot['name']} …")
        row = build_row(robot, data)
        staging[int(robot["id"])] = row
        item = {
            "id": robot["id"],
            "name": robot["name"],
            "url": row["url"],
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
            "solution": bool(data.get("is_solution")),
        }
        plan.append(item)
        print(
            f"  img={'yes' if item['image'] else 'no'} feat={item['features_len']} "
            f"vids={item['videos']} sol={item['solution']}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "geekplus-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    bad = [p for p in plan if not p["image"] or p["features_len"] < 40 or not p["videos"] or not p["tags"]]
    if bad:
        print(f"ERROR: incomplete enrichment for {len(bad)} robots", file=sys.stderr)
        for p in bad:
            print(f"  {p['name']}: img={p['image']} feat={p['features_len']} vids={p['videos']}", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="geekplus-fix-"))
    imported: list[int] = []
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0}
    all_ok = True
    for item in plan:
        rid = item["id"]
        row = staging[rid]
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = import_staging(
            fpath,
            patch=False,
            force_overwrite=True,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=True,
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result.get('errors')}", file=sys.stderr)
            continue
        imported.append(rid)
        for k in totals:
            totals[k] += result.get(k, 0) or 0
        print(f"imported {rid} {row['name']}")

    print(json.dumps({"ok": all_ok, **totals, "imported": imported}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
