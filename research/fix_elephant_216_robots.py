"""Fix Elephant Robotics (company 216) content-queue enrichment.

OEM: https://www.elephantrobotics.com (+ shop.elephantrobotics.com / docs).

Issues addressed:
- 12 robots (2482–2493) shared identical CDN hero bytes — replace with distinct OEM/shop heroes
- All 16 had payload_kg=3.0 (C3 copy) — restore OEM payloads (many are grams-scale arms / AGV kg)
- Broken doubled URLs on 449/450/451/452 — remap to clean EN PDPs
- Empty family_key on all — set elephant-robotics:{series}
- 450 MarsCat Robotic Pet = duplicate of 2483 MarsCat — reject
- 2482 URL is catbot-en but product is Elephant Robotics C3 cobot (not a pet)
- purpose / availability / taxonomy / videos / TagCatalog tags
"""
from __future__ import annotations

import argparse
import hashlib
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

COMPANY_ID = 216
COMPANY_SLUG = "elephant-robotics"
COMPANY_NAME = "Elephant Robotics"
CN = "CN"
OEM = "https://www.elephantrobotics.com"
STATIC = "https://static.elephantrobotics.com/wp-content/uploads"
SHOP = "https://shop.elephantrobotics.com/cdn/shop"
MEDIA_DIR = _RESEARCH_DIR / "staging" / "elephant_216_media"
REPORT = _RESEARCH_DIR / "staging" / "reports" / "overnight-216-elephant.md"
PREVIEW = _RESEARCH_DIR / "staging" / "reports" / "elephant-216-fix-preview.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# Distinct heroes (md5-verified unique across company before apply).
IMG = {
    2493: f"{SHOP}/files/myArm_300_Pi.png?v=1734342470",  # 8bea20678c45
    2490: f"{SHOP}/files/myAGVJetsonNano2023.png?v=1698978108",  # 42b8b3bb2a6c
    2489: f"{SHOP}/files/myAGV_Pi.png?v=1734342188",  # a0ec1779a84d
    2488: f"{SHOP}/files/Mercury-X1-new.jpg?v=1739786966",  # 49c48b3c6c8a
    2487: f"{SHOP}/files/1_aa9f84cf-d7ab-4624-b518-0317abfb7524.png?v=1739786966",  # f00d167b4f68
    2486: "https://cdn.shopify.com/s/files/1/0055/1826/2358/files/3_71d59ce9-a911-412a-a51f-5d985bb066aa.png?v=1703149789",  # 16cf920fb394
    2485: f"{STATIC}/2022/08/mechArm-%E4%B9%B0.png",  # 42744b2b3e7e
    2484: f"{SHOP}/files/mechArm_Pi.png?v=1734341873",  # ed89acf94248
    2483: f"{STATIC}/2022/08/MarsCat.png",  # 39813f3f0fa2
    2482: f"{STATIC}/2022/11/C-Series.png",  # 9bfd519ca720
    452: f"{SHOP}/products/ultraArmP3401.jpg?v=1672366363",  # f4d90932ceb8
    451: f"{STATIC}/2022/08/%E5%8F%8C%E8%87%82%E5%8D%8F%E5%90%8C%E6%9C%BA%E5%99%A8%E4%BA%BA.png",  # 64a6c5363b6e
    449: f"{STATIC}/2022/08/metacat.png",  # 3d4a554523a1
}

# Local crops (text stripped) — uploaded during --apply then used as image URL.
LOCAL_HERO = {
    2492: MEDIA_DIR / "pro_hero_final.png",
    2491: MEDIA_DIR / "plus_hero_final.png",
}

URL = {
    2493: f"{OEM}/en/myarm-300-pi-2023-en/",
    2492: f"{OEM}/en/myagv-pro/",
    2491: f"{OEM}/en/myagv-plus/",
    2490: f"{OEM}/en/myagv-2023-jn-en/",
    2489: f"{OEM}/en/myagv-new-en/",
    2488: f"{OEM}/en/mercury-x1-en/",
    2487: f"{OEM}/en/mercury-b1-en/",
    2486: f"{OEM}/en/mercury-a1-en/",
    2485: f"{OEM}/en/mecharm-m5-cn/",
    2484: f"{OEM}/en/mecharm-cn/",
    2483: f"{OEM}/en/mars-en/",
    2482: f"{OEM}/en/catbot-en/",
    452: f"{OEM}/en/ultraarm-p340-en/",
    451: f"{OEM}/en/mybuddy-280-pi-en/",
    449: f"{OEM}/en/metacat-2023-en/",
}

FAMILY_URL = {
    "myarm": f"{OEM}/en/myarm-300-pi-2023-en/",
    "myagv": f"{OEM}/en/myagv-new-en/",
    "mercury": f"{OEM}/en/mercury-humanoid-robot/",
    "mecharm": f"{OEM}/en/mecharm-cn/",
    "marscat": f"{OEM}/en/mars-en/",
    "c3": f"{OEM}/en/catbot-en/",
    "ultraarm": f"{OEM}/en/ultraarm-p340-en/",
    "mybuddy": f"{OEM}/en/mybuddy-280-pi-en/",
    "metacat": f"{OEM}/en/metacat-2023-en/",
}

YT = {
    2493: ["https://www.youtube.com/watch?v=EXDZLiHUs_E"],
    2492: ["https://www.youtube.com/watch?v=SUPmAri4Bjk"],
    2491: ["https://www.youtube.com/watch?v=uF0RcF7J3ME", "https://www.youtube.com/watch?v=oSjKckPussQ"],
    2490: ["https://www.youtube.com/watch?v=RLksUxbczBc"],
    2489: ["https://www.youtube.com/watch?v=hn3giIWblhw"],
    2488: ["https://www.youtube.com/watch?v=w1THU78Nt6A", "https://www.youtube.com/watch?v=sF_j4nBpi6s"],
    2487: ["https://www.youtube.com/watch?v=a4aOFrozVqo", "https://www.youtube.com/watch?v=Xb-Lbf9AM3g"],
    2486: ["https://www.youtube.com/watch?v=igxPLJGXGio"],
    2485: ["https://www.youtube.com/watch?v=j4w0RLMH5kw"],
    2484: ["https://www.youtube.com/watch?v=YBvp11NlbXY"],
    2483: ["https://www.youtube.com/watch?v=nwT1z8oW7os"],
    2482: [],  # no exact-token C3 OEM video found this pass
    452: ["https://www.youtube.com/watch?v=isfDa6vi3vc"],
    451: ["https://www.youtube.com/watch?v=OzbkmGphgH8"],
    449: ["https://www.youtube.com/watch?v=m3QSYhsxxmk"],
}

TAGS_ARM = "6-Axis|Collaborative Robot|Cobot|Education|Research|Pick-and-Place"
TAGS_ARM7 = "7-axis|Collaborative Robot|Cobot|Education|Research|Pick-and-Place"
TAGS_AGV = "AGV|AMR|Autonomous Mobile Robot|Wheeled|Education|Research|Material Handling"
TAGS_MERCURY_A = "7-axis|Collaborative Robot|Cobot|Education|Research|Humanoid"
TAGS_MERCURY_B = "Humanoid|Collaborative Robot|Education|Research|Mobile Manipulator"
TAGS_MERCURY_X = "Humanoid|Wheeled|Mobile Manipulator|Education|Research"
TAGS_PET_MARS = "Quadruped|Companion|Entertainment|Research"
TAGS_PET_META = "Companion|Entertainment"
TAGS_BUDDY = "Collaborative Robot|Cobot|Education|Research|Pick-and-Place"
TAGS_C3 = "6-Axis|Collaborative Robot|Cobot|Industrial|Manufacturing|Pick-and-Place"
TAGS_ULTRA = "Education|Research|Pick-and-Place|Collaborative Robot"

REJECTS: dict[int, str] = {
    450: (
        "Duplicate of robot 2483 (MarsCat). Same OEM MarsCat robotic-pet SKU; "
        "this record had a broken doubled URL "
        "(elephantrobotics.com/https://…/marscat/) and thin features. "
        "Keep 2483 as the canonical OEM-enriched MarsCat."
    ),
}

_AVAIL_IDS = {"announced": 10, "available": 11, "released": 3, "discontinued": 4, "pre_order": 12}


def _family(series: str, name: str, url: str) -> dict[str, Any]:
    return {
        "family_key": f"{COMPANY_SLUG}:{series}",
        "family_name": name,
        "family_url": FAMILY_URL[series],
        "product_url_scope": "exact_variant",
        "url": url,
    }


def arm_fix(
    *,
    rid: int,
    name: str,
    model: str,
    series: str,
    family_name: str,
    description: str,
    purpose: str,
    features: str,
    payload_kg: float | None,
    reach_mm: float | None,
    weight_kg: float | None,
    repeatability_mm: float | None,
    dof: int | None,
    tags: str,
    availability: str = "available",
    movement: str = "stationary",
    industry: str = "education|research",
    uses: str = "research|education|pick-and-place",
    category: str = "research-robots",
    sub: str = "learning",
    extra_typed: dict[str, Any] | None = None,
    source_extra: list[str] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": name,
        "model_name": model,
        "variant_code": model,
        "variant_label": model,
        **_family(series, family_name, URL[rid]),
        "image": IMG.get(rid),
        "description": description,
        "purpose": purpose,
        "features": features,
        "availability_status_key": availability,
        "movement_type_keys": movement,
        "industry_keys": industry,
        "use_keys": uses,
        "category_slugs": category,
        "sub_category_slug": sub,
        "tags": tags,
        "manufacturer_country_code": CN,
        "videos": YT.get(rid) or [],
        "information_source_urls": [URL[rid], *(source_extra or [])],
        "notes_force": (
            f"[AI Research] OEM specs from {URL[rid]}. "
            f"Hero replaced shared company CDN collision hash with distinct OEM/shop asset. "
            f"Corrected fabricated payload_kg=3.0 copy."
        ),
        "source_note": f"{URL[rid]} — Elephant Robotics OEM",
    }
    if payload_kg is not None:
        row["payload_kg"] = payload_kg
    if reach_mm is not None:
        row["reach_mm"] = reach_mm
    if weight_kg is not None:
        row["weight_kg"] = weight_kg
        row["weight"] = f"{weight_kg:g} kg"
    if repeatability_mm is not None:
        row["repeatability_mm"] = repeatability_mm
    if dof is not None:
        row["dof"] = dof
    if extra_typed:
        row.update(extra_typed)
    if rid in LOCAL_HERO:
        row["local_image"] = str(LOCAL_HERO[rid])
        row["image"] = None  # filled after upload
    return row


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    2493: arm_fix(
        rid=2493,
        name="myArm 300 Pi 2023",
        model="myArm 300 Pi 2023",
        series="myarm",
        family_name="myArm",
        description=(
            "myArm 300 Pi 2023 is Elephant Robotics' portable 7-axis desktop arm powered by "
            "Raspberry Pi 4B and a customized Ubuntu Mate OS for robotics education, control "
            "logic teaching, and ROS simulation."
        ),
        purpose=(
            "7-axis robotics education\n"
            "ROS simulation and control teaching\n"
            "Desktop pick-and-place demos\n"
            "Research prototyping with myCobot accessories"
        ),
        features=(
            "Official myArm 300 Pi specs: 7 DOF, 300 mm working radius, 200 g maximum load, "
            "1.5 kg net weight, ±0.5 mm repeatability, DC 12V-5A adapter, Raspberry Pi 4B "
            "master with ROS1/ROS2, myBlockly, drag-and-teach, and GPIO. Cited from OEM PDP "
            "and docs.elephantrobotics.com myArm-PI product table / brochure."
        ),
        payload_kg=0.2,
        reach_mm=300,
        weight_kg=1.5,
        repeatability_mm=0.5,
        dof=7,
        tags=TAGS_ARM7,
        source_extra=[
            "https://docs.elephantrobotics.com/docs/myarm-pi-300-en/2-serialproduct/2.12-myArm/2.12-myArm.html",
            "https://static.elephantrobotics.com/wp-content/uploads/2023/11/myArm300Pi-Brochure-V20230825.pdf",
        ],
    ),
    2492: arm_fix(
        rid=2492,
        name="myAGV Pro",
        model="myAGV Pro",
        series="myagv",
        family_name="myAGV",
        description=(
            "myAGV Pro is Elephant Robotics' industrial-leaning omnidirectional mobile base "
            "with a 50 kg payload, 1.5 m/s full-load speed, and ROS2 Humble support for "
            "compound mobile-manipulator deployments."
        ),
        purpose=(
            "Indoor material transport\n"
            "Compound mobile manipulation with mounted arms\n"
            "2D/3D SLAM navigation research\n"
            "ROS2 Humble education and demos"
        ),
        features=(
            "OEM myAGV Pro table: 50 kg maximum payload, 40 kg weight, 530×360×245 mm, "
            "omnidirectional steering, 1.5 m/s full-load speed, 0 m turning radius, 10° "
            "incline, 24 V 20 Ah LiFePO4 battery, 5–6 h no-load runtime, IP22, ROS2 Humble "
            "on Ubuntu 22.04, modular Mecanum or omni wheel options."
        ),
        payload_kg=50.0,
        reach_mm=None,
        weight_kg=40.0,
        repeatability_mm=None,
        dof=None,
        tags=TAGS_AGV,
        movement="wheeled",
        industry="education|research|logistics|manufacturing",
        uses="material-handling|logistics|research|mapping",
        category="industrial-robots",
        sub="logistics-warehouse",
        extra_typed={
            "speed": 5.4,  # 1.5 m/s → km/h
            "length_mm": 530,
            "width_mm": 360,
            "height_mm": 245,
            "battery_wh": 480,  # 24 V × 20 Ah
        },
    ),
    2491: arm_fix(
        rid=2491,
        name="myAGV Plus",
        model="myAGV Plus",
        series="myagv",
        family_name="myAGV",
        description=(
            "myAGV Plus is Elephant Robotics' compact AI mobile robot for education and "
            "research, with up to 8 kg payload, FOC brushless drive, and Jetson Orin Nano "
            "Super compute for LiDAR–vision navigation."
        ),
        purpose=(
            "AI education and robotics development\n"
            "Indoor autonomous navigation demos\n"
            "Light material transport and route delivery\n"
            "ROS2 / Python mobile-robot coursework"
        ),
        features=(
            "OEM myAGV Plus specs: 4 DOF (mobile), net weight <5 kg, max payload 8 kg, "
            "max speed 1.6 m/s, Jetson Orin Nano Super 8 GB, ESP32-PICO-D4 MCU, 360° LiDAR "
            "(0.12–8 m), FOC brushless planetary motors, ROS2 / RViz2 / Gazebo, CAN + USB."
        ),
        payload_kg=8.0,
        reach_mm=None,
        weight_kg=None,  # OEM lists "<5KG" — not an exact citeable float
        repeatability_mm=None,
        dof=4,
        tags=TAGS_AGV,
        movement="wheeled",
        industry="education|research|logistics",
        uses="material-handling|research|mapping|education",
        category="industrial-robots",
        sub="logistics-warehouse",
        extra_typed={"speed": 5.76},  # 1.6 m/s → km/h
    ),
    2490: arm_fix(
        rid=2490,
        name="myAGV Jetson Nano 2023",
        model="myAGV Jetson Nano 2023",
        series="myagv",
        family_name="myAGV",
        description=(
            "myAGV Jetson Nano 2023 is Elephant Robotics' Mecanum AGV powered by NVIDIA "
            "Jetson Nano B01 4 GB for 2D/3D mapping, ROS simulation, and compound "
            "arm-on-AGV education kits."
        ),
        purpose=(
            "Jetson Nano robotics education\n"
            "2D/3D SLAM mapping and navigation\n"
            "Compound mobile grasping with desktop arms\n"
            "ROS simulation labs"
        ),
        features=(
            "OEM myAGV JN 2023 page: 5000 g (5 kg) payload, 360° LiDAR, Jetson Nano B01 4 GB, "
            "custom Ubuntu Mate 20.04, 2D/3D mapping and navigation, graphical programming, "
            "gamepad/keyboard control, ROS simulation. Mecanum omnidirectional drive."
        ),
        payload_kg=5.0,
        reach_mm=None,
        weight_kg=None,
        repeatability_mm=None,
        dof=None,
        tags=TAGS_AGV,
        movement="wheeled",
        industry="education|research",
        uses="research|mapping|material-handling|education",
        category="industrial-robots",
        sub="learning",
    ),
    2489: arm_fix(
        rid=2489,
        name="myAGV",
        model="myAGV",
        series="myagv",
        family_name="myAGV",
        description=(
            "myAGV is Elephant Robotics' entry Mecanum mobile base for compound robots, "
            "with 2000 g payload, 360° LiDAR SLAM, and mounts for myCobot / mechArm / "
            "myPalletizer arms."
        ),
        purpose=(
            "Compound mobile robot education\n"
            "LiDAR SLAM mapping practice\n"
            "Omnidirectional mobile base for desktop arms\n"
            "ROS navigation coursework"
        ),
        features=(
            "OEM myAGV page: Payload 2000 g, 360° LiDAR, competition-level Mecanum wheels, "
            "fully wrapped metal frame, removable split structure, gmapping/cartographer "
            "ROS algorithms, built-in camera. Designed as a compound base for Elephant arms."
        ),
        payload_kg=2.0,
        reach_mm=None,
        weight_kg=None,
        repeatability_mm=None,
        dof=None,
        tags=TAGS_AGV,
        movement="wheeled",
        industry="education|research",
        uses="research|mapping|material-handling|education",
        category="industrial-robots",
        sub="learning",
    ),
    2488: arm_fix(
        rid=2488,
        name="Mercury X1",
        model="Mercury X1",
        series="mercury",
        family_name="Mercury",
        description=(
            "Mercury X1 is Elephant Robotics' wheeled humanoid platform pairing "
            "high-performance dual arms with a LiDAR/ultrasonic mobile base for "
            "teleoperation, research, and commercial demos."
        ),
        purpose=(
            "Wheeled humanoid research\n"
            "Real-time teleoperation demos\n"
            "Dual-arm mobile manipulation\n"
            "Commercial and education showcases"
        ),
        features=(
            "OEM Mercury hub: Mercury X1 maximum payload 1 kg, net weight 55 kg, "
            "repeatability ±0.05 mm, high-performance direct-drive motors, wheeled base "
            "with LiDAR/ultrasonic/vision guidance, up to 8 hours motion endurance. "
            "Dual-arm 7-DOF Mercury architecture on a mobile chassis."
        ),
        payload_kg=1.0,
        reach_mm=450,
        weight_kg=55.0,
        repeatability_mm=0.05,
        dof=None,  # dual-arm + base; OEM does not publish a single total DOF on the hub row
        tags=TAGS_MERCURY_X,
        movement="wheeled",
        industry="education|research|commercial",
        uses="research|manipulation|education",
        category="research-robots",
        sub="learning",
        source_extra=[f"{OEM}/en/mercury-humanoid-robot/"],
    ),
    2487: arm_fix(
        rid=2487,
        name="Mercury B1",
        model="Mercury B1",
        series="mercury",
        family_name="Mercury",
        description=(
            "Mercury B1 is Elephant Robotics' dual-arm 7-DOF semi-humanoid collaborative "
            "robot for education, research, and intelligent assistant demonstrations."
        ),
        purpose=(
            "Dual-arm collaborative research\n"
            "Semi-humanoid HRI demos\n"
            "Education and teleoperation labs\n"
            "Light dual-arm manipulation"
        ),
        features=(
            "OEM Mercury hub: Mercury B1 maximum payload 1 kg, net weight 8 kg, "
            "working radius 450 mm, repeatability ±0.05 mm, harmonic reducers. "
            "OEM video cites 17 DOF semi-humanoid configuration. Dual-arm collaboration "
            "with preset shortcut commands and exoskeleton/VR teleoperation support."
        ),
        payload_kg=1.0,
        reach_mm=450,
        weight_kg=8.0,
        repeatability_mm=0.05,
        dof=17,
        tags=TAGS_MERCURY_B,
        movement="stationary",
        industry="education|research",
        uses="research|manipulation|education",
        category="research-robots",
        sub="learning",
        source_extra=[f"{OEM}/en/mercury-humanoid-robot/"],
    ),
    2486: arm_fix(
        rid=2486,
        name="Mercury A1",
        model="Mercury A1",
        series="mercury",
        family_name="Mercury",
        description=(
            "Mercury A1 is Elephant Robotics' lightweight 7-DOF collaborative arm with "
            "harmonic 'Power Spring' modules, carbon-fiber shell, and myPanel teaching "
            "for research and education."
        ),
        purpose=(
            "7-DOF collaborative research\n"
            "Desktop teaching and myPanel programming\n"
            "Light pick-and-place demos\n"
            "Humanoid-series arm development"
        ),
        features=(
            "OEM Mercury hub / shop: Mercury A1 max payload 1 kg, net weight 3.5 kg, "
            "working radius 450 mm, repeatability ±0.05 mm, size 98×128×640 mm, "
            "harmonic reducer, electromagnetic friction-plate brakes, carbon fiber + "
            "aluminum + engineering plastics, myPanel 2-inch touch teaching."
        ),
        payload_kg=1.0,
        reach_mm=450,
        weight_kg=3.5,
        repeatability_mm=0.05,
        dof=7,
        tags=TAGS_MERCURY_A,
        extra_typed={"width_mm": 98, "length_mm": 128, "height_mm": 640},
        source_extra=[
            f"{OEM}/en/mercury-humanoid-robot/",
            "https://shop.elephantrobotics.com/products/mercury-humanoid-robot-series",
        ],
    ),
    2485: arm_fix(
        rid=2485,
        name="mechArm M5",
        model="mechArm 270 M5",
        series="mecharm",
        family_name="mechArm",
        description=(
            "mechArm M5 is Elephant Robotics' compact 6-axis desktop arm with built-in "
            "M5Stack-Basic controller, 270 mm reach, and 250 g payload for education and "
            "makerspace automation."
        ),
        purpose=(
            "Desktop robotics education\n"
            "M5Stack maker projects\n"
            "Light pick-and-place demos\n"
            "Drag-and-teach programming labs"
        ),
        features=(
            "OEM mechArm M5 page: 6 DOF, 270 mm working radius, 250 g payload, M5Stack "
            "ecosystem, Python / myBlockly / ROS / drag-and-teach, LEGO-compatible "
            "interfaces. Compact educational cobot form factor."
        ),
        payload_kg=0.25,
        reach_mm=270,
        weight_kg=None,
        repeatability_mm=None,
        dof=6,
        tags=TAGS_ARM,
    ),
    2484: arm_fix(
        rid=2484,
        name="mechArm Pi",
        model="mechArm 270 Pi",
        series="mecharm",
        family_name="mechArm",
        description=(
            "mechArm Pi is Elephant Robotics' Raspberry Pi–powered 6-axis desktop arm "
            "with 270 mm reach and 250 g payload for ROS education and maker projects."
        ),
        purpose=(
            "Raspberry Pi robotics education\n"
            "ROS desktop arm labs\n"
            "Light pick-and-place demos\n"
            "Drag-and-teach programming"
        ),
        features=(
            "OEM mechArm (Pi) page: 6 DOF, 270 mm working radius, 250 g payload, "
            "Raspberry Pi controller, Python / JavaScript / ROS / C# / C++ / myBlockly, "
            "HDMI, drag-and-teach, LEGO interfaces."
        ),
        payload_kg=0.25,
        reach_mm=270,
        weight_kg=None,
        repeatability_mm=None,
        dof=6,
        tags=TAGS_ARM,
    ),
    2483: arm_fix(
        rid=2483,
        name="MarsCat",
        model="MarsCat",
        series="marscat",
        family_name="MarsCat",
        description=(
            "MarsCat is Elephant Robotics' bionic robotic cat companion with articulated "
            "legs, expressive eyes, and app-based personality interactions for home and "
            "research companionship demos."
        ),
        purpose=(
            "Robotic pet companionship\n"
            "Bionic quadruped research demos\n"
            "Entertainment and HRI exhibits\n"
            "App-based interactive play"
        ),
        features=(
            "OEM MarsCat page: bionic robotic cat / home robot with articulated walking "
            "legs, expressive eye displays, and companion behaviors. No industrial payload "
            "spec on the EN PDP — fabricated 3.0 kg payload removed. Companion/entertainment "
            "positioning, not a cobot arm."
        ),
        payload_kg=None,
        reach_mm=None,
        weight_kg=None,
        repeatability_mm=None,
        dof=None,
        tags=TAGS_PET_MARS,
        movement="quadruped",
        industry="homes|entertainment|research",
        uses="companion|entertainment|research",
        category="research-robots",
        sub="companionship",
    ),
    2482: arm_fix(
        rid=2482,
        name="Elephant Robotics C3",
        model="C3",
        series="c3",
        family_name="C Series",
        description=(
            "Elephant Robotics C3 is a 6-axis all-in-one collaborative arm with 3 kg "
            "payload and 600 mm reach for commercial, education, research, and light "
            "industrial applications."
        ),
        purpose=(
            "Commercial collaborative automation\n"
            "Education and research labs\n"
            "Light industrial pick-and-place\n"
            "Voice- and cloud-programmed demos"
        ),
        features=(
            "OEM catbot-en / C Series page: Working radius 600 mm, payload 3 kg, "
            "repeatability ±0.05 mm (±0.02 mm lite), 6-axis, weight 18 kg, base φ150 mm, "
            "typical tool speed 1 m/s, graphical + cloud programming, collision stop, "
            "ISO 10218-1 Clause 5.4.3 collaboration notes, SDK Python/C++/JAVA/ROS."
        ),
        payload_kg=3.0,  # genuine OEM value for C3
        reach_mm=600,
        weight_kg=18.0,
        repeatability_mm=0.05,
        dof=6,
        tags=TAGS_C3,
        industry="education|research|manufacturing|commercial",
        uses="pick-and-place|assembly|research|education",
        category="industrial-robots",
        sub="manufacturing-industrial",
    ),
    452: arm_fix(
        rid=452,
        name="ultraArm P340",
        model="ultraArm P340",
        series="ultraarm",
        family_name="ultraArm",
        description=(
            "ultraArm P340 is Elephant Robotics' metal-structure stepper desktop arm "
            "with 340 mm reach, 650 g payload, and ±0.1 mm repeatability for drawing, "
            "laser engraving, and vision pick kits."
        ),
        purpose=(
            "STEM drawing and engraving labs\n"
            "Vision pick-and-place education\n"
            "Conveyor and slide-rail kit demos\n"
            "ROS1/ROS2 desktop arm coursework"
        ),
        features=(
            "OEM ultraArm P340 page: 340 mm working radius, 650 g payload, ± "
            "positioning accuracy ±0.1 mm, stepper motors, metal structure, ROS1 & ROS2 "
            "simulation, drawing / laser engraving / vision & picking kits."
        ),
        payload_kg=0.65,
        reach_mm=340,
        weight_kg=None,
        repeatability_mm=0.1,
        dof=4,
        tags=TAGS_ULTRA,
    ),
    451: arm_fix(
        rid=451,
        name="myBuddy 280 Pi",
        model="myBuddy 280 Pi",
        series="mybuddy",
        family_name="myBuddy",
        description=(
            "myBuddy 280 Pi is Elephant Robotics' dual-arm collaborative robot with 13 DOF, "
            "280 mm per-arm reach, and 250 g per-arm payload on a Raspberry Pi platform "
            "for education and research."
        ),
        purpose=(
            "Dual-arm collaborative education\n"
            "ROS dual-arm research\n"
            "Desktop HRI and demos\n"
            "myBlockly programming labs"
        ),
        features=(
            "OEM myBuddy 280 Pi EN page: 13 DOF, 280 mm single-arm working radius, "
            "250 g maximum payload per arm, 0.5 mm repeatability, 7-inch interactive "
            "display, dual 2 MP cameras, Raspberry Pi, ROS simulation, drag-and-teach."
        ),
        payload_kg=0.25,
        reach_mm=280,
        weight_kg=None,
        repeatability_mm=0.5,
        dof=13,
        tags=TAGS_BUDDY,
    ),
    449: arm_fix(
        rid=449,
        name="metaCat",
        model="metaCat",
        series="metacat",
        family_name="metaCat",
        description=(
            "metaCat is Elephant Robotics' furred robotic companion pet focused on "
            "lifelike interaction, companionship behaviors, and gift/entertainment use "
            "rather than industrial automation."
        ),
        purpose=(
            "Companion pet interaction\n"
            "Home entertainment\n"
            "Gift and lifestyle robotics demos"
        ),
        features=(
            "OEM metaCat EN pages: furred robotic companion pet (distinct from hard-shell "
            "MarsCat). No industrial payload/reach table on the EN PDP — fabricated 3.0 kg "
            "payload removed. Positioned for companionship and entertainment."
        ),
        payload_kg=None,
        reach_mm=None,
        weight_kg=None,
        repeatability_mm=None,
        dof=None,
        tags=TAGS_PET_META,
        movement="stationary",
        industry="homes|entertainment",
        uses="companion|entertainment",
        category="research-robots",
        sub="companionship",
    ),
}


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
        return f"{resp.status_code} {(resp.text or '')[:200]}"
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


def upload_local_hero(client: ResearchApiClient, rid: int, path: Path) -> str:
    headers = {
        key: value
        for key, value in client._session.headers.items()
        if key.lower() != "content-type"
    }
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    with path.open("rb") as handle:
        response = requests.post(
            client._url(f"robots/robots/{rid}/images/"),
            headers=headers,
            files={"images": (path.name, handle, mime)},
            data={
                "title": f"Elephant Robotics hero {rid}",
                "description": "Distinct OEM product crop/render for content-queue enrich.",
            },
            timeout=120,
        )
    response.raise_for_status()
    data = response.json()
    photos = data.get("photos") or [data.get("photo") or {}]
    url = str((photos[0] or {}).get("url") or "")
    if not url:
        raise RuntimeError(f"upload returned no URL for {rid}")
    return url


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
    }
    skip = {"videos", "notes_force", "source_note", "images", "replace_media", "local_image"}
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


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
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
        "url",
    ):
        if k in fix and fix[k] not in (None, ""):
            body[k] = fix[k]
    # Explicitly clear fabricated payload on pets when OEM has none
    if rid in (2483, 449) and "payload_kg" not in fix:
        body["payload_kg"] = None
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


def hash_url(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=90)
        if not resp.ok:
            return None
        return hashlib.md5(resp.content).hexdigest()
    except requests.RequestException:
        return None


def assert_distinct_heroes(fixes: dict[int, dict[str, Any]]) -> None:
    hashes: dict[str, int] = {}
    for rid, fix in fixes.items():
        local = fix.get("local_image")
        if local:
            data = Path(str(local)).read_bytes()
            h = hashlib.md5(data).hexdigest()
        else:
            url = fix.get("image")
            if not url:
                raise RuntimeError(f"{rid}: missing image")
            h = hash_url(str(url))
            if not h:
                raise RuntimeError(f"{rid}: failed to hash image {url}")
        if h in hashes:
            raise RuntimeError(f"hero hash collision {rid} vs {hashes[h]} md5={h}")
        hashes[h] = rid
        print(f"  hero hash {rid}: {h[:12]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Elephant Robotics company 216")
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
                print(f"dry-run reject {rid}: {reason[:100]}...")
                continue
            msg = reject_robot(rid, reason)
            print(f"reject {rid}: {msg}")

    # Preflight local heroes exist
    for rid, path in LOCAL_HERO.items():
        if rid in ROBOT_FIXES and not path.is_file():
            print(f"ERROR missing local hero {rid}: {path}", file=sys.stderr)
            return 1

    targets = []
    for rid, fix in ROBOT_FIXES.items():
        if args.only and rid not in args.only:
            continue
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        # Dry-run uses placeholder for local images
        if fix.get("local_image") and not fix.get("image"):
            fix = {**fix, "image": f"file://{fix['local_image']}"}
        row = build_row(fix, tags=tags)
        if len(row.get("features") or "") < 40:
            print(f"ERROR {rid}: features too short", file=sys.stderr)
            return 1
        if not row.get("family_key"):
            print(f"ERROR {rid}: missing family_key", file=sys.stderr)
            return 1
        if not row.get("image") and not ROBOT_FIXES[rid].get("local_image"):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": ROBOT_FIXES[rid]})
        print(
            f"  {rid} {row['name']}: payload={row.get('payload_kg')} "
            f"reach={row.get('reach_mm')} fam={row.get('family_key')} "
            f"avail={row.get('availability_status_key')} vids={len(row.get('video_urls') or [])}"
        )

    print("Hash-verifying candidate heroes...")
    try:
        assert_distinct_heroes({t["id"]: t["fix"] for t in targets})
    except RuntimeError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW.write_text(
        json.dumps(
            [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "payload_kg": t["row"].get("payload_kg"),
                    "reach_mm": t["row"].get("reach_mm"),
                    "family_key": t["row"].get("family_key"),
                    "url": t["row"].get("url"),
                    "image": (t["row"].get("image") or "")[:140],
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
        print(
            f"Preview: {PREVIEW}. Re-run with "
            "--apply --copy-media --verify-cdn --reject-dupes --mark-done"
        )
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="elephant-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    imported: list[int] = []
    for item in targets:
        rid = item["id"]
        fix = item["fix"]
        # Upload local crops first so bulk-import has a public URL
        if fix.get("local_image"):
            try:
                uploaded = upload_local_hero(client, rid, Path(str(fix["local_image"])))
                fix = {**fix, "image": uploaded}
                print(f"  uploaded local hero {rid}: {uploaded[:100]}")
            except Exception as exc:
                print(f"IMPORT FAIL {rid}: local upload {exc}", file=sys.stderr)
                continue
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        row = build_row(fix, tags=tags)
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
            patch_typed(client, rid, fix)
            notes = fix.get("notes_force")
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
        import subprocess

        rc = subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--company-id",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )
        if rc != 0:
            print("CDN verify FAILED", file=sys.stderr)
            return rc

    if args.mark_done and imported:
        # Prefer triage helper when available
        import subprocess

        subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    print("totals", totals, "copy", copy_stats, "imported", imported)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
