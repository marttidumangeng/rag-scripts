"""Backfill IIT (company 50) pending robots: correct URLs, photos, features, specs, videos, tags.

Prefer IIT-domain pages (bsr.iit.it, dls.iit.it, advr.iit.it, opentalk.iit.it) over
standalone EU project domains. Photos are official IIT / project media verified visually.
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

COMPANY_ID = 50
COMPANY_SLUG = "iit-italian-institute-of-technology"
COMPANY_NAME = "IIT (Italian Institute of Technology)"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Catalog tag names only (pipe-separated) — must match TagCatalog exactly.
TAGS_BY_NAME: dict[str, str] = {
    "GrowBot": "Research|Research Robot|Research Platform|Prototyping|Modular|Autonomous|Service Robot|Industrial",
    "HyQReal": "Quadruped|Legged|Outdoor|Industrial|Autonomous|high-payload|Research|Research Platform",
    "XoSoft": "Wearable|Healthcare|Rehabilitation|Assistive Technology|Modular|Research|Service Robot|Exoskeleton Technology",
    "PLANTOID": "Research|Research Robot|Prototyping|Modular|Autonomous|Service Robot|Industrial|Environmental Sensing",
    "I-Seed": "Research|Research Robot|Prototyping|Modular|Autonomous|3D-Printed|Service Robot|Environmental Sensing",
    "HyQCentaur": "Quadruped|Legged|Manipulation|Mobile Manipulation|Dual Arm|Research|Industrial|Autonomous",
    "HyQ": "Quadruped|Legged|Outdoor|Industrial|Autonomous|Research|Research Platform|Research Robot",
    "HyQ2Max": "Quadruped|Legged|Outdoor|Rough-Terrain|Industrial|Autonomous|Research|Research Platform|Research Robot",
    "MiniHyQ": "Quadruped|Legged|Lightweight|Portable|Compact|Research|Research Platform|Research Robot|Autonomous",
}

ROBOT_DATA: dict[str, dict[str, Any]] = {
    "GrowBot": {
        "url": "https://bsr.iit.it/climbing-plants",
        "image": "https://bsr.iit.it/documents/216217/504905/GrowBot.png/089799c5-0b81-4d14-7d6f-e4de14c606fd?t=1623395518849",
        "images": [
            "https://bsr.iit.it/documents/216217/504905/GrowBot.png/089799c5-0b81-4d14-7d6f-e4de14c606fd?t=1623395518849",
            "https://bsr.iit.it/documents/216217/504911/Tendril.png/0482079d-ab76-4db5-e7bf-146fc704ffe8?t=1623403084517",
            "https://bsr.iit.it/documents/216217/504908/Im_02.png/1b3599f0-7e44-e77e-2c72-fca70311c78e?t=1623399586574",
        ],
        "description": (
            "GrowBot is IIT's H2020 FET-Proactive line of plant-inspired growing robots that "
            "move by growing — like climbing plants — to anchor, negotiate voids, and climb "
            "where wheeled, legged, or rail climbers struggle."
        ),
        "features": (
            "Movement-by-growth paradigm inspired by climbing plants (H2020 GrowBot / FET-Proactive). "
            "Low-mass, low-volume soft robots that can anchor and climb through unstructured gaps. "
            "Osmosis-driven / reversible actuation concepts for tendril-like coiling and attachment. "
            "Bio-hybrid energy ideas converting environmental mechanical energy (wind/rain, contact) into usable power. "
            "Micropatterned attachment devices inspired by climbing-plant hooks and pads. "
            "Developed by IIT Bioinspired Soft Robotics (Barbara Mazzolai) with EU partners."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=SqZPp5r1ALk",
        ],
        "source_note": (
            "URL/features/images from bsr.iit.it/climbing-plants (IIT domain). "
            "Project overview also at growbot.eu. YouTube: GrowBot plant-inspired artefacts film."
        ),
    },
    "HyQReal": {
        "url": "https://dls.iit.it/web/dynamic-legged-systems/hyqreal",
        "image": "https://dls.iit.it/documents/216534/411410/MicrosoftTeams-image.png/b00d7a47-dc70-c9ab-6dd6-77f91691bc77?t=1632125571065",
        "images": [
            "https://dls.iit.it/documents/216534/411410/MicrosoftTeams-image.png/b00d7a47-dc70-c9ab-6dd6-77f91691bc77?t=1632125571065",
        ],
        "description": (
            "HyQReal is IIT's hydraulically powered quadruped for outdoor rough-terrain work — "
            "the rugged successor in the HyQ series, developed with Moog hydraulic components "
            "and demonstrated pulling a small aircraft at Genoa Airport (ICRA 2019)."
        ),
        "features": (
            "Hydraulically actuated quadruped with 12 joints (4 legs). "
            "Aluminum roll cage plus Kevlar / glass-fiber / plastic protective skin. "
            "Custom high-traction rubber feet; hydraulic actuators including 3D-printed titanium components. "
            "Onboard sensing: LIDAR, stereo camera for 3D mapping, joint position/torque sensing. "
            "Dual hydraulic pump units (front/hind); dual computers (vision + control); Intel Core i7 real-time Linux. "
            "Battery autonomy cited up to ~2 hours; demonstrated aircraft-towing power test with Piaggio Aerospace."
        ),
        "weight_kg": 140.0,
        "weight": "140 kg",
        "dimensions_mm": "1350x700x900",
        "dof": 12,
        "videos": [
            "https://www.youtube.com/watch?v=cj_66TzT378",
            "https://www.youtube.com/watch?v=cip4b2UdKVA",
        ],
        "source_note": (
            "Specs from dls.iit.it HyQReal page / IIT infographic (1.35 m L, 0.90 m H, 0.70 m W, 140 kg, 12 DOF). "
            "YouTube: IIT aircraft-tow demo and 2019 highlights."
        ),
    },
    "XoSoft": {
        "url": "https://advr.iit.it/exoskeletons",
        "image": "https://cordis.europa.eu/docs/results/h2020/688/688175_PS/xosoft-prototypes-2019.jpg",
        "images": [
            "https://cordis.europa.eu/docs/results/h2020/688/688175_PS/xosoft-prototypes-2019.jpg",
            "https://advr.iit.it/documents/215626/877513/XoSoft_banner.jpg/2da3a90c-937e-33d2-177a-31b4a839fa2b?t=1692357064181",
        ],
        "description": (
            "XoSoft is IIT Advanced Robotics' soft modular lower-limb wearable assistive "
            "exoskeleton (H2020 GA 688175) for people with mobility impairments — elderly, "
            "post-stroke, and incomplete SCI users — using quasi-passive soft actuation."
        ),
        "features": (
            "Soft modular biomimetic lower-limb exoskeleton (EU H2020 XoSoft). "
            "Quasi-passive / soft actuation instead of rigid powered joints for lighter wearability. "
            "Prototype lineage β1 → β2 → γ with progressive integration of harness, lumbar pack, and soft panels. "
            "Targets mobility assistance for elderly and neurological patients; also informs industrial assistive wearables research at ADVR. "
            "Intent-aware assistance combining inertial sensing, pressure sensing, and soft mechanical sensing concepts. "
            "IIT Advanced Robotics (Jesus Ortiz group) with EU consortium partners."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=KFMJqh-LMxU",
            "https://www.youtube.com/watch?v=ixulwOLMFuc",
        ],
        "source_note": (
            "URL/features from advr.iit.it/exoskeletons. Hero image: CORDIS XoSoft prototypes 2019 "
            "(official EU project result). Secondary: IIT XoSoft banner. YouTube: XoSoft Beta1 + vision intro."
        ),
    },
    "PLANTOID": {
        "url": "https://bsr.iit.it/plantoid",
        "image": "https://bsr.iit.it/documents/216217/457962/Plantoid.png/ca2a56bf-6bc1-244d-d0fe-5dbd4c4988da?t=1621331426341",
        "images": [
            "https://bsr.iit.it/documents/216217/457962/Plantoid.png/ca2a56bf-6bc1-244d-d0fe-5dbd4c4988da?t=1621331426341",
            "https://bsr.iit.it/documents/216217/457971/Plantoid_Im_01.jpg/a8a9d5b6-5e22-b549-1b15-81313a9d521c?t=1621361644105",
            "https://opentalk.iit.it/wp-content/uploads/2023/06/PLANTOID_Top-view_%C2%A9-2016-IIT_491-scaled.jpg",
        ],
        "description": (
            "PLANTOID is IIT's plant-root-inspired robot that combines root-like growth, "
            "sensing, and tropism behaviors to explore and adapt in soil-like environments — "
            "an early flagship of IIT Bioinspired Soft Robotics."
        ),
        "features": (
            "Plant-root-inspired soft robot with above-ground shoot and below-ground root modules. "
            "Sensorized root apexes for environmental exploration and tropism-like responses. "
            "Segmented flexible root actuators for soil penetration and morphological adaptation. "
            "Energy-efficient, low-speed, strong-actuation design philosophy taken from plant roots. "
            "Demonstrator platform for collective adaptive behavior and ICT inspired by root systems. "
            "Coordinated by IIT (Barbara Mazzolai) under the EU PLANTOID project."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=rHMaiExI-PM",
            "https://www.youtube.com/watch?v=32CmLWAot9Q",
        ],
        "source_note": (
            "URL/images from bsr.iit.it/plantoid (IIT domain; replaces plantoidproject.eu homepage nature photo). "
            "YouTube: Plantoid project film + plantoids overview."
        ),
    },
    "I-Seed": {
        "url": "https://opentalk.iit.it/en/iit-the-first-biodegradable-seed-robot-able-to-change-shape-in-response-to-humidity/",
        "image": "https://opentalk.iit.it/wp-content/uploads/2023/06/SEMI-ISEED-MAZZOLAI.jpg",
        "images": [
            "https://opentalk.iit.it/wp-content/uploads/2023/06/SEMI-ISEED-MAZZOLAI.jpg",
            "https://opentalk.iit.it/wp-content/uploads/2023/11/Acer-i-Seed-.jpg",
        ],
        "description": (
            "I-Seed is IIT's family of self-deployable, biodegradable soft miniaturized robots "
            "inspired by plant-seed morphology and dispersal — built for distributed "
            "environmental monitoring of soil and air (H2020 FET Proactive Environmental Intelligence)."
        ),
        "features": (
            "Seed-inspired soft robots for distributed environmental monitoring. "
            "3D/4D-printed biodegradable structures that change shape with humidity. "
            "Acer i-Seed fluorescent variants for soil-temperature monitoring readable by drones. "
            "I-Seed ERO corkscrew morphology for soil penetration; aerial seed-like dispersal concepts. "
            "Merges bioinspired robotics, materials science, AI, and environmental sensing. "
            "Led by IIT Bioinspired Soft Robotics with EU I-Seed consortium partners."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=V1K4zfqVKJA",
            "https://www.youtube.com/watch?v=98r8intxVUY",
        ],
        "source_note": (
            "URL/images from opentalk.iit.it I-Seed articles (IIT domain; replaces iseedproject.eu logo banner). "
            "YouTube: IIT biodegradable seed robot + 4D humidity-driven seed robots."
        ),
    },
    "HyQCentaur": {
        "url": "https://dls.iit.it/web/dynamic-legged-systems/hyqcentaur",
        "image": "https://dls.iit.it/documents/216534/411410/hyq_centaur2small.jpg/d692f268-aba3-45a5-f743-a2ed90e9dab5?t=1620116008869",
        "images": [
            "https://dls.iit.it/documents/216534/411410/hyq_centaur2small.jpg/d692f268-aba3-45a5-f743-a2ed90e9dab5?t=1620116008869",
            "https://dls.iit.it/documents/216534/411410/HyQ-centaur_robot_concept1_reduced.jpg/98aaeb94-ff67-4661-72f4-2f3459bad0fe?t=1620298029442",
        ],
        "description": (
            "HyQCentaur extends IIT's HyQ quadruped with torque-controlled hydraulic arms "
            "for mobile manipulation in environments where wheeled vehicles cannot go — "
            "door opening, valve work, and hazardous-material handling concepts."
        ),
        "features": (
            "HyQ quadruped base plus one or two hydraulic manipulator arms (centaur configuration). "
            "Full torque-controlled hydraulic arm without a separate external control unit. "
            "Designed for rough-terrain mobile manipulation: doors, valves, hazardous containers. "
            "Left/right arm mounting variants shown in IIT ADVR/DLS CAD and lab prototypes. "
            "Builds on HyQ's hydraulic locomotion stack for whole-body optimization research. "
            "Developed by IIT Dynamic Legged Systems (ADVR)."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=g-qR--jNtYw",
            "https://www.youtube.com/watch?v=su1Xjq1lxsA",
        ],
        "source_note": (
            "URL/images from dls.iit.it/hyqcentaur. Lab photo hyq_centaur2small + concept CAD. "
            "YouTube: whole-body optimization on HyQ Centaur; HyQ platform overview as locomotion base."
        ),
    },
    "HyQ": {
        "url": "https://dls.iit.it/web/dynamic-legged-systems/hyq",
        "image": "https://dls.iit.it/documents/216534/411410/HyQ_and_HyQ_bluesmall.jpg/31140c3a-36a5-96ac-5262-43d2d54873bc?t=1620116009077",
        "images": [
            "https://dls.iit.it/documents/216534/411410/HyQ_and_HyQ_bluesmall.jpg/31140c3a-36a5-96ac-5262-43d2d54873bc?t=1620116009077",
            "https://dls.iit.it/documents/216534/411410/hyq_robot_stage2_cad.jpg/e10efb32-65d4-b605-ffe4-480d64cf8338?t=1620218654421",
        ],
        "description": (
            "HyQ (Hydraulically actuated Quadruped) is IIT's fully torque-controlled hydraulic "
            "quadruped research platform for versatile rough-terrain locomotion, compliance, "
            "and energy-efficient gaits — the foundation of the HyQ robot series since ~2007–2011."
        ),
        "features": (
            "Fully torque-controlled hydraulically actuated quadruped (12 active DOF). "
            "8 hydraulic cylinders (hip/knee flexion-extension) + 4 rotary hip abduction/adduction actuators. "
            "Peak cylinder torque ~181 Nm and rotary actuator ~120 Nm at 200 bar. "
            "Onboard joint position/torque sensing, IMU, hydraulic pressure sensing, stereo vision. "
            "Lab treadmill and outdoor rough-terrain testing since 2011. "
            "Applications researched: disaster response, hazardous inspection, rough outdoor mobility."
        ),
        "weight_kg": 80.0,
        "weight": "80 kg (external hydraulic supply); 100 kg (onboard supply)",
        "dimensions_mm": "1000x500x980",
        "dof": 12,
        "videos": [
            "https://www.youtube.com/watch?v=su1Xjq1lxsA",
            "https://www.youtube.com/watch?v=4FcPz7neqvc",
        ],
        "source_note": (
            "Specs from dls.iit.it/hyq table: 1.0×0.5×0.98 m, 80/100 kg, 12 DOF, torque figures. "
            "YouTube: HyQ overview + leg assembly."
        ),
    },
    "HyQ2Max": {
        "url": "https://dls.iit.it/hyq2max",
        "image": (
            "https://dls.iit.it/documents/216534/411410/HyQ2Maxsmall.jpg/"
            "132f8da4-fc6e-f4c2-4e88-5c68320f77db?t=1620116008740"
        ),
        "images": [
            (
                "https://dls.iit.it/documents/216534/411410/HyQ2Maxsmall.jpg/"
                "132f8da4-fc6e-f4c2-4e88-5c68320f77db?t=1620116008740"
            ),
            "https://dls.iit.it/o/adaptive-media/image/411430/Preview-1000x0/HyQ2Maxsmall.jpg?t=1620116008740",
        ],
        "description": (
            "HyQ2Max is IIT's improved hydraulic quadruped successor to HyQ — built for "
            "greater strength, robustness, and versatility with a much larger joint range "
            "and higher joint torque at essentially the same overall weight."
        ),
        "features": (
            "Improved hydraulic quadruped vs HyQ: higher reliability/robustness, larger joint ROM, "
            "higher joint torque at ~zero weight cost. "
            "Impact- and dirt-resistant layout: sensors, valves, actuators, and electronics protected inside the structure. "
            "Aerospace-grade 7000-series aluminium torso frame with front/rear tubular roll frames "
            "and glass-fibre/Kevlar covers. "
            "12 active DOF; hydraulic actuation with high peak joint torques (IEEE T-MECH 2016). "
            "Developed by IIT Dynamic Legged Systems (DLS)."
        ),
        "weight_kg": 80.0,
        "weight": "80 kg (offboard power)",
        "dimensions_mm": "1306x544x918",
        "length_mm": 1306.0,
        "width_mm": 544.0,
        "height_mm": 918.0,
        "dof": 12,
        "videos": [
            "https://www.youtube.com/watch?v=Azu-FA_3ClM",
            "https://www.youtube.com/watch?v=wEXkWj5NSyI",
        ],
        "source_note": (
            "URL https://dls.iit.it/hyq2max (CRM /robots/hyq2max 404). "
            "Hero from DLS robots carousel HyQ2Maxsmall.jpg. "
            "Specs from IEEE T-MECH 2016 Table III linked from product page "
            "(1.306×0.544×0.918 m, 80 kg offboard, 12 DOF). "
            "YouTube: HyQ2Max Video Teaser + 'robot you can't keep down'."
        ),
    },
    "MiniHyQ": {
        "url": "https://dls.iit.it/robots",
        "image": (
            "https://dls.iit.it/documents/216534/411410/MiniHyQsmall.jpg/"
            "344c1876-e189-1623-d0ec-fb0209e7f763?t=1620116008963"
        ),
        "images": [
            (
                "https://dls.iit.it/documents/216534/411410/MiniHyQsmall.jpg/"
                "344c1876-e189-1623-d0ec-fb0209e7f763?t=1620116008963"
            ),
            "https://dls.iit.it/o/adaptive-media/image/411459/Preview-1000x0/MiniHyQsmall.jpg?t=1620116008963",
        ],
        "description": (
            "MiniHyQ is IIT's compact hydraulic quadruped — among the lightest of its class — "
            "fully torque-controlled with reconfigurable leg layouts, wide joint range, "
            "and an onboard compact hydraulic power pack, portable by one person."
        ),
        "features": (
            "Lightweight hydraulic quadruped (35 kg with onboard pack; 24 kg with offboard pump). "
            "Fully torque-controlled; reconfigurable leg configurations. "
            "Wide joint range of motion enabling self-righting; hydraulic rotary hip + linear knee "
            "actuators with isogram mechanism. "
            "Onboard compact hydraulic power pack (13 L/min, 20 MPa per TEPRA 2015 paper). "
            "Portable by one person. Developed by IIT Dynamic Legged Systems (DLS)."
        ),
        "weight_kg": 35.0,
        "weight": "35 kg (onboard pump); 24 kg (offboard pump)",
        "dimensions_mm": "850x350x770",
        "length_mm": 850.0,
        "width_mm": 350.0,
        "height_mm": 770.0,
        "dof": 12,
        "videos": [
            "https://www.youtube.com/watch?v=Yux0FMzUzPo",
        ],
        "source_note": (
            "No dedicated /minihyq page — description on https://dls.iit.it/robots. "
            "Hero MiniHyQsmall.jpg from DLS carousel. "
            "Specs from TEPRA 2015 (khan15tepra.pdf) cited by DLS: "
            "0.85×0.35×0.77 m fully stretched, 35/24 kg, 12 DOF. "
            "YouTube: Development of MiniHyQ (TEPRA'15)."
        ),
    },
}


def verify_image(url: str) -> bool:
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code == 405 or "image" not in (resp.headers.get("content-type") or "").lower():
            resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
            resp.close()
        ctype = (resp.headers.get("content-type") or "").lower()
        if resp.status_code != 200:
            return False
        if "image" in ctype:
            return True
        return bool(re.search(r"\.(png|jpe?g|webp)(\?|$)", url, re.I))
    except requests.RequestException:
        return False


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
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
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.1)
    return ok, fail


def build_row(robot: dict, data: dict[str, Any]) -> dict[str, Any]:
    images = [u for u in data.get("images") or [] if verify_image(u)]
    hero = data.get("image") or ""
    if hero and verify_image(hero):
        if hero not in images:
            images = [hero, *images]
    elif images:
        hero = images[0]
    else:
        hero = ""

    videos = enrich_video_list(data.get("videos") or [])
    row: dict[str, Any] = {
        "name": robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "IT",
        "description": data["description"],
        "purpose": data["description"],
        "features": data["features"],
        "url": data["url"],
        "image": hero,
        "images": images,
        "video_urls": videos,
        "movement_type_keys": data.get("movement") or "quadruped",
        "category_slugs": data.get("category") or "ground",
        "sub_category_slug": data.get("sub_category") or "research",
        "sources": [{"url": data["url"], "type": "website", "title": robot["name"]}],
        "research_notes": data.get("source_note") or "IIT product enrichment.",
        "tags": TAGS_BY_NAME.get(robot["name"]) or "Research|Industrial",
    }
    if data.get("weight_kg") is not None:
        row["weight_kg"] = data["weight_kg"]
    if data.get("weight"):
        row["weight"] = data["weight"]
    if data.get("dimensions_mm"):
        row["dimensions_mm"] = data["dimensions_mm"]
    for key in ("length_mm", "width_mm", "height_mm"):
        if data.get(key) is not None:
            row[key] = data[key]
    if data.get("dof") is not None:
        row["dof"] = data["dof"]

    # Soft / wearable / plant robots are not quadrupeds.
    if robot["name"] in {"GrowBot", "PLANTOID", "I-Seed"}:
        row["movement_type_keys"] = "other"
        row["category_slugs"] = "service-robots"
        row["sub_category_slug"] = "research"
    if robot["name"] == "XoSoft":
        row["movement_type_keys"] = "wearable"
        row["category_slugs"] = "service-robots"
        row["sub_category_slug"] = "healthcare"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix IIT robots for company 50")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument(
        "--names",
        default="",
        help="Comma-separated robot names to process (default: all curated pending)",
    )
    args = parser.parse_args()

    only = {n.strip() for n in args.names.split(",") if n.strip()} if args.names else set()

    client = ResearchApiClient()
    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") != "published"
    ]
    if only:
        robots = [r for r in robots if r.get("name") in only]
    print(f"targets: {len(robots)}" + (f" (filter={sorted(only)})" if only else ""))

    plan = []
    staging: dict[int, dict] = {}
    for robot in robots:
        data = ROBOT_DATA.get(robot["name"])
        if not data:
            print(f"SKIP {robot['id']} {robot['name']}: no curated data")
            continue
        row = build_row(robot, data)
        staging[int(robot["id"])] = row
        plan.append({
            "id": robot["id"],
            "name": robot["name"],
            "url": row.get("url"),
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "weight_kg": row.get("weight_kg"),
            "dof": row.get("dof"),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
        })
        print(
            f"{robot['name']}: img={'yes' if row.get('image') else 'no'} "
            f"feat={len(row.get('features') or '')} weight={row.get('weight_kg')} "
            f"dof={row.get('dof')} vids={len(row.get('video_urls') or [])} "
            f"url={row.get('url')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "iit-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    incomplete = [
        p for p in plan
        if not p["image"] or not p["features_len"] or not p["videos"] or not p["tags"]
    ]
    if incomplete:
        print("ERROR: incomplete enrichment:", incomplete, file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="iit-fix-"))
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

    print(json.dumps({"ok": all_ok, **totals}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
