"""Text/spec/tag/year pass for the 31 thin-content Ecovacs records (company 32).

Companion to ``fix_ecovacs_robots.py`` (which handles the *greenfield* 47xx
records). These targets are DIFFERENT: they already carry a description and a
media gallery, but their `features` are either a ~55-char stub or — worse —
boilerplate copied from an unrelated product (the ULTRAMARINE P1 *pool cleaner*:
"4800GPH UltraPure Suction", "scrubs pool floors and walls"), which is present
verbatim on 13 records including the AIRBOT Z1 air purifier. Tags are junk
fleet-wide (`long`, `round`, `space`, `gate`, `profile`, plus Drone/Humanoid on
vacuums). Every `url` points at a category page rather than a model PDP.

Why direct DRF PATCH instead of bulk-import patch mode:
- bulk-import patch mode NEVER overwrites a non-blank field, and every target
  here has non-blank (wrong) features/purpose/tags — so patch mode is a no-op.
- `force_overwrite` sends '' for every unsent field and WILL wipe features and
  media. Same trap documented in lessons.md (Noblelift descriptions).
  `client._patch('robots/robots/<id>/')` hits RobotSerializer (a full
  ModelSerializer), which updates exactly the keys we send and upserts
  information sources via `information_source_urls`.

Media is deliberately NOT touched here (see the audit finding in lessons.md):
the existing galleries are byte-shared across whole families and need their own
pass. Run `audit_ecovacs_media.py --live --ids ...` to see the damage.

    python fix_ecovacs_thin_content.py                  # dry-run preview
    python fix_ecovacs_thin_content.py --apply
    python fix_ecovacs_thin_content.py --apply --ids 1937,1939
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 32
SKIP_STATUSES = {"published", "approved"}

G = "https://www.ecovacs.com/global"
U = "https://www.ecovacs.com/us/shop"
V = "deebot-robotic-vacuum-cleaner"
W = "winbot-window-cleaning-robot"
O = "goat-robotic-lawn-mower"

# TagCatalog-exact names (verified against list_tags()). Family-correct:
# a DEEBOT vacuum, a GOAT mower, a WINBOT window robot and the AIRBOT air
# purifier must NOT share a tag set.
TAGS_VACUUM = ["Robot Vacuum", "Home Cleaning", "Cleaning", "Smart Home", "AI",
               "Autonomous", "Wheeled", "Ground", "Navigation", "Consumer"]
TAGS_MOWER = ["Outdoor", "All-Terrain", "Autonomous", "AI", "Navigation",
              "Wheeled", "Ground", "Smart Home", "Consumer"]
TAGS_WINDOW = ["Cleaning", "Home Cleaning", "Smart Home", "AI", "Autonomous",
               "Navigation", "Consumer", "Indoor"]
TAGS_AIR = ["Smart Home", "AI", "Autonomous", "Navigation", "Consumer",
            "Indoor", "Monitoring", "Wheeled", "Ground"]

# Frequently reused citations.
SRC_CES25 = {"url": "https://www.prnewswire.com/news-releases/ecovacs-unveils-next-gen-smart-home-robotic-vacuum-cleaners-and-beyond-at-ces-2025-302342025.html",
             "type": "press", "title": "ECOVACS unveils next-gen robot vacuums at CES 2025 (PR Newswire)"}
SRC_CES26 = {"url": "https://www.prnewswire.com/news-releases/ecovacs-showcases-its-acceleration-towards-full-scenario-service-robotics-at-ces-2026-302653595.html",
             "type": "press", "title": "ECOVACS at CES 2026 (PR Newswire)"}
SRC_VW_ROLLER = {"url": "https://vacuumwars.com/ecovacs-expands-deebot-lineup-with-two-new-ozmo-roller-models/",
                 "type": "review", "title": "Ecovacs Expands Deebot Lineup with OZMO Roller Models - mid-May 2025 (Vacuum Wars)"}


def _oem(url: str, title: str) -> dict:
    return {"url": url, "type": "website", "title": title}


# id -> curated record. `features` and `purpose` are hand-written per model from
# the OEM PDP (see scripts/research/staging/reports/ecovacs-thin-recon.json).
# release_year is present ONLY with a grounded citation; otherwise absent.
ROBOT_DATA: dict[int, dict[str, Any]] = {
    1937: {
        "name": "ECOVACS DEEBOT X5 OMNI",
        "url": f"{G}/{V}/deebot-x5-omni-white",
        "purpose": "Cleans hard floors and carpets throughout the home, vacuuming and mopping in one pass and returning to its OMNI Station to empty, wash and dry itself.",
        "features": (
            "12,800Pa suction power | Ultra-thin and ultra-narrow body reaches under and "
            "between furniture | OZMO ROLLER self-washing mop with continuous rinsing | "
            "ZeroTangle 2.0 anti-tangle brush | TruEdge 2.0 adaptive edge mopping | "
            "15mm auto mop-lifting for carpets | 22mm threshold crossing | "
            "Up to 164 min runtime | "
            "OMNI Station with hot-water mop washing and hot-air drying"
        ),
        "runtime_minutes": 164,
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{G}/{V}/deebot-x5-omni-white", "DEEBOT X5 OMNI WHITE - ECOVACS Global (specs)")],
    },
    1939: {
        "name": "ECOVACS DEEBOT X9 PRO OMNI",
        "url": f"{U}/{V}/deebot-x9-pro-omni",
        "purpose": "Flagship whole-home floor care - vacuums and wet-mops in a single pass, detects and re-cleans stains, and handles its own emptying, mop washing and drying.",
        "features": (
            "BLAST system: 16.3L/s airflow with 16,600Pa suction | "
            "OZMO ROLLER self-washing mop at up to 220 rpm and 3,700Pa mopping pressure | "
            "TruEdge 2.0 with 3D edge sensor | AIVI 3D 3.0 omni-approach obstacle avoidance | "
            "AI Stain Detection 2.0 | 6,400mAh battery with 2.4x battery lifespan | "
            "Up to 3h 6min runtime | Dedicated carpet care"
        ),
        "battery_capacity": "6400mAh",
        "runtime_minutes": 186,
        "release_year": 2025,
        "year_cite": "release_year=2025: Ecovacs announced the X9 PRO OMNI (with the T80 OMNI) for a mid-May 2025 release (Vacuum Wars).",
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{U}/{V}/deebot-x9-pro-omni", "DEEBOT X9 PRO OMNI - ECOVACS US (specs)"), SRC_VW_ROLLER],
    },
    1941: {
        "name": "ECOVACS DEEBOT T50 MAX PRO OMNI",
        "url": f"{U}/{V}/deebot-t50-max-pro-omni",
        "purpose": "Daily vacuuming and mopping across hard floors and carpets, with a station that empties the dust, washes the mop in hot water and dries it between runs.",
        "features": (
            "18,500Pa suction with 16.3L/s airflow | 100W high-torque motor | "
            "45% larger battery delivering up to 206 min runtime | "
            "TruEdge 2.0 complete edge and corner cleaning | "
            "22mm (0.87 in) threshold crossing | dToF LiDAR navigation with obstacle avoidance | "
            "OMNI Station with hot-water mop washing, drying, auto-empty and refill"
        ),
        "runtime_minutes": 206,
        "release_year": 2025,
        "year_cite": "release_year=2025: DEEBOT T50 Series unveiled at CES 2025 (Jan 6, 2025) per ECOVACS/PR Newswire.",
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{U}/{V}/deebot-t50-max-pro-omni", "DEEBOT T50 MAX PRO OMNI - ECOVACS US (specs)"), SRC_CES25],
    },
    1943: {
        "name": "ECOVACS DEEBOT T50 OMNI",
        "url": f"{U}/{V}/deebot-t50-omni",
        "purpose": "Automates routine floor cleaning in the home, vacuuming and mopping under low furniture thanks to an ultra-thin chassis, then self-cleaning at its station.",
        "features": (
            "15,000Pa suction power | 3.19-inch (81mm) ultra-thin body reaches under low furniture | "
            "ZeroTangle 2.0 anti-tangle technology | TruEdge 2.0 adaptive edge cleaning | "
            "OZMO Turbo 2.0 mopping with auto-lift and carpet strategy | "
            "TrueMapping 2.0 navigation | YIKO-GPT AI voice assistant | "
            "Self-cleaning OMNI Station with hot wash and drying"
        ),
        # "3.19inch Ultra-Thin DEEBOT" stated on the OEM PDP -> robot height.
        "height_mm": 81.0,
        "release_year": 2025,
        "year_cite": "release_year=2025: DEEBOT T50 Series unveiled at CES 2025 (Jan 6, 2025) per ECOVACS/PR Newswire.",
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{U}/{V}/deebot-t50-omni", "DEEBOT T50 OMNI - ECOVACS US (specs)"), SRC_CES25],
    },
    1945: {
        "name": "ECOVACS WINBOT W2 OMNI",
        "url": f"{U}/{W}/winbot-w2-omni",
        "purpose": "Cleans household windows and glass automatically - adheres to the pane, plans full edge-to-edge coverage, and works from a portable station so it can be carried between windows.",
        "features": (
            "Portable station doubles as a carry case and power source | "
            "WIN-SLAM intelligent path planning for full-pane coverage | "
            "TruEdge edge-to-edge cleaning into frames and corners | "
            "Anti-drop safety system with backup power and safety tether | "
            "Automatic spray for even solution distribution | "
            "Cordless operation between windows"
        ),
        "tags": TAGS_WINDOW,
        # Glass-adhering climbing robot - NOT a ground/wheeled platform.
        "movement": "other",
        "sources": [_oem(f"{U}/{W}/winbot-w2-omni", "WINBOT W2 OMNI - ECOVACS US (specs)")],
    },
    1947: {
        "name": "ECOVACS WINBOT W2S",
        "url": f"{U}/{W}/winbot-w2s",
        "purpose": "Washes household window glass without manual effort - climbs the pane, sprays and wipes edge to edge, and stays attached with a backup power and tether system.",
        "features": (
            "3-nozzle spray system for even solution coverage | "
            "10-level water volume control | Edge-cleaning coverage into frames and corners | "
            "3,000mAh lithium battery for cordless operation | "
            "Quiet operation at 68dB | Handles 2mm-4mm framed and frameless glass | "
            "Anti-drop protection with safety tether"
        ),
        "battery_capacity": "3000mAh",
        "tags": TAGS_WINDOW,
        "movement": "other",
        "sources": [_oem(f"{U}/{W}/winbot-w2s", "WINBOT W2S - ECOVACS US (specs)")],
    },
    1949: {
        "name": "ECOVACS WINBOT W3",
        "url": f"{G}/{W}/winbot-w3",
        "purpose": "Cleans windows and glass surfaces in the home autonomously, removing the need to wipe panes by hand or work at height.",
        "features": (
            "Strong adsorption keeps the robot attached to vertical glass | "
            "Intelligent path planning for complete pane coverage | "
            "Edge-to-edge cleaning into frames and corners | "
            "Automatic spray and wiping pad system | "
            "Anti-dropping protection mechanism | "
            "Works on framed and frameless windows"
        ),
        "tags": TAGS_WINDOW,
        "movement": "other",
        "sources": [_oem(f"{G}/{W}/winbot-w3", "WINBOT W3 - ECOVACS Global")],
    },
    1951: {
        "name": "ECOVACS GOAT A3000",
        "url": f"{G}/{O}/goat-a3000-lidar",
        "purpose": "Mows a domestic lawn without boundary wires - maps the garden with dual LiDAR, plans efficient routes, avoids obstacles and returns to its station to recharge.",
        "features": (
            "HoloScope 360 dual-LiDAR navigation, wire-free setup with 2cm positioning accuracy | "
            "32V platform with speedy dual blade-discs | 33cm (13 in) cutting width | "
            "AI Vision recognising 200+ obstacle types plus 3D-ToF LiDAR | "
            "Covers up to 500 m2 per charge; 45 min recharge with 180W fast charging | "
            "Slope climbing up to 50% (27 degrees) | 4cm barrier crossing | IPX6 waterproof body"
        ),
        "charging_time_minutes": 45,
        "voltage": "32V",
        "release_year": 2025,
        "year_cite": "release_year=2025: GOAT A3000 LiDAR is the 2025 GOAT lineup model (9to5toys Dec 2025 pricing coverage; Freshly Charged '2025 Ecovacs GOAT A3000 LiDAR'). The A3000 LiDAR PRO is the later 2026 refresh.",
        "tags": TAGS_MOWER,
        "sources": [
            _oem(f"{G}/{O}/goat-a3000-lidar", "GOAT A3000 LiDAR - ECOVACS Global (specs)"),
            {"url": "https://9to5toys.com/2025/12/17/ecovacs-goat-a3000-lidar-robot-lawn-mower-2100/",
             "type": "press", "title": "ECOVACS Goat A3000 LiDAR robot lawn mower - 2025 pricing (9to5toys)"},
        ],
    },
    1954: {
        "name": "ECOVACS GOAT O800",
        "url": f"{G}/{O}/goat-o800-rtk-white",
        "purpose": "Keeps a small-to-medium domestic lawn cut without perimeter wires, navigating by RTK satellite positioning and returning to its base to recharge.",
        "features": (
            "RTK satellite positioning for wire-free boundary setup | "
            "Systematic route planning for even lawn coverage | "
            "Obstacle detection and avoidance during mowing | "
            "App-based mapping, scheduling and zone control | "
            "IPX6 waterproof body | Automatic return to base for recharging"
        ),
        "tags": TAGS_MOWER,
        "sources": [_oem(f"{G}/{O}/goat-o800-rtk-white", "GOAT O800 RTK WHITE - ECOVACS Global")],
    },
    1955: {
        "name": "ECOVACS DEEBOT T30 Pro",
        "url": f"{G}/{V}/deebot-t30-pro-omni-white",
        "purpose": "Handles everyday vacuuming and mopping across the home, lifting its mop for carpet and refilling its own small water tank from the station.",
        "features": (
            "11,000Pa suction power | OZMO TURBO 2.0 rotating mop system | "
            "TruEdge adaptive edge mopping | ZeroTangle anti-tangle roller brush | "
            "TrueDetect 3D 3.0 obstacle avoidance and TrueMapping 2.0 navigation | "
            "9mm auto mop-lifting for carpets | Auto small tank refill | "
            "Mini OMNI Station with 70C hot-water mop washing and easy-maintenance design"
        ),
        "release_year": 2024,
        "year_cite": "release_year=2024: DEEBOT T30 PRO OMNI launched May 2024 for major markets (ECOVACS AU newsroom; Ausdroid 23 May 2024; Singapore availability 25 Mar 2024).",
        "tags": TAGS_VACUUM,
        "sources": [
            _oem(f"{G}/{V}/deebot-t30-pro-omni-white", "DEEBOT T30 PRO OMNI WHITE - ECOVACS Global (specs)"),
            {"url": "https://www.ecovacs.com/au/newsroom/official-news/deebot-t30-pro-omni-launch",
             "type": "press", "title": "ECOVACS Launch DEEBOT T30 PRO OMNI - ECOVACS AU newsroom (2024)"},
        ],
    },
    1956: {
        "name": "ECOVACS DEEBOT T30 Omni",
        "url": f"{G}/{V}/deebot-t30-omni-black",
        "purpose": "Vacuums and mops hard floors and carpets on a schedule, then empties its dustbin and washes and dries its mop pads at the OMNI Station.",
        "features": (
            "11,000Pa suction power | OZMO TURBO 2.0 rotating mop system | "
            "ZeroTangle anti-tangle roller brush | TruEdge adaptive edge mopping | "
            "TrueDetect 3D 3.0 obstacle avoidance and TrueMapping 2.0 navigation | "
            "9mm auto mop-lifting for carpets | Auto small tank refill | "
            "OMNI Station with hot-water mop washing and hot-air drying"
        ),
        "release_year": 2024,
        "year_cite": "release_year=2024: DEEBOT T30 series launched 2024 (ECOVACS AU newsroom T30 PRO OMNI launch, May 2024; TechRadar T30 Omni review 2024).",
        "tags": TAGS_VACUUM,
        "sources": [
            _oem(f"{G}/{V}/deebot-t30-omni-black", "DEEBOT T30 OMNI BLACK - ECOVACS Global (specs)"),
            {"url": "https://www.techradar.com/home/robot-vacuums/ecovacs-deebot-t30-omni-robot-vacuum-review",
             "type": "review", "title": "Ecovacs Deebot T30 Omni review (TechRadar)"},
        ],
    },
    1957: {
        "name": "ECOVACS DEEBOT X5 Pro Omni",
        "url": f"{U}/{V}/deebot-x5-pro-omni",
        "purpose": "Cleans large homes end to end, vacuuming and mopping in one pass with a long-runtime battery and a station that maintains the mop unattended.",
        "features": (
            "12,800Pa suction power | Ultra-thin, ultra-narrow D-shaped body for reach "
            "under and between furniture | OZMO ROLLER self-washing mop with continuous rinsing | "
            "ZeroTangle 2.0 anti-tangle brush | TruEdge 2.0 adaptive edge mopping | "
            "Up to 224 min runtime covering approximately 320 m2 in standard mode | "
            "AIVI 3D obstacle avoidance | OMNI Station with hot-water washing and hot-air drying"
        ),
        "runtime_minutes": 224,
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{U}/{V}/deebot-x5-pro-omni", "DEEBOT X5 PRO OMNI - ECOVACS US (specs)")],
    },
    1958: {
        "name": "ECOVACS DEEBOT X2 Omni",
        "url": f"{U}/{V}/deebot-x2-omni",
        "purpose": "Vacuums and mops the whole home, using a squared chassis to reach further into corners than a round robot, and self-maintains at its station.",
        "features": (
            "Squared chassis design reaches deeper into corners | 8,000Pa suction power | "
            "6,400mAh battery with charging speed increased 45% over the X1 | "
            "Up to 212 min runtime covering approximately 435 m2 | "
            "AIVI 3D and TrueMapping 2.0 dual-laser navigation | "
            "Robot weight approximately 5kg; station approximately 11kg | "
            "OMNI Station with auto-empty, hot-water mop washing and hot-air drying"
        ),
        "battery_capacity": "6400mAh",
        "runtime_minutes": 212,
        "weight_kg": 5.0,
        "release_year": 2023,
        "year_cite": "release_year=2023: DEEBOT X2 OMNI announced at ECOVACS' Global Launch Event 17 Aug 2023, shown at IFA 2023 (Berlin, 1-5 Sept 2023), US availability 3 Oct 2023 (PR Newswire; Vacuum Wars; Reviewed).",
        "tags": TAGS_VACUUM,
        "sources": [
            _oem(f"{U}/{V}/deebot-x2-omni", "DEEBOT X2 OMNI - ECOVACS US (specs)"),
            {"url": "https://www.prnewswire.com/news-releases/ecovacs-debuts-newly-designed-deebot-x2-omni-to-clean-every-square-inch-of-your-floors-301933939.html",
             "type": "press", "title": "ECOVACS debuts newly designed DEEBOT X2 OMNI (PR Newswire, 2023)"},
        ],
    },
    1959: {
        "name": "ECOVACS DEEBOT N30 Pro",
        "url": f"{G}/{V}/deebot-n30pro-omni-white",
        "purpose": "Provides routine vacuuming and mopping for the home at a mid-range price, with station-based mop washing and dust emptying.",
        "features": (
            "10,000Pa suction power | OZMO mopping with auto mop-lifting for carpets | "
            "ZeroTangle anti-tangle roller brush | TrueMapping laser navigation | "
            "Edge-adaptive mopping into corners | "
            "OMNI Station with auto-empty, mop washing and hot-air drying"
        ),
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{G}/{V}/deebot-n30pro-omni-white", "DEEBOT N30 PRO OMNI WHITE - ECOVACS Global (specs)")],
    },
    1960: {
        "name": "ECOVACS DEEBOT T20 Omni",
        "url": f"{U}/{V}/deebot-t20-omni",
        "purpose": "Vacuums and mops household floors, lifting its mop pads to cross carpet and washing them in hot water at the station between runs.",
        "features": (
            "6,000Pa suction power | Hot-water mop washing at the OMNI Station | "
            "Auto mop-lifting with carpet detection | TrueMapping 2.0 laser navigation | "
            "TrueDetect 3D obstacle avoidance | 5,200mAh battery | "
            "Robot dimensions 362 x 362 x 103.5mm; station 448 x 430 x 578mm | "
            "Auto-empty, auto water refill and drying"
        ),
        "battery_capacity": "5200mAh",
        "length_mm": 362.0,
        "width_mm": 362.0,
        "height_mm": 103.5,
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{U}/{V}/deebot-t20-omni", "DEEBOT T20 OMNI - ECOVACS US (specs)")],
    },
    1961: {
        "name": "ECOVACS WINBOT W2 PRO",
        "url": f"{U}/{W}/winbot-w2-pro",
        "purpose": "Cleans household window glass hands-free, climbing the pane under its own suction and covering it edge to edge while a tether guards against falls.",
        "features": (
            "Smart climbing system for stable vertical movement on glass | "
            "260mm x 251mm compact footprint | 3,000mAh lithium battery | "
            "Approximately 30 min of battery operation during a power interruption | "
            "Edge-to-edge cleaning into frames and corners | "
            "Automatic spray and wiping system | Anti-drop protection with safety tether"
        ),
        "battery_capacity": "3000mAh",
        "tags": TAGS_WINDOW,
        "movement": "other",
        "sources": [_oem(f"{U}/{W}/winbot-w2-pro", "WINBOT W2 PRO - ECOVACS US (specs)")],
    },
    1962: {
        "name": "ECOVACS WINBOT W1 PRO",
        "url": f"{U}/{W}/winbot-w1-pro",
        "purpose": "Washes household windows automatically, spraying and wiping the glass in a planned path so panes are cleaned without manual work at height.",
        "features": (
            "2,800Pa adsorption power holds the robot to the glass | "
            "Dual cross auto-spray for even solution coverage | "
            "Intelligent path planning for complete pane coverage | "
            "Works on framed and frameless windows | "
            "Anti-drop protection with safety tether and backup power | "
            "Cleans a standard pane in approximately 2 min 50 s"
        ),
        "tags": TAGS_WINDOW,
        "movement": "other",
        "sources": [_oem(f"{U}/{W}/winbot-w1-pro", "WINBOT W1 PRO - ECOVACS US (specs)")],
    },
    1963: {
        "name": "ECOVACS GOAT G1",
        "url": f"{G}/campaign/goat-robotic-lawn-mower",
        "purpose": "Mows a domestic lawn without a buried boundary wire, using UWB beacons to learn the lawn edge and a camera to avoid pets, hoses and garden objects.",
        "features": (
            "Wire-free boundary setup using ultra-wideband (UWB) beacons | "
            "AIVI 3D obstacle avoidance with a 150-degree fisheye camera and ToF module | "
            "Onboard 360-degree camera doubles as a garden security camera | "
            "Mows a standard 600 m2 lawn in a single day | "
            "Cutting height adjustable 3-6cm | App-based zone mapping and scheduling"
        ),
        "release_year": 2023,
        "year_cite": "release_year=2023: GOAT G1 launched at IFA 2023; available in Australia from 21 Sept 2023 at RRP AU$2,999 (Appliance Retailer; EFTM).",
        "tags": TAGS_MOWER,
        "sources": [
            {"url": "https://www.applianceretailer.com.au/ifa-2023-ecovacs-expands-into-robotic-lawn-mowing/",
             "type": "press", "title": "IFA 2023: ECOVACS expands into robotic lawn mowing (Appliance Retailer)"},
            {"url": "https://eftm.com/2023/09/ecovacs-goes-from-floors-to-lawns-with-the-goat-g1-robotic-lawn-mower-237274",
             "type": "review", "title": "Ecovacs goes from floors to lawns with the GOAT G1 (EFTM, Sept 2023)"},
        ],
    },
    1964: {
        "name": "ECOVACS GOAT G1 Plus",
        "url": f"{G}/campaign/goat-robotic-lawn-mower",
        "purpose": "Mows a domestic lawn wire-free, using UWB beacons for boundaries and camera-based obstacle avoidance, in the larger-capacity configuration of the GOAT G1 line.",
        "features": (
            "Wire-free boundary setup using ultra-wideband (UWB) beacons | "
            "AIVI 3D obstacle avoidance with fisheye camera and ToF module | "
            "Onboard 360-degree camera doubles as a garden security camera | "
            "App-based zone mapping, scheduling and cutting-height control | "
            "Automatic return to base for recharging"
        ),
        "tags": TAGS_MOWER,
        "sources": [
            {"url": "https://www.notebookcheck.net/ECOVACS-announces-two-new-GOAT-G1-robot-lawn-mowers.807942.0.html",
             "type": "press", "title": "ECOVACS announces two new GOAT G1 robot lawn mowers (NotebookCheck)"},
        ],
    },
    1965: {
        "name": "ECOVACS AIRBOT Z1",
        "url": f"{G}/campaign/airbot-z1",
        "purpose": "Purifies indoor air where people actually are - drives itself from room to room, measures air quality on the move, and filters and disinfects the air instead of sitting in one corner.",
        "features": (
            "600 m3/h CADR air purification with HEPA H13 filtration | "
            "UV disinfection module eliminating up to 99.9% of tested bacteria and viruses | "
            "Self-propelled: drives between rooms rather than sitting in one spot | "
            "TrueMapping 2.0 SLAM navigation with obstacle detection up to 10m | "
            "960P HD starlight camera for day and night home monitoring | "
            "Real-time temperature, humidity and VOC air-quality sensing | "
            "2L tank for humidification | 5,200mAh battery, approximately 3h operation | "
            "YIKO voice assistant and ECOVACS Home app control"
        ),
        "battery_capacity": "5200mAh",
        "weight_kg": 14.0,
        "length_mm": 369.0,
        "width_mm": 350.0,
        "height_mm": 523.0,
        "release_year": 2022,
        "year_cite": "release_year=2022: AIRBOT Z1 launched at IFA 2022 (NotebookCheck: 'ECOVACS AIRBOT Z1 air purifying robot launches in Europe with AI camera'; Homecrux IFA 2022 coverage).",
        "tags": TAGS_AIR,
        "sources": [
            {"url": "https://www.notebookcheck.net/ECOVACS-AIRBOT-Z1-air-purifying-robot-launches-in-Europe-with-AI-camera.661203.0.html",
             "type": "press", "title": "ECOVACS AIRBOT Z1 launches in Europe with AI camera (NotebookCheck, IFA 2022)"},
            {"url": "https://www.homecrux.com/ecovacs-airbot-z1-moving-air-purifier/180017/",
             "type": "press", "title": "AIRBOT Z1 is an Air Purifying Robot that Moves from Room to Room (Homecrux)"},
        ],
    },
    2473: {
        "name": "ECOVACS DEEBOT mini 2",
        "url": f"{G}/{V}/deebot-mini-2-white",
        "purpose": "Cleans small homes and apartments where a full-size robot will not fit, vacuuming and mopping from a compact all-in-one station.",
        "features": (
            "10,000Pa suction power | ZeroTangle 4.0 anti-tangle system | "
            "OZMO Turbo 2.0 intensive mopping | "
            "TrueMapping 2.0 laser mapping with TrueDetect 3D obstacle avoidance | "
            "Ultra-compact body for mobility in small spaces | "
            "Space-saving all-in-one mini OMNI Station | "
            "Noise control around 55dB | Up to 189 min runtime on a 3,200mAh battery"
        ),
        "battery_capacity": "3200mAh",
        "runtime_minutes": 189,
        "release_year": 2026,
        "year_cite": "release_year=2026: Introduced by ECOVACS in 2026 (site (c) 2026; showcased at CES 2026, Las Vegas - PR Newswire).",
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{G}/{V}/deebot-mini-2-white", "DEEBOT mini 2 - ECOVACS Global (specs)"), SRC_CES26],
    },
    2474: {
        "name": "ECOVACS DEEBOT N20 PLUS",
        "url": f"{U}/{V}/deebot-n20-plus",
        "purpose": "Entry-level whole-home vacuuming and mopping with a self-emptying base, aimed at households that want mapping and scheduling without a flagship price.",
        "features": (
            "Tangle-free brush design for pet and long hair | "
            "Up to 300 min runtime | Smart mapping with multi-floor plans | "
            "Auto-empty station storing dust between emptyings | "
            "OZMO mopping with scheduling and zone control | "
            "App and voice control via the ECOVACS Home app"
        ),
        "runtime_minutes": 300,
        "release_year": 2024,
        "year_cite": "release_year=2024: DEEBOT N20 Series introduced alongside the N30 OMNI in 2024 (PR Newswire: 'ECOVACS Elevates Value Line with Premium Technology: Introducing the DEEBOT N30 OMNI and N20 Series').",
        "tags": TAGS_VACUUM,
        "sources": [
            _oem(f"{U}/{V}/deebot-n20-plus", "DEEBOT N20 PLUS - ECOVACS US (specs)"),
            {"url": "https://www.prnewswire.com/news-releases/ecovacs-elevates-value-line-with-premium-technology-introducing-the-deebot-n30-omni-and-n20-series-302253771.html",
             "type": "press", "title": "ECOVACS introduces the DEEBOT N30 OMNI and N20 Series (PR Newswire, 2024)"},
        ],
    },
    2475: {
        "name": "ECOVACS DEEBOT N30 PLUS",
        "url": f"{G}/{V}/deebot-n30-plus-white",
        "purpose": "Vacuums and mops household floors with a self-emptying base, positioned in the value tier of the DEEBOT range.",
        "features": (
            "10,000Pa suction power | ZeroTangle anti-tangle roller brush | "
            "OZMO mopping with auto mop-lifting for carpets | "
            "TrueMapping laser navigation with multi-floor mapping | "
            "Auto-empty station storing dust between emptyings | "
            "App and voice control via the ECOVACS Home app"
        ),
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{G}/{V}/deebot-n30-plus-white", "DEEBOT N30 PLUS WHITE - ECOVACS Global (specs)")],
    },
    2476: {
        "name": "ECOVACS DEEBOT T30C",
        "url": f"{U}/{V}/deebot-t30c",
        "purpose": "Handles daily floor cleaning for homes with pets, combining high suction and a dual anti-tangle system so hair does not wrap the brush or the mop.",
        "features": (
            "20,000Pa hyper suction with strong airflow | "
            "Dual ZeroTangle system for pet and long hair | "
            "TruEdge adaptive edge mopping | 20mm threshold crossing | "
            "Up to 180 min runtime | TrueMapping laser navigation | "
            "OMNI Station with hot-water mop washing, drying and auto-empty"
        ),
        "runtime_minutes": 180,
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{U}/{V}/deebot-t30c", "DEEBOT T30C - ECOVACS US (specs)")],
    },
    2477: {
        "name": "ECOVACS DEEBOT T80 OMNI",
        "url": f"{U}/{V}/deebot-t80-omni",
        "purpose": "Cleans hard floors and carpets across the home with a roller mop that rinses itself while it works, so dirty water is not spread back onto the floor.",
        "features": (
            "OZMO ROLLER mopping with high-speed scrubbing and continuous rinsing | "
            "18,000Pa tangle-free suction | Ultra-slim 98mm design fits under most furniture | "
            "9mm precision edge mopping: 100% external and 98% internal corners | "
            "20mm obstacle crossing with 10mm brush lift | Up to 4h 37min runtime | "
            "OMNI Station with 45C hot-air mop drying and maintenance-free washing tray"
        ),
        "runtime_minutes": 277,
        # "Ultra-Slim 98mm Design" stated on the OEM PDP -> robot height.
        "height_mm": 98.0,
        "release_year": 2025,
        "year_cite": "release_year=2025: Ecovacs announced the T80 OMNI (with the X9 PRO OMNI) for a mid-May 2025 release (Vacuum Wars).",
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{U}/{V}/deebot-t80-omni", "DEEBOT T80 OMNI - ECOVACS US (specs)"), SRC_VW_ROLLER],
    },
    2478: {
        "name": "ECOVACS DEEBOT T90 OMNI",
        "url": f"{U}/{V}/deebot-t90-omni",
        "purpose": "Automates everyday floor cleaning in the home - vacuuming and mopping hard floors and carpets, then self-emptying, washing and drying its own mop so the user never handles dirty water.",
        "features": (
            "BLAST system: 30,000Pa suction with 16 L/s airflow for 100% debris pickup | "
            "OZMO ROLLER instant self-cleaning roller mop | "
            "ZeroTangle anti-tangle system | TruEdge edge and corner cleaning | "
            "95mm robot height fits under low furniture | 15mm auto mop-lifting | "
            "Covers up to 400 m2 per run | "
            "Self-maintaining OMNI Station (auto-empty, hot-water mop wash and drying)"
        ),
        # "95mm Height of Robot" stated on the OEM PDP.
        "height_mm": 95.0,
        "release_year": 2026,
        "year_cite": "release_year=2026: DEEBOT T90 family unveiled at CES 2026 (Jan 6-9, 2026; PR Newswire + ECOVACS CES 2026 highlights). Family-level citation - the CES release names the T90 PRO OMNI; the T90 OMNI US listing and assets are dated 2026.",
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{U}/{V}/deebot-t90-omni", "DEEBOT T90 OMNI - ECOVACS US (specs, 30,000Pa)"), SRC_CES26],
    },
    2517: {
        "name": "DEEBOT X5 OMNI BLACK",
        "url": f"{G}/{V}/deebot-x5-omni-black",
        "purpose": "Cleans hard floors and carpets throughout the home in a single vacuum-and-mop pass, then empties, washes and dries itself at the OMNI Station.",
        "features": (
            "12,800Pa suction power | Ultra-thin and ultra-narrow body reaches under and "
            "between furniture | OZMO ROLLER self-washing mop with continuous rinsing | "
            "ZeroTangle 2.0 anti-tangle brush | TruEdge 2.0 adaptive edge mopping | "
            "15mm auto mop-lifting for carpets | 22mm threshold crossing | "
            "Up to 164 min runtime | OMNI Station with hot-water washing and hot-air drying"
        ),
        "runtime_minutes": 164,
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{G}/{V}/deebot-x5-omni-black", "DEEBOT X5 OMNI BLACK - ECOVACS Global (specs)")],
    },
    2518: {
        "name": "DEEBOT T30C BLACK",
        "url": f"{G}/{V}/deebot-t30c-black",
        "purpose": "Daily floor cleaning for homes with pets, pairing high suction with a dual anti-tangle system so hair does not wrap around the brush or mop.",
        "features": (
            "20,000Pa hyper suction with strong airflow | "
            "Dual ZeroTangle system for pet and long hair | "
            "TruEdge adaptive edge mopping | 20mm threshold crossing | "
            "Up to 180 min runtime | TrueMapping laser navigation | "
            "OMNI Station with hot-water mop washing, drying and auto-empty"
        ),
        "runtime_minutes": 180,
        "tags": TAGS_VACUUM,
        "sources": [_oem(f"{G}/{V}/deebot-t30c-black", "DEEBOT T30C BLACK - ECOVACS Global (specs)")],
    },
}

# Records whose exact SKU cannot be established, so NO text/spec/year is written
# (that would mean inventing a model). ECOVACS has no "DEEBOT X11 OMNI" /
# "DEEBOT X12 OMNI" SKU — the X11 and X12 lines are each OmniCyclone + PRO OMNI —
# so 2479/2480 are most likely duplicates of the already-enriched 4681 (X11
# OmniCyclone) / 4676 (X12 OmniCyclone). 1952 "GOAT A2000" has no OEM PDP: only
# the A2000 LiDAR PRO page exists, and taking its specs would be the sibling-page
# trap (SKILL rule 11 / `page_covers_model`).
#
# Their TAGS are still objectively wrong independent of the SKU question — a
# DEEBOT is a robot vacuum whichever X11 it is, and a GOAT is a consumer mower —
# so tags alone are corrected here. Everything else is left for a human.
AMBIGUOUS_IDS = {
    2479: "ECOVACS DEEBOT X11 OMNI",
    2480: "ECOVACS DEEBOT X12 OMNI",
    1952: "ECOVACS GOAT A2000",
}
TAGS_ONLY: dict[int, list[str]] = {
    2479: TAGS_VACUUM,
    2480: TAGS_VACUUM,
    1952: TAGS_MOWER,
}

_SPEC_PASSTHROUGH = (
    "battery_capacity", "runtime_minutes", "charging_time_minutes", "weight_kg",
    "width_mm", "length_mm", "height_mm", "voltage",
)


def build_payload(rid: int, data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": data["url"],
        "purpose": data["purpose"],
        "features": data["features"],
        "tags": data["tags"],
        "information_source_urls": [s["url"] for s in data["sources"]],
    }
    for key in _SPEC_PASSTHROUGH:
        if data.get(key) not in (None, ""):
            payload[key] = data[key]
    if data.get("release_year"):
        payload["release_year"] = data["release_year"]
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Fix thin/contaminated Ecovacs content (company 32)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=str, default="")
    args = ap.parse_args()

    ids = list(ROBOT_DATA)
    if args.ids.strip():
        want = {int(x) for x in args.ids.split(",") if x.strip().isdigit()}
        ids = [i for i in ids if i in want]

    client = ResearchApiClient()
    live = {r["id"]: r for r in client.list_robots_for_company(COMPANY_ID)}

    plan, ok, fail = [], 0, 0
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
            print(f"SKIP {rid} {cur.get('name')}: status={status} (pending_review only)", file=sys.stderr)
            continue

        data = ROBOT_DATA[rid]
        payload = build_payload(rid, data)
        row = {
            "id": rid, "name": data["name"], "feat_before": len(cur.get("features") or ""),
            "feat_after": len(data["features"]), "year": data.get("release_year"),
            "n_sources": len(data["sources"]), "n_tags": len(data["tags"]),
            "specs": [k for k in _SPEC_PASSTHROUGH if k in payload],
        }
        plan.append(row)
        print(f"{rid} {data['name']}: feat {row['feat_before']}->{row['feat_after']} "
              f"year={row['year']} tags={row['n_tags']} srcs={row['n_sources']} specs={row['specs']}")

        if args.apply:
            try:
                client._patch(f"robots/robots/{rid}/", payload)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                fail += 1
                print(f"  PATCH FAIL {rid}: {exc}", file=sys.stderr)

    # Tags-only rescue for the identity-ambiguous rows: the junk tags
    # (Drone/Humanoid/Industrial on vacuums, Professional/long/round on a mower)
    # are wrong regardless of which SKU the record turns out to be.
    for rid, nm in AMBIGUOUS_IDS.items():
        if args.ids.strip() and rid not in {int(x) for x in args.ids.split(",") if x.strip().isdigit()}:
            continue
        cur = live.get(rid)
        if cur is None or (cur.get("status") or "").lower() != "pending_review":
            continue
        print(f"AMBIGUOUS {rid} {nm}: SKU unresolved -> text/specs/year left for a human; "
              f"correcting junk tags only", file=sys.stderr)
        if args.apply:
            try:
                client._patch(f"robots/robots/{rid}/", {"tags": TAGS_ONLY[rid]})
                ok += 1
            except Exception as exc:  # noqa: BLE001
                fail += 1
                print(f"  TAGS PATCH FAIL {rid}: {exc}", file=sys.stderr)

    out = _RESEARCH_DIR / "staging" / "reports" / "ecovacs-thin-content-preview.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: {len(plan)} robots; ok={ok} fail={fail}")
    print(f"Preview: {out}")
    if not args.apply:
        print("Re-run with --apply")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
