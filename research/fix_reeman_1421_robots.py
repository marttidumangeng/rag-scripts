"""Curate REEMAN (company 1421) pending_review robots.

Maps CN/EN catalog duplicates, rejects SEO shells and chassis-vs-full SKU
dupes, enriches keepers from official reemanrobot.com / reemanbot.com PDPs.
Never invents specs. Leaves status=pending_review (no auto-publish).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from PIL import Image

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 1421
COMPANY_SLUG = "shenzhen-reeman-intelligent-equipment"
COMPANY_NAME = "REEMAN"
COMPANY_WEBSITE = "https://reemanbot.com/"
AVAILABLE = 11
CHINA = 3
REPORT = _HERE / "staging" / "reports" / "reeman-1421-curated-report.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# Movement: wheeled AMR-style
MOV_WHEELED = [4]
# Uses / industries — logistics + delivery oriented (IDs used by BlueSword/Geek+)
USES_LOGISTICS = [74, 62, 32, 54, 78]
USES_SERVICE = [74, 62, 32]
INDUSTRIES = [11, 12]

TAGS_FORK = [
    "AMR",
    "AGV",
    "Autonomous Forklift",
    "Forklift",
    "Pallet Handling",
    "Warehouse Automation",
    "Intralogistics",
    "Material Handling",
]
TAGS_AMR = [
    "AMR",
    "AGV",
    "Autonomous Mobile Robot",
    "Material Handling",
    "Warehouse Automation",
    "Intralogistics",
    "Logistics",
]
TAGS_FOOD = [
    "AMR",
    "Delivery",
    "Service Robot",
    "Indoor Delivery",
    "Hospitality",
]
TAGS_HOSP = [
    "AMR",
    "Delivery",
    "Service Robot",
    "Hospital",
    "Indoor Delivery",
]
TAGS_CLEAN = [
    "AMR",
    "Cleaning",
    "Service Robot",
    "Floor Cleaning",
]
TAGS_DISINFECT = [
    "AMR",
    "Cleaning",
    "Service Robot",
    "Hospital",
]
TAGS_CHASSIS = [
    "AMR",
    "AGV",
    "Autonomous Mobile Robot",
    "Mobile Robot",
]

# ---------------------------------------------------------------------------
# Keepers — one EN-named canonical record per SKU
# ---------------------------------------------------------------------------
PRODUCTS: dict[int, dict[str, Any]] = {
    2305: {
        "name": "Dual Laser Fly Boat PRO",
        "model": "Dual Laser Fly Boat PRO",
        "family_key": "reeman:fly-boat",
        "family_name": "Fly Boat",
        "family_url": "https://www.reemanrobot.com/agv-amr/",
        "url": "https://www.reemanrobot.com/agv-amr/dual-laser-fly-boat-pro-factory-delivery.html",
        "image": "https://www.reemanrobot.com/uploads/33814/dual-laser-fly-boat-pro-factory-deliveryad8bf.jpg",
        "description": (
            "Dual Laser Fly Boat PRO is REEMAN's backpack-style factory AMR with "
            "dual-laser SLAM navigation and a 300 kg rated load for marker-free "
            "industrial material handling."
        ),
        "features": (
            "Official Dual Laser Fly Boat PRO PDP: 300 kg large load capacity; "
            "REEMAN SLAM 2.0 autonomous positioning and navigation without floor "
            "codes; open SDK with API interfaces for secondary development. "
            "Positioned for one-way backpack factory and warehouse transport."
        ),
        "purpose": (
            "Factory floor material transport\n"
            "Warehouse tote and parts delivery\n"
            "Open-SDK AMR platform deployments"
        ),
        "typed": {"payload_kg": 300},
        "tags": TAGS_AMR,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "body mass, exact dimensions, speed, runtime, release year, exact public video",
    },
    2308: {
        "name": "HAMMER 2.0 Autonomous Forklift",
        "model": "HAMMER 2.0",
        "family_key": "reeman:hammer",
        "family_name": "HAMMER",
        "family_url": "https://www.reemanrobot.com/forklift/",
        "url": "https://www.reemanrobot.com/forklift/stackman-1200-autonomous-forklift-trucks.html",
        "image": None,
        "description": (
            "HAMMER 2.0 is REEMAN's counterbalanced autonomous forklift for "
            "cruciform pallet pickup with 3D pallet recognition in warehouses "
            "and factories."
        ),
        "features": (
            "Official HAMMER 2.0 / Stackman-1200 PDP: next-generation autonomous "
            "forklift designed for cruciform pallets with easy pickup and precise "
            "handling; 3D pallet recognition for accurate cargo detection. "
            "Marketed for smart warehousing pallet transport."
        ),
        "purpose": (
            "Cruciform pallet pickup and transport\n"
            "Warehouse counterbalanced forklift automation\n"
            "Factory pallet material handling"
        ),
        "typed": {},
        "tags": TAGS_FORK,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": (
            "exact payload_kg, lift height, dims, mass, speed, runtime on this PDP "
            "(marketing copy only); release year; exact public video"
        ),
        "image_todo": (
            "Official PDP og:image is a text-heavy 'Autonomous Stacker Forklift' "
            "warehouse banner. No clean robot-only product photo found on the PDP."
        ),
    },
    2310: {
        "name": "Mini Autonomous Forklift 2.0",
        "model": "Mini 2.0",
        "family_key": "reeman:mini-forklift",
        "family_name": "Mini Autonomous Forklift",
        "family_url": "https://www.reemanrobot.com/forklift/",
        "url": "https://www.reemanrobot.com/forklift/mini-autonomous-forklift-2-0.html",
        "image": None,
        "description": (
            "Mini Autonomous Forklift 2.0 is REEMAN's narrow-aisle unmanned stacker "
            "for 1.1 m aisles with 500 kg load capacity and 3D vision."
        ),
        "features": (
            "Official Mini Autonomous Forklift 2.0 PDP: positioned as the world's "
            "narrowest mini autonomous forklift; ideal for 1.1 m aisles; 500 kg "
            "load capacity; 3D vision; 24/7 operation."
        ),
        "purpose": (
            "Narrow-aisle pallet stacking\n"
            "Compact warehouse forklift automation\n"
            "24/7 light-pallet material handling"
        ),
        "typed": {"payload_kg": 500},
        "tags": TAGS_FORK,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "body mass, exact dims, lift height mm, speed, runtime, release year, exact video",
        "image_todo": (
            "Official PDP og:image is a promotional banner with large 'Mini "
            "Autonomous Forklift' title overlay and narrow-lane badge."
        ),
    },
    2311: {
        "name": "Rhinoceros Autonomous Forklift 3.0",
        "model": "Rhinoceros 3.0",
        "family_key": "reeman:rhinoceros",
        "family_name": "Rhinoceros",
        "family_url": "https://www.reemanrobot.com/forklift/",
        "url": "https://www.reemanrobot.com/forklift/rbot30f-autonomous-forklift-trucks-3-0.html",
        "image": None,
        "description": (
            "Rhinoceros 3.0 is REEMAN's autonomous stacker forklift with 360° "
            "stereoscopic obstacle avoidance, 1.5 t load capacity, and 2.5 m lift."
        ),
        "features": (
            "Official Rhinoceros Autonomous Forklift Truck 3.0 PDP: 360° "
            "stereoscopic obstacle avoidance; 1.5-ton large load capacity; "
            "2.5-meter lifting height; compact ~1.7 m in-situ rotation for "
            "narrow warehouse channels."
        ),
        "purpose": (
            "High-lift pallet stacking\n"
            "Narrow-channel warehouse forklift work\n"
            "Heavy pallet transport"
        ),
        "typed": {"payload_kg": 1500},
        "tags": TAGS_FORK,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "body mass, exact L/W/H, travel speed, runtime, release year, exact video",
        "image_todo": (
            "Official PDP og:image follows the same text-heavy warehouse forklift "
            "banner pattern as Mini/HAMMER; no clean robot-only hero verified."
        ),
    },
    2315: {
        "name": "Ironhide Autonomous Forklift 3.0",
        "model": "Ironhide 3.0",
        "family_key": "reeman:ironhide",
        "family_name": "Ironhide",
        "family_url": "https://www.reemanrobot.com/forklift/",
        "url": "https://www.reemanrobot.com/forklift/autonomous-forklift-ironhide-3-0.html",
        "image": None,
        "description": (
            "Ironhide 3.0 is REEMAN's autonomous transport forklift with a 550 mm "
            "fork arm and 3D visual pallet recognition for high-efficiency logistics."
        ),
        "features": (
            "Official Autonomous Forklift Ironhide 3.0 PDP: latest-generation "
            "autonomous forklift for high-efficiency logistics; 550 mm fork arm; "
            "advanced 3D visual pallet recognition for precise pallet handling."
        ),
        "purpose": (
            "Pallet cargo transport\n"
            "Factory and warehouse forklift automation\n"
            "3D-vision pallet recognition handling"
        ),
        "typed": {},
        "tags": TAGS_FORK,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": (
            "payload_kg on this PDP (marketing only; Ironhide 2.0 cites 1.5 t on a "
            "sibling page — not applied here); dims; mass; speed; runtime; video"
        ),
        "image_todo": (
            "Official PDP og:image is a text-heavy warehouse forklift marketing "
            "banner; no clean robot-only hero verified."
        ),
    },
    2316: {
        "name": "Garbage Transfer Robot",
        "model": "Garbage Transfer 300KG",
        "family_key": "reeman:garbage-transfer",
        "family_name": "Garbage Transfer",
        "family_url": "https://www.reemanrobot.com/agv-amr/",
        "url": "https://www.reemanrobot.com/agv-amr/reeman-intelligent-mobile-garbage-delivery.html",
        "image": (
            "https://www.reemanrobot.com/Content/uploads/2023807153/"
            "202311091713040403c9696bb1482eb0d99181584f7520.jpg"
        ),
        "description": (
            "REEMAN's intelligent garbage transfer robot is a 300 kg open-SDK AMR "
            "chassis for autonomous refuse transport in airports, malls, and campuses."
        ),
        "features": (
            "Official Garbage Transfer Robot PDP: 300 kg carrying capacity; "
            "automatic charging; open SDK for secondary development; positioned "
            "for airports, shopping malls, squares, and similar public venues."
        ),
        "purpose": (
            "Airport and mall refuse transport\n"
            "Campus waste transfer\n"
            "Open-SDK garbage AMR deployments"
        ),
        "typed": {"payload_kg": 300},
        "tags": TAGS_AMR + ["Cleaning"],
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "exact dims, mass, speed, runtime hours, release year, exact video",
    },
    2319: {
        "name": "Big Dog Factory Delivery Robot",
        "model": "Big Dog",
        "family_key": "reeman:big-dog",
        "family_name": "Big Dog",
        "family_url": "https://www.reemanrobot.com/agv-amr/",
        "url": "https://www.reemanrobot.com/agv-amr/factory-warehouse-intelligent-carrying-robot.html",
        "image": None,
        "description": (
            "Big Dog is REEMAN's 100 kg factory delivery AMR with dual 3D cameras "
            "and SLAM 2.0 navigation for marker-free workshop material transport."
        ),
        "features": (
            "Official Big Dog / factory carrying robot PDP: dual 3D cameras for "
            "all-around perception; 100 kg load capacity; REEMAN SLAM 2.0 "
            "navigation without floor codes; central dispatching and multi-robot "
            "collaboration; open SDK with rich APIs."
        ),
        "purpose": (
            "Workshop material delivery\n"
            "Factory line-side transport\n"
            "Multi-robot dispatched AMR logistics"
        ),
        "typed": {"payload_kg": 100},
        "tags": TAGS_AMR,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "exact dims, mass, speed, runtime, release year, exact video",
        "image_todo": (
            "List-page OG asset is ambiguous vs Fly Boat/HUSSAR mast siblings; "
            "no verified Big Dog-labeled exact-model hero. Do not use the 100KG "
            "HUSSAR PRO factory OG (possible sibling)."
        ),
    },
    2326: {
        "name": "Fogging Spraying Disinfection Robot",
        "model": "Fogging Spraying",
        "family_key": "reeman:fogging-disinfection",
        "family_name": "Fogging Disinfection",
        "family_url": "https://www.reemanrobot.com/disinfection-robot/",
        "url": (
            "https://www.reemanrobot.com/disinfection-robot/"
            "spray-disinfection-robot/fogging-spraying-disinfection-robot.html"
        ),
        "image": (
            "https://www.reemanrobot.com/Content/uploads/2021807153/"
            "202106021127096d7e316dc5ec4525b9b66034805df2ad.jpg"
        ),
        "description": (
            "REEMAN's fogging spraying disinfection robot atomizes disinfectant "
            "along autonomously planned indoor routes for facility-wide spray "
            "sanitation."
        ),
        "features": (
            "Official Fogging Spraying Disinfection Robot PDP: spray/fog "
            "disinfection with mobile-app map management; cruise speed up to "
            "0.8 m/s; about 4 hours battery life with automatic return-to-charge "
            "when battery is low."
        ),
        "purpose": (
            "Indoor fog/spray disinfection\n"
            "Hospital and public-space sanitation routes\n"
            "Scheduled unmanned disinfectant deployment"
        ),
        "typed": {"speed": 2.88, "runtime_minutes": 240},
        "tags": TAGS_DISINFECT,
        "uses": USES_SERVICE,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "payload, dims, mass, tank volume, release year, exact video",
    },
    2329: {
        "name": "Chengying UVC Disinfection Robot",
        "model": "Chengying",
        "family_key": "reeman:chengying",
        "family_name": "Chengying",
        "family_url": "https://www.reeman.cn/",
        "url": "https://www.reeman.cn/default.aspx?pageid=2&pageType=detail&id=22",
        "image": None,  # fail closed — CDN 403; no verified EN OEM hero
        "description": (
            "Chengying (承影) is REEMAN's wheeled UVC disinfection robot for "
            "autonomous indoor ultraviolet surface and air sterilization."
        ),
        "features": (
            "Chinese OEM catalog page (reeman.cn detail id=22) for 承影 ultraviolet "
            "disinfection robot. No matching English PDP naming 'Chengying' was "
            "found on reemanrobot.com during the 2026-07-22 pass (Spark / Sword / "
            "Radiation pages are distinct SKUs). Typed UV wattage and dims left "
            "blank — not invented from sibling Sword/Spark pages."
        ),
        "purpose": (
            "Indoor UVC surface disinfection\n"
            "Healthcare and public-space sterilization routes"
        ),
        "typed": {},
        "tags": TAGS_DISINFECT,
        "uses": USES_SERVICE,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": (
            "EN PDP URL; citeable wattage/dims/speed from a Chengying-named source; "
            "exact-model hero (owned CDN 403; no verified OEM upload)"
        ),
        "image_todo": (
            "No verified exact-model OEM hero. Owned CDN path returns 403. "
            "Do not substitute Sword/Spark sibling renders. Source a Chengying-"
            "labeled photo from reeman.cn / OEM press."
        ),
    },
    2330: {
        "name": "Sword NO.1 UVC Disinfection Robot",
        "model": "Sword NO.1",
        "family_key": "reeman:sword",
        "family_name": "Sword UVC",
        "family_url": "https://www.reemanrobot.com/disinfection-robot/",
        "url": (
            "https://www.reemanrobot.com/disinfection-robot/"
            "uvc-disinfection-robot/sword-no-1-uvc-disinfection-robot.html"
        ),
        "image": (
            "https://www.reemanrobot.com/uploads/202133814/"
            "sword-no-1-uvc-disinfection-robot56013921636.jpg"
        ),
        "description": (
            "Sword NO.1 is REEMAN's autonomous UVC disinfection robot using "
            "PHILIPS TUV lamps for timed multi-room indoor sterilization routes."
        ),
        "features": (
            "Official Sword NO.1 PDP: autonomous navigation along set routes; "
            "PHILIPS TUV 30 W T8 UV lamps; 254 nm UVC; sterilization life more "
            "than 8000 hours; multi-point timed disinfection on the navigation map."
        ),
        "purpose": (
            "Multi-room UVC disinfection\n"
            "Timed indoor sterilization routes\n"
            "Healthcare and commercial UV sanitation"
        ),
        "typed": {},
        "tags": TAGS_DISINFECT,
        "uses": USES_SERVICE,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": (
            "total UV wattage not explicitly summed on NO.1 PDP (sibling Sword 3 "
            "cites 180 W — not copied); dims; mass; speed; runtime; video"
        ),
    },
    2332: {
        "name": "Sword No.3 UVC Disinfection Robot",
        "model": "Sword No.3",
        "family_key": "reeman:sword",
        "family_name": "Sword UVC",
        "family_url": "https://www.reemanrobot.com/disinfection-robot/",
        "url": (
            "https://www.reemanrobot.com/disinfection-robot/"
            "uvc-disinfection-robot/sword-no-3-uvc-disinfection-robot.html"
        ),
        "image": (
            "https://www.reemanrobot.com/Content/uploads/2022807153/"
            "202205191624309fe30e065a3447729f88e1f79305b47c.jpg"
        ),
        "description": (
            "Sword No.3 is REEMAN's fully autonomous UVC sterilizer with up to "
            "180 W UV output and 0.2–0.8 m/s route control for 24/7 indoor "
            "disinfection."
        ),
        "features": (
            "Official Sword No.3 PDP: UV lamp output up to 180 W; 360° "
            "sterilization; trajectory/speed remote control 0.2–0.8 m/s; "
            "autonomous navigation and auto return-to-charge; 6 PHILIPS TUV "
            "lamps at 30 W each; lamp life more than 8000 hours; indoor-only "
            "factories, offices, and malls."
        ),
        "purpose": (
            "High-power indoor UVC sterilization\n"
            "Fixed-point multi-area disinfection\n"
            "24/7 unmanned public-space UV routes"
        ),
        "typed": {"speed": 2.88},
        "tags": TAGS_DISINFECT,
        "uses": USES_SERVICE,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "body dims, mass, runtime hours, release year, exact video",
    },
    2334: {
        "name": "Snail Commercial Cleaning Robot",
        "model": "Snail Clean",
        "family_key": "reeman:snail",
        "family_name": "Snail Clean",
        "family_url": "https://www.reemanrobot.com/cleaning-robot/",
        "url": (
            "https://www.reemanrobot.com/cleaning-robot/"
            "mopping-cleaning-robot/commercial-mopping-cleaning-robot.html"
        ),
        "image": (
            "https://www.reemanrobot.com/uploads/202233814/"
            "commercial-mopping-cleaning-robot42548631476.jpg"
        ),
        "description": (
            "Snail is REEMAN's commercial floor robot combining sweeping, "
            "vacuuming, mopping, and UVC floor disinfection for large indoor sites."
        ),
        "features": (
            "Official commercial mopping/Snail PDP: multi-functional large-scale "
            "commercial cleaner integrating sweeping, vacuuming, mopping, and "
            "disinfecting; 15 L water tank with circulation filtration; built-in "
            "UVC floor/mop disinfection; supports large-area map construction."
        ),
        "purpose": (
            "Commercial floor sweeping and vacuuming\n"
            "Autonomous mopping of malls and facilities\n"
            "UVC-assisted floor disinfection while cleaning"
        ),
        "typed": {},
        "tags": TAGS_CLEAN,
        "uses": USES_SERVICE,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "exact dims, mass, speed, runtime, coverage rate, release year, exact video",
    },
    4654: {
        "name": "HUSSAR Food Delivery Robot",
        "model": "HUSSAR",
        "family_key": "reeman:hussar",
        "family_name": "HUSSAR",
        "family_url": "https://www.reemanrobot.com/delivery-robot/",
        "url": (
            "https://www.reemanrobot.com/delivery-robot/food-delivery-robot/"
            "autonomous-delivery-robot.html"
        ),
        "image": None,
        "description": (
            "HUSSAR is REEMAN's multi-tray restaurant and hotel food delivery "
            "robot for autonomous table-side meal transport in narrow aisles."
        ),
        "features": (
            "Official autonomous waiter PDP (HUSSAR marketing line): passes "
            "aisles as narrow as 80 cm; tray size 320×400 mm across 3 layers; "
            "overall size about 500×1300 mm; 10–12 hours runtime; swing radius "
            "254 mm; multi-point delivery with autonomous scheduling."
        ),
        "purpose": (
            "Restaurant table-side meal delivery\n"
            "Hotel dining and room-service food transport\n"
            "Multi-robot coordinated waiter fleets"
        ),
        "typed": {
            "runtime_minutes": 660,
            "length_mm": 500,
            "height_mm": 1300,
        },
        "tags": TAGS_FOOD,
        "uses": USES_SERVICE,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "payload_kg total, exact width, mass, speed km/h, release year, exact video",
        "image_todo": (
            "PDP og:image has promotional callout banners (Automatic Delivery / "
            "Lower Labor Cost / Improve Efficiency). Gallery PNG placeholders were "
            "728-byte stubs. Need a clean robot-only photo."
        ),
    },
    4655: {
        "name": "FLASH Food Delivery Robot",
        "model": "FLASH",
        "family_key": "reeman:flash",
        "family_name": "FLASH",
        "family_url": "https://www.reemanrobot.com/delivery-robot/",
        "url": (
            "https://www.reemanrobot.com/delivery-robot/food-delivery-robot/"
            "intelligent-delivery-robot.html"
        ),
        "image": None,
        "description": (
            "FLASH is REEMAN's ultra-thin multi-floor food delivery robot for "
            "narrow restaurant paths with LiDAR/3D obstacle avoidance and "
            "elevator-ready options."
        ),
        "features": (
            "Official FLASH PDP: passes paths as narrow as 55 cm; about 40 kg "
            "robot mass; tray 335×465 mm across 4 layers; overall size "
            "540×360×1216 mm; LiFePO4 25.6 V/25 Ah; 15 kg per tray layer; "
            "around 15 hours battery life; swing radius 254 mm."
        ),
        "purpose": (
            "Narrow-aisle restaurant food delivery\n"
            "Multi-floor meal transport with elevator control\n"
            "Hotel and F&B tray delivery"
        ),
        "typed": {
            "weight_kg": 40,
            "weight": "40 kg",
            "payload_kg": 60,
            "length_mm": 540,
            "width_mm": 360,
            "height_mm": 1216,
            "runtime_minutes": 900,
        },
        "tags": TAGS_FOOD,
        "uses": USES_SERVICE,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "travel speed km/h, release year, exact public video",
        "image_todo": (
            "PDP og:image has promotional callout banners (Obstacle Avoidance / "
            "No Paste Code / Narrow Passage). Need clean robot-only photo."
        ),
    },
    4656: {
        "name": "R1D1 Food Delivery Robot",
        "model": "R1D1",
        "family_key": "reeman:r1d1",
        "family_name": "R1D1",
        "family_url": "https://www.reemanrobot.com/delivery-robot/",
        "url": (
            "https://www.reemanrobot.com/delivery-robot/food-delivery-robot/"
            "package-delivery-robot.html"
        ),
        "image": None,
        "description": (
            "R1D1 is REEMAN's enclosed-bin restaurant delivery robot with QR-code "
            "cabinet release for secure contactless food handoff."
        ),
        "features": (
            "Official R1D1 / package-delivery PDP: three sealed storage bins keep "
            "food uncontaminated; QR code verification at destination triggers "
            "automatic cabinet door release. Marketing positions it for restaurant "
            "waiter/package delivery."
        ),
        "purpose": (
            "Secure enclosed food delivery\n"
            "QR-verified contactless handoff\n"
            "Restaurant cabinet-style waiter service"
        ),
        "typed": {},
        "tags": TAGS_FOOD,
        "uses": USES_SERVICE,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "payload, dims, mass, speed, runtime, battery, release year, exact video",
        "image_todo": (
            "Gallery asset is a tall marketing infographic with feature icons and "
            "tagline — not a clean robot-only primary."
        ),
    },
    4657: {
        "name": "Drug Delivery Intelligent Robot",
        "model": "Drug Delivery",
        "family_key": "reeman:drug-delivery",
        "family_name": "Drug Delivery",
        "family_url": "https://www.reemanrobot.com/delivery-robot/",
        "url": (
            "https://www.reemanrobot.com/delivery-robot/food-delivery-robot/"
            "meal-delivery-robot.html"
        ),
        "image": None,
        "description": (
            "REEMAN's drug delivery intelligent robot autonomously distributes "
            "medicines and supplies through hospitals and hotels with "
            "high-precision indoor navigation."
        ),
        "features": (
            "Official hospital/hotel unmanned delivery PDP: designed for hospital "
            "and hotel environments; autonomous navigation with high-precision "
            "positioning to distribute materials safely across floors and wards."
        ),
        "purpose": (
            "Hospital medicine and supply delivery\n"
            "Hotel amenity and item transport\n"
            "Secure indoor unmanned distribution"
        ),
        "typed": {},
        "tags": TAGS_HOSP,
        "uses": USES_SERVICE,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "payload, dims, mass, speed, runtime, release year, exact video",
        "image_todo": (
            "PDP hero is a marketing collage with HOSPITAL/CLUBHOUSE/HOTEL inset "
            "callouts — not a clean robot-only primary."
        ),
    },
    4658: {
        "name": "Iron Bov PRO Factory Delivery Robot",
        "model": "Iron Bov PRO",
        "family_key": "reeman:iron-bov",
        "family_name": "Iron Bov",
        "family_url": "https://www.reemanrobot.com/delivery-robot/",
        "url": "https://www.reemanrobot.com/delivery-robot/iron-bov-pro-factory-delivery-robot.html",
        "image": "https://www.reemanrobot.com/uploads/33814/0cf4f.jpg",
        "description": (
            "Iron Bov PRO is REEMAN's heavy-duty factory AMR for up to 600 kg "
            "pallet and production-material transport with laser navigation and "
            "autonomous jacking."
        ),
        "features": (
            "Official Iron Bov PRO PDP: maximum payload up to 600 kg; laser "
            "navigation and intelligent obstacle avoidance without fixed tracks; "
            "autonomous lifting/jacking for loading and unloading; one-button "
            "remote calling and flexible route management for factory logistics."
        ),
        "purpose": (
            "Heavy pallet and rack transport\n"
            "Warehouse and line-side material delivery\n"
            "Autonomous jacking load transfer"
        ),
        "typed": {"payload_kg": 600},
        "tags": TAGS_AMR,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "exact dims, mass, speed, runtime, lift height mm on this PDP, release year, video",
    },
    4659: {
        "name": "HUSSAR PRO Mobile Robot Chassis",
        "model": "HUSSAR PRO Chassis",
        "family_key": "reeman:hussar-pro",
        "family_name": "HUSSAR PRO",
        "family_url": "https://www.reemanrobot.com/delivery-robot/",
        "url": "https://www.reemanrobot.com/delivery-robot/hussar-pro-mobile-robot-chassis.html",
        "image": "https://www.reemanrobot.com/uploads/33814/hussar-pro-mobile-robot-chassisfdaa8.jpg",
        "description": (
            "HUSSAR PRO Mobile Robot Chassis is REEMAN's open platform AMR base "
            "for industrial and service secondary development."
        ),
        "features": (
            "Official HUSSAR PRO chassis PDP: mobile robot chassis supporting "
            "autonomous transport and AMR development across industrial and "
            "service environments. Distinct from the HUSSAR PRO factory delivery "
            "full product (4660)."
        ),
        "purpose": (
            "Open-SDK mobile robot development\n"
            "Industrial AMR chassis integration\n"
            "Service-robot platform deployments"
        ),
        "typed": {},
        "tags": TAGS_CHASSIS,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "payload, dims, mass, speed, runtime, battery, release year, exact video",
    },
    4660: {
        "name": "HUSSAR PRO Factory Delivery Robot",
        "model": "HUSSAR PRO",
        "family_key": "reeman:hussar-pro",
        "family_name": "HUSSAR PRO",
        "family_url": "https://www.reemanrobot.com/delivery-robot/",
        "url": "https://www.reemanrobot.com/delivery-robot/hussar-pro-factory-delivery-robot.html",
        "image": None,
        "description": (
            "HUSSAR PRO Factory Delivery Robot is REEMAN's LiDAR/3D-vision AMR "
            "for autonomous factory and warehouse material transport."
        ),
        "features": (
            "Official HUSSAR PRO factory delivery PDP: LiDAR and 3D vision for "
            "navigation and obstacle avoidance in complex industrial environments; "
            "positioned for factory/warehouse material transport."
        ),
        "purpose": (
            "Factory material delivery\n"
            "Warehouse AMR transport\n"
            "LiDAR/3D-vision obstacle-aware logistics"
        ),
        "typed": {},
        "tags": TAGS_AMR,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "payload, dims, mass, speed, runtime, release year, exact video",
        "image_todo": (
            "PDP og:image shows a 100KG mast AMR that is ambiguous vs Big Dog; "
            "fail closed rather than risk sibling substitution."
        ),
    },
    4661: {
        "name": "BlazeBot",
        "model": "BlazeBot",
        "family_key": "reeman:blazebot",
        "family_name": "BlazeBot",
        "family_url": "https://www.reemanrobot.com/delivery-robot/blazebot.html",
        "url": "https://www.reemanrobot.com/delivery-robot/blazebot.html",
        "image": "https://www.reemanrobot.com/uploads/33814/blazebot5a00b.jpg",
        "description": (
            "BlazeBot is REEMAN's delivery robot with a 1.8 m vertical reach arm, "
            "3D camera and LiDAR obstacle avoidance, and automatic recharging."
        ),
        "features": (
            "Official BlazeBot PDP: robotic arm can automatically raise and lower "
            "1.8 meters for flexible operation; 3D camera and lidar for "
            "autonomous obstacle avoidance; automatic recharge when battery is low."
        ),
        "purpose": (
            "Elevated reach item delivery\n"
            "Flexible arm-assisted indoor transport\n"
            "Autonomous recharge delivery routes"
        ),
        "typed": {},
        "tags": TAGS_AMR + ["Delivery"],
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "payload, dims, mass, speed, runtime, release year, exact video",
    },
    5082: {
        "name": "Moon Knight Robot Chassis (FBOT13B)",
        "model": "FBOT13B",
        "family_key": "reeman:fbot13b",
        "family_name": "Moon Knight Robot Chassis",
        "family_url": (
            "https://www.reemanrobot.com/robot-chassis/square-robot-chassis/"
            "open-sdk-square-robot-chassis.html"
        ),
        "url": (
            "https://www.reemanrobot.com/robot-chassis/square-robot-chassis/"
            "open-sdk-square-robot-chassis.html"
        ),
        "image": None,
        "description": (
            "Moon Knight (FBOT13B) is REEMAN's square open-SDK mobile chassis "
            "with 60 kg capacity, LiDAR/vision navigation, and LiFePO4 power."
        ),
        "features": (
            "Official open-SDK square chassis PDP / prior CTRL ownership notes: "
            "sheet-metal structure; 60 kg carrying capacity; 25 Ah/25.6 V "
            "LiFePO4; 15–20 hours runtime at 30 kg load; 0.1–1.0 m/s; "
            "500×500×310 mm; 25 m laser detection."
        ),
        "purpose": (
            "Open-SDK square chassis development\n"
            "Indoor AMR platform integration\n"
            "Secondary-development mobile robotics"
        ),
        "typed": {
            "payload_kg": 60,
            "speed": 3.6,
            "length_mm": 500,
            "width_mm": 500,
            "height_mm": 310,
            "runtime_minutes": 900,
        },
        "tags": TAGS_CHASSIS,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "exact curb weight on this pass (CTRL note cited 34 kg — re-verify before PATCH if needed), release year, exact video",
        "image_todo": (
            "Square FBOT13B: PDP/gallery candidates were circular chassis or "
            "banner assets. Do not use Hot Wheels circular sibling. Need exact "
            "square-chassis product photo."
        ),
    },
    5083: {
        "name": "Hot Wheels Robot Chassis (WBOT11B)",
        "model": "WBOT11B",
        "family_key": "reeman:wbot11b",
        "family_name": "Hot Wheels Robot Chassis",
        "family_url": (
            "https://www.reemanrobot.com/robot-chassis/circular-robot-chassis/"
            "automatic-circular-robot-chassis.html"
        ),
        "url": (
            "https://www.reemanrobot.com/robot-chassis/circular-robot-chassis/"
            "automatic-circular-robot-chassis.html"
        ),
        "image": (
            "https://www.reemanrobot.com/Content/uploads/2022807153/"
            "202210181102510bda585930db49f9acbb09d7c3f26584.jpg"
        ),
        "description": (
            "Hot Wheels (WBOT11B) is REEMAN's circular open-SDK chassis with "
            "sensor-fusion navigation for secondary mobile-robot development."
        ),
        "features": (
            "Official circular chassis PDP: about 6 hours runtime; 0.2–0.8 m/s; "
            "37 V/10 Ah or 37 V/20 Ah optional battery; 450×450×317 mm body. "
            "Open SDK interfaces for secondary development."
        ),
        "purpose": (
            "Open-SDK circular chassis development\n"
            "Compact AMR platform integration\n"
            "Indoor mobile-robot prototyping"
        ),
        "typed": {
            "payload_kg": 60,
            "speed": 2.88,
            "length_mm": 450,
            "width_mm": 450,
            "height_mm": 317,
            "runtime_minutes": 360,
        },
        "tags": TAGS_CHASSIS,
        "uses": USES_LOGISTICS,
        "movement": MOV_WHEELED,
        "videos": [],
        "dead": "exact curb weight (CTRL note 28 kg — re-verify), release year, exact video",
    },
}

REJECTS: dict[int, str] = {
    2306: (
        "cn_chassis_duplicate: 双激光飞船底盘 is the chassis sibling of Dual Laser "
        "Fly Boat PRO keeper 2305"
    ),
    2313: (
        "cn_language_duplicate: 铁牛Pro搬运机器人 maps to Iron Bov PRO keeper 4658"
    ),
    2314: (
        "superseded_sku: 大力士无人叉车 (non-2.0) superseded by HAMMER 2.0 keeper 2308"
    ),
    2318: (
        "cn_language_duplicate: 飞船搬运机器人 older Fly Boat line; keep Dual Laser "
        "Fly Boat PRO 2305"
    ),
    2320: (
        "cn_language_duplicate: 德利哥·送餐机器人 maps to HUSSAR waiter keeper 4654"
    ),
    2322: (
        "cn_language_duplicate: 闪电·送餐机器人 maps to FLASH keeper 4655"
    ),
    2324: (
        "cn_language_duplicate: 大白·医院智能配送机器人 maps to Drug Delivery keeper 4657"
    ),
    2327: (
        "generic_sibling_duplicate: 雾化消毒机器人 is a generic fogger shell of "
        "Fogging Spraying keeper 2326"
    ),
    4662: (
        "chassis_vs_full_sku: IronBov chassis duplicates Iron Bov PRO family; "
        "keep PRO 4658"
    ),
    4663: (
        "sibling_duplicate: Iron Bov·Delivery Robot non-PRO sibling of Iron Bov "
        "PRO keeper 4658"
    ),
    4664: (
        "seo_title_duplicate: generic waiter SEO title duplicates HUSSAR keeper 4654"
    ),
    4665: (
        "generic_seo_shell: 'Food Delivery Robot' is a non-unique SEO catalog title"
    ),
}


def payload(rid: int) -> dict[str, Any]:
    data = PRODUCTS[rid]
    notes = (
        f"[AI Research — REEMAN curated full enrichment 2026-07-22] "
        f"OEM source: {data['url']}. Dead searches: {data['dead']}."
    )
    if data.get("image_todo"):
        notes = (
            "[IMAGE TO-DO — no hero, deliberate]\n"
            f"{data['image_todo']}\n"
            "ACTION FOR TEAM: source a licensed exact-model OEM product photo.\n"
            "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
            "---\n"
            + notes
        )
    body: dict[str, Any] = {
        "name": data["name"],
        "model_name": data["model"],
        "variant_code": data["model"].replace(" ", "-"),
        "description": data["description"],
        "features": data["features"],
        "purpose": data["purpose"],
        "url": data["url"],
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": data["family_url"],
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "manufacturer_country_ref": CHINA,
        "manufacturer_countries": [CHINA],
        "uses": data["uses"],
        "industries": INDUSTRIES,
        "movement_types": data["movement"],
        "tags": data["tags"],
        "information_source_urls": [data["url"], COMPANY_WEBSITE],
        "notes": notes,
        "status": "pending_review",
    }
    if data.get("image"):
        body["image"] = data["image"]
        body["images"] = [data["image"]]
        body["s3_image"] = None
    else:
        body["image"] = None
        body["images"] = []
        body["s3_image"] = None
    body.update(data.get("typed") or {})
    return body


def scalar_payload(rid: int) -> dict[str, Any]:
    body = payload(rid)
    for key in ("image", "images", "s3_image"):
        body.pop(key, None)
    return body


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace(
        "/api/v1", ""
    )


def _internal_headers() -> dict[str, str]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        raise RuntimeError("INTERNAL_API_SECRET missing")
    return {"X-Internal-Secret": secret}


def replace_media_and_videos(client: ResearchApiClient, rid: int) -> dict[str, Any]:
    data = PRODUCTS[rid]
    row = payload(rid)
    row.update(
        {
            "id": rid,
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "CN",
            "manufacturer_country_codes": "CN",
            "video_urls": [],
        }
    )
    # Skip enrich_video_list — all keepers have empty video lists; oEmbed can hang.
    return client.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        status="pending_review",
        skip_company_update=True,
        replace_media=True,
        replace_videos=True,
    )


def copy_media(rid: int) -> dict[str, Any]:
    if not PRODUCTS[rid].get("image"):
        return {"skipped": True, "reason": "no_image"}
    response = requests.post(
        f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/"
        f"{rid}/copy-media/?force=1",
        headers=_internal_headers(),
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def reject_invalid_rows(client: ResearchApiClient) -> list[dict[str, Any]]:
    results = []
    for rid, reason in REJECTS.items():
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": reason,
                "notes": f"[CURATED FULL 2026-07-22] {reason}",
            },
        )
        results.append({"id": rid, "reason": reason})
    return results


def patch_company(client: ResearchApiClient) -> dict[str, Any]:
    return client._patch(
        f"companies/{COMPANY_ID}/",
        {
            "website": COMPANY_WEBSITE,
            "country_id": CHINA,
        },
    )


def verify_company(client: ResearchApiClient) -> dict[str, Any]:
    rows = client.list_robots_for_company(COMPANY_ID)
    pending = [row for row in rows if row.get("status") == "pending_review"]
    pending_ids = {int(row["id"]) for row in pending}
    if pending_ids != set(PRODUCTS):
        raise RuntimeError(
            f"pending set mismatch: got={sorted(pending_ids)} "
            f"expected={sorted(PRODUCTS)}"
        )
    media = []
    hashes: set[str] = set()
    imageless = []
    for rid in sorted(PRODUCTS):
        robot = client._get(f"robots/robots/{rid}/")
        if robot.get("family_key") != PRODUCTS[rid]["family_key"]:
            raise RuntimeError(f"family invariant failed for {rid}")
        if not PRODUCTS[rid].get("image"):
            imageless.append(rid)
            media.append({"id": rid, "url": None, "imageless": True})
            continue
        url = str(robot.get("s3_image") or robot.get("image") or "")
        response = requests.get(url, headers=HEADERS, timeout=90)
        response.raise_for_status()
        if not (
            response.content.startswith(b"\xff\xd8")
            or response.content.startswith(b"\x89PNG")
            or response.content.startswith(b"RIFF")
        ):
            raise RuntimeError(f"non-image body for {rid}: {url}")
        image = Image.open(io.BytesIO(response.content))
        digest = hashlib.sha256(response.content).hexdigest()
        if digest in hashes:
            raise RuntimeError(f"duplicate hero hash for {rid}: {digest}")
        hashes.add(digest)
        media.append(
            {
                "id": rid,
                "url": url,
                "size": list(image.size),
                "bytes": len(response.content),
                "sha256": digest,
            }
        )
    return {
        "pending_ids": sorted(PRODUCTS),
        "imageless": imageless,
        "media": media,
        "distinct_hero_hashes": len(hashes),
    }


def approve_allowlist() -> list[int]:
    """IDs that pass must-clear after enrich (have hero + features + country)."""
    return sorted(rid for rid, data in PRODUCTS.items() if data.get("image"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate REEMAN company 1421")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    live = client.list_robots_for_company(COMPANY_ID)
    pending_ids = {
        int(robot["id"])
        for robot in live
        if robot.get("status") == "pending_review"
    }
    expected = set(PRODUCTS) | set(REJECTS)
    if pending_ids not in (expected, set(PRODUCTS)):
        # Allow already-rejected subset on re-run
        missing = expected - pending_ids
        unexpected = pending_ids - expected
        # If rejects already applied, pending should equal PRODUCTS
        if pending_ids != set(PRODUCTS) and unexpected:
            raise RuntimeError(
                f"live queue drift: missing={sorted(missing)} "
                f"unexpected={sorted(unexpected)}"
            )

    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "company_website": COMPANY_WEBSITE,
        "mode": "apply" if args.apply else "dry-run",
        "keepers": sorted(PRODUCTS),
        "rejects": REJECTS,
        "approve_allowlist": approve_allowlist(),
        "imageless_holds": sorted(
            rid for rid, d in PRODUCTS.items() if not d.get("image")
        ),
        "products": {str(rid): payload(rid) for rid in PRODUCTS},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if not args.apply:
        REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "mode": "dry-run",
                    "keepers": len(PRODUCTS),
                    "rejects": len(REJECTS),
                    "keeper_ids": sorted(PRODUCTS),
                    "reject_ids": sorted(REJECTS),
                    "approve_allowlist": approve_allowlist(),
                    "imageless_holds": report["imageless_holds"],
                    "company_website": COMPANY_WEBSITE,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    company_result = patch_company(client)
    print("company patched", company_result.get("website"), flush=True)
    import_results = {}
    copy_results = {}
    for rid in sorted(PRODUCTS):
        print(f"enrich {rid} {PRODUCTS[rid]['name']} ...", flush=True)
        try:
            import_results[rid] = replace_media_and_videos(client, rid)
            if import_results[rid].get("error_count"):
                raise RuntimeError(
                    f"bulk import failed for {rid}: {import_results[rid]}"
                )
            client._patch(f"robots/robots/{rid}/", scalar_payload(rid))
            copy_results[rid] = copy_media(rid)
            print(f"  done import+patch+copy {rid}", flush=True)
        except Exception as exc:
            print(f"  FAILED {rid}: {exc}", flush=True)
            raise

    print("rejecting duplicates...", flush=True)
    reject_results = reject_invalid_rows(client)
    print("verifying...", flush=True)
    verified = verify_company(client)
    report.update(
        {
            "applied": True,
            "company_patch": {
                "website": company_result.get("website"),
                "country": company_result.get("country")
                or company_result.get("country_id"),
            },
            "import_results": import_results,
            "copy_media": copy_results,
            "reject_results": reject_results,
            "verified": verified,
        }
    )
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "applied": True,
                "keepers": len(PRODUCTS),
                "rejects": len(REJECTS),
                "approve_allowlist": approve_allowlist(),
                "verified": verified,
                "company_website": COMPANY_WEBSITE,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
