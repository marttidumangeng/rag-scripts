"""Fix Trossen Robotics (company 307) content-queue gaps.

Rejects TOTL PC / tutorial thumbs / Hugging Face graphics / gripper-only closeups
and shared site OG. Prefers Wix product stills + docs.trossenrobotics.com X-series
heroes. Skips published ALOHA Mobile V2.0 (5265).
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

COMPANY_ID = 307
COMPANY_SLUG = "trossen-robotics"
COMPANY_NAME = "Trossen Robotics"


def _wix(mid: str, ext: str = "png", w: int = 1400, h: int = 1050) -> str:
    """Stable Wix fill URL for a media id (prefix like d3716d_hex)."""
    file_stem = f"{mid}~mv2.{ext}"
    return (
        f"https://static.wixstatic.com/media/{file_stem}"
        f"/v1/fill/w_{w},h_{h},al_c,q_90/{file_stem}"
    )


# Visually verified 2026-07-14 (reject PC / tutorials / HG graphics / gripper-only).
IMG_SOLO = _wix("d3716d_7c5a120850e44a25a3c3f7cbfacf91ed", "png")  # Solo leader+follower + tablet
IMG_STATIONARY = _wix("d3716d_af935404f33e46c2861450b084477412", "png")  # bimanual ALOHA frame
IMG_MOBILE_AI = _wix("d3716d_70ee60d93d8d4ac1969f4e9501db2a05", "png")  # Mobile AI chassis + arms
IMG_PX100 = "https://docs.trossenrobotics.com/interbotix_xsarms_docs/_images/px100.png"
IMG_VX300 = "https://docs.trossenrobotics.com/interbotix_xsarms_docs/_images/vx300.png"
IMG_WX250 = "https://docs.trossenrobotics.com/interbotix_xsarms_docs/_images/wx250.png"
IMG_VIPER_ALOHA = _wix("d3716d_a8da5eaeb6d1425da9f7fc1e8059513e", "png", 1200, 900)  # TROSSEN + RealSense
IMG_WIDOW_AI = IMG_VIPER_ALOHA  # same AI-ready arm still; WidowX AI page lacks full-arm hero
IMG_WIDOW_ALOHA_SET = IMG_STATIONARY  # matched leader/follower kit context

TAGS_SOLO = "AI|Data Collection|Machine Learning|Portable|Research|Robotic Arm"
TAGS_STATIONARY = "AI|Education|Machine Learning|Research|Robotics Research|Stationary"
TAGS_MOBILE = "AI|Data Collection|Machine Learning|Mobile Robot|Research|Wheeled"
TAGS_PX = "Compact|Education|Manipulation|Research|Robotic Arm|Stationary"
TAGS_VX = "6-Axis|Manipulation|Research|Research Robot|Robotic Arm|Stationary"
TAGS_VX_ALOHA = "6-Axis|Machine Learning|Manipulation|Research|Research Robot|Robotic Arm"
TAGS_WX = "6-Axis|Education|Manipulation|Research|Research Robot|Robotic Arm"
TAGS_WX_AI = "6-Axis|AI|Machine Learning|Research|Robotic Arm|Stationary"
TAGS_WX_SET = (
    "Data Collection|Machine Learning|Research|Research Platform|Robotic Arm|Robotics Research"
)

# Product demos only (oEmbed-checked). Reject LeRobot/Colab/software-primary clips.
YT_SOLO = [
    "https://www.youtube.com/watch?v=E0AdjrUvtLk",  # Aloha Solo In Action
    "https://www.youtube.com/watch?v=cwexO9Cf9s4",  # Aloha Solo Ad 2
    "https://www.youtube.com/watch?v=ZafCcc-mu4I",  # Trossen Solo AI kit
]
YT_STATIONARY = [
    "https://www.youtube.com/watch?v=mFgiSRtKg5M",  # Trossen Stationary AI
    "https://www.youtube.com/watch?v=dCsocGe736o",  # Aloha is now Trossen AI
]
YT_MOBILE = [
    "https://www.youtube.com/watch?v=hCAehlKs-sg",  # Trossen Mobile AI kit
]
YT_PX = [
    "https://www.youtube.com/watch?v=u1Cpx2sCkLE",  # PincherX 100 Payload Test
    "https://www.youtube.com/watch?v=hc6bQTv2fJQ",  # X-Series PincherX 100
    "https://www.youtube.com/watch?v=8Q3oiBn_P7U",  # Introducing PincherX 100
]
YT_VX = [
    "https://www.youtube.com/watch?v=UHdXCvbnv1o",  # X-Series ViperX 300
    "https://www.youtube.com/watch?v=G2hLbEzCLk0",  # ViperX 300 Payload Test
    "https://www.youtube.com/watch?v=Q30WBYfOdGA",  # ViperX CNC door
]
YT_VX_ALOHA = [
    "https://www.youtube.com/watch?v=mFgiSRtKg5M",  # Stationary AI (shows follower arms)
    "https://www.youtube.com/watch?v=PAZeG0qehYI",  # Aloha hardware configuration
    "https://www.youtube.com/watch?v=8G9gxX3DB9Q",  # Stationary hardware assembly
]
YT_WX = [
    "https://www.youtube.com/watch?v=OOMabEnktQs",  # WidowX 250 Payload Test
    "https://www.youtube.com/watch?v=l_10IHoJNxI",  # X-Series WidowX 250
]
YT_WX_AI = [
    "https://www.youtube.com/watch?v=vi7u3XxYNLs",  # WidowX AI Overview
    "https://www.youtube.com/watch?v=tFe33xlAuy4",  # WidowX AI arm styling
    "https://www.youtube.com/watch?v=Teb6jeyjVl4",  # WidowX AI bumpers
]
YT_WX_SET = [
    "https://www.youtube.com/watch?v=mFgiSRtKg5M",
    "https://www.youtube.com/watch?v=dCsocGe736o",
    "https://www.youtube.com/watch?v=PAZeG0qehYI",
]

# Specs from Interbotix X-series / PDP claims only (no invented Aloha kit payload).
ROBOT_FIXES: dict[int, dict[str, Any]] = {
    5266: {
        "name": "ALOHA Solo",
        "model_name": "ALOHA Solo",
        "url": "https://www.trossenrobotics.com/aloha-solo",
        "image": IMG_SOLO,
        "images": [IMG_SOLO],
        "replace_media": True,
        "description": (
            "Portable single leader–follower ALOHA machine-learning kit for teleoperation "
            "data collection and on-device / cloud training."
        ),
        "features": (
            "Portable leader–follower arm pair on a shared rail with wrist + workspace cameras. "
            "Supports Hugging Face LeRobot and Interbotix ROS data pipelines; optional "
            "preloaded Linux laptop. Starting price cited on OEM page (~$8,999.95)."
        ),
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "research-robots",
        "sub_category_slug": "research-platforms",
        "tags": TAGS_SOLO,
        "videos": YT_SOLO,
        "notes_force": (
            "Hero: Wix Solo product still (leader+follower+tablet; rejected shared OG / "
            "laptop-only / System76 chrome). Videos: product demos only — removed LeRobot/"
            "Colab/software tutorials from CRM."
        ),
        "source_note": "trossenrobotics.com/aloha-solo + YT E0AdjrUvtLk/cwexO9Cf9s4/ZafCcc-mu4I",
    },
    5267: {
        "name": "ALOHA Stationary V2.0",
        "model_name": "ALOHA Stationary V2.0",
        "url": "https://www.trossenrobotics.com/aloha-stationary",
        "image": IMG_STATIONARY,
        "images": [IMG_STATIONARY],
        "replace_media": True,
        "description": (
            "Official ALOHA Stationary bimanual teleoperation / ML kit with gravity-compensated "
            "leader arms and ViperX-class followers."
        ),
        "features": (
            "Bimanual ALOHA frame with dual leader + dual follower arms, Aero-Motive gravity "
            "compensators, overhead and table RealSense views, upgraded grippers/haptics/"
            "joints. Optional preloaded Linux laptop."
        ),
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "research-robots",
        "sub_category_slug": "research-platforms",
        "tags": TAGS_STATIONARY,
        "videos": YT_STATIONARY,
        "notes_force": (
            "Hero: Wix full Stationary kit still (rejected assembly-guide thumbs / shared OG). "
            "Videos: Stationary AI product clips — not Mobile assembly or software series."
        ),
        "source_note": "trossenrobotics.com/aloha-stationary + YT mFgiSRtKg5M/dCsocGe736o",
    },
    5268: {
        "name": "Mobile AI",
        "model_name": "Mobile AI",
        "url": "https://www.trossenrobotics.com/mobile-ai",
        "image": IMG_MOBILE_AI,
        "images": [IMG_MOBILE_AI],
        "replace_media": True,
        "description": (
            "Trossen Mobile AI — wheeled machine-learning kit with dual WidowX AI "
            "leader–follower pairs."
        ),
        "features": (
            "Mobile research kit: 2× WidowX AI leader–follower pairs, 3× Intel RealSense D405 "
            "cameras, integrated wheeled base / SLATE-compatible chassis, optional "
            "high-performance laptop and on-device training. Prices cited on OEM page from "
            "~$33,695.95."
        ),
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "research-robots",
        "sub_category_slug": "research-platforms",
        "tags": TAGS_MOBILE,
        "videos": YT_MOBILE,
        "notes_force": (
            "Hero: Wix Mobile AI chassis+arms (rejected TOTL workstation PC / OpenPi software "
            "clips / WidowX assembly thumbs mistagged on CRM)."
        ),
        "source_note": "trossenrobotics.com/mobile-ai + YT hCAehlKs-sg",
    },
    5269: {
        "name": "PincherX 100",
        "model_name": "PincherX 100",
        "url": "https://www.trossenrobotics.com/pincherx100",
        "image": IMG_PX100,
        "images": [IMG_PX100],
        "replace_media": True,
        "description": "Compact Interbotix PincherX 100 4-DoF research manipulator (50 g / ~300 mm).",
        "features": (
            "Compact 4-DoF X-series arm with XL-430 Dynamixel servos and parallel gripper. "
            "OEM/docs cite ~50 g payload and ~300 mm reach; custom 3D-printed end-effectors "
            "supported. Education / first-arm research platform."
        ),
        "dof": 4,
        "payload_kg": 0.05,
        "reach_mm": 300.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "research-robots",
        "sub_category_slug": "research-platforms",
        "tags": TAGS_PX,
        "videos": YT_PX,
        "notes_force": (
            "Hero: docs.trossenrobotics.com px100.png (PX-100 plate). Specs: 4 DoF / 50 g / "
            "300 mm from X-series PDP (ignored cross-product reach noise on page)."
        ),
        "source_note": "docs + trossenrobotics.com/pincherx100; YT u1Cpx2sCkLE",
    },
    5270: {
        "name": "ViperX 300 S",
        "model_name": "ViperX 300 S",
        "url": "https://www.trossenrobotics.com/viperx-300",
        "image": IMG_VX300,
        "images": [IMG_VX300],
        "replace_media": True,
        "description": "Interbotix ViperX 300 S 6-DoF research arm (750 g / 750 mm).",
        "features": (
            "Largest X-series research manipulator: 6 DoF, ~750 g payload, ~750 mm reach, "
            "~1 mm class repeatability (OEM). DYNAMIXEL actuation; stationary or mobile mounts; "
            "custom 3D-printed end-effectors."
        ),
        "dof": 6,
        "payload_kg": 0.75,
        "reach_mm": 750.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "research-robots",
        "sub_category_slug": "research-platforms",
        "tags": TAGS_VX,
        "videos": YT_VX,
        "notes_force": (
            "Hero: docs vx300.png (full arm). Rejected VX-300 base-only closeup as primary. "
            "Specs 6 DoF / 750 g / 750 mm from X-series PDP."
        ),
        "source_note": "docs + trossenrobotics.com/viperx-300; YT UHdXCvbnv1o/G2hLbEzCLk0",
    },
    5271: {
        "name": "ViperX Aloha Follower Arm V2.0",
        "model_name": "ViperX Aloha Follower V2.0",
        "url": "https://www.trossenrobotics.com/viperx-aloha",
        "image": IMG_VIPER_ALOHA,
        "images": [IMG_VIPER_ALOHA],
        "replace_media": True,
        "description": (
            "ALOHA-tuned ViperX follower arm (6 DoF / 750 g / 750 mm class) with upgraded "
            "grippers and camera mount."
        ),
        "features": (
            "ViperX-class ALOHA follower: 6 DoF, ~750 g payload, ~750 mm reach / ~1500 mm "
            "span class, ~1 mm repeatability. Upgraded grippers, haptics, and joints for "
            "bimanual Stationary kits."
        ),
        "dof": 6,
        "payload_kg": 0.75,
        "reach_mm": 750.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "research-robots",
        "sub_category_slug": "research-platforms",
        "tags": TAGS_VX_ALOHA,
        "videos": YT_VX_ALOHA,
        "notes_force": (
            "Hero: Wix TROSSEN+RealSense arm (rejected Hugging Face Cloud Storage graphic). "
            "Videos: kit hardware/config — not Solo ads mistagged on CRM."
        ),
        "source_note": "trossenrobotics.com/viperx-aloha; YT mFgiSRtKg5M/PAZeG0qehYI",
    },
    5272: {
        "name": "WidowX 250 S",
        "model_name": "WidowX 250 S",
        "url": "https://www.trossenrobotics.com/widowx-250",
        "image": IMG_WX250,
        "images": [IMG_WX250],
        "replace_media": True,
        "description": "Interbotix WidowX 250 S 6-DoF research arm (250 g / 650 mm).",
        "features": (
            "Go-to teleoperation / research arm: 6 DoF, ~250 g payload, ~650 mm reach "
            "(OEM/docs). ROS 2 support; custom 3D-printed end-effectors."
        ),
        "dof": 6,
        "payload_kg": 0.25,
        "reach_mm": 650.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "research-robots",
        "sub_category_slug": "research-platforms",
        "tags": TAGS_WX,
        "videos": YT_WX,
        "notes_force": (
            "Hero: docs wx250.png. Specs 6 DoF / 250 g / 650 mm from X-series PDP. Removed "
            "WidowX AI assembly clip mistagged as WidowX 250 media."
        ),
        "source_note": "docs + trossenrobotics.com/widowx-250; YT OOMabEnktQs/l_10IHoJNxI",
    },
    5273: {
        "name": "WidowX AI",
        "model_name": "WidowX AI",
        "url": "https://www.trossenrobotics.com/widowx-ai",
        "image": IMG_WIDOW_AI,
        "images": [IMG_WIDOW_AI],
        "replace_media": True,
        "description": (
            "Next-gen WidowX AI manipulator for ML research — Base / Leader / Follower SKUs."
        ),
        "features": (
            "WidowX AI 6-DoF arm with precision grip end-effector and molded silicone pads. "
            "Available as Base, Leader, and Follower configurations for Mobile AI / ALOHA "
            "pipelines. OEM cites ~4 kg arm mass class."
        ),
        "dof": 6,
        "weight_kg": 4.0,
        "weight": "4 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "research-robots",
        "sub_category_slug": "research-platforms",
        "tags": TAGS_WX_AI,
        "videos": YT_WX_AI,
        "notes_force": (
            "Hero: AI-ready TROSSEN+camera arm still (WidowX AI PDP lacked full-arm hero; "
            "rejected TOTL PC / gripper-only / logo crops). Videos: WidowX AI overview + "
            "styling — not OpenPi / generic assembly."
        ),
        "source_note": "trossenrobotics.com/widowx-ai; YT vi7u3XxYNLs/tFe33xlAuy4/Teb6jeyjVl4",
    },
    5274: {
        "name": "WidowX Aloha Set",
        "model_name": "WidowX Aloha Set",
        "url": "https://www.trossenrobotics.com/widowx-aloha-set",
        "image": IMG_WIDOW_ALOHA_SET,
        "images": [IMG_WIDOW_ALOHA_SET],
        "replace_media": True,
        "description": (
            "Matched WidowX ALOHA leader-arm set for bimanual teleoperation / ML kits."
        ),
        "features": (
            "Pre-configured matched WidowX leader pair for ALOHA kits: 6 DoF, ~250 g payload, "
            "~650 mm reach / ~1300 mm span class. Upgraded grippers, haptics, joints; gravity "
            "compensation compatible."
        ),
        "dof": 6,
        "payload_kg": 0.25,
        "reach_mm": 650.0,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "research-robots",
        "sub_category_slug": "research-platforms",
        "tags": TAGS_WX_SET,
        "videos": YT_WX_SET,
        "notes_force": (
            "Hero: shared Stationary kit still (context for matched leader set; rejected "
            "assembly-guide thumbs / Solo ads previously on CRM)."
        ),
        "source_note": "trossenrobotics.com/widowx-aloha-set; YT mFgiSRtKg5M/dCsocGe736o",
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
        except requests.RequestException as e:
            fail += 1
            print(f"copy-media fail {rid}: {e}", flush=True)
        time.sleep(0.15)
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Trossen Robotics company 307 robots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--no-replace-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
    parser.add_argument("--mark-done", action="store_true")
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

    preview = _RESEARCH_DIR / "staging" / "reports" / "trossen-fix-preview.json"
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

    tmp = Path(tempfile.mkdtemp(prefix="trossen-fix-"))
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

    if args.mark_done and all_ok and len(imported) >= len(ROBOT_FIXES):
        done = _RESEARCH_DIR / "state" / "content_queue_done.json"
        done.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if done.is_file():
            try:
                data = json.loads(done.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        # Merge company_ids + legacy companies[] — never replace with a singleton set.
        ids: set[int] = set()
        for key in ("company_ids", "companies"):
            for x in data.get(key) or []:
                try:
                    ids.add(int(x))
                except (TypeError, ValueError):
                    continue
        ids.add(COMPANY_ID)
        merged = sorted(ids)
        data["companies"] = merged
        data["company_ids"] = merged
        data.setdefault("notes", {})[str(COMPANY_ID)] = (
            "2026-07-14 Trossen: 9/9 pending enriched (skipped published 5265)"
        )
        done.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Marked company {COMPANY_ID} done in {done} (n={len(merged)})")

    out = {"ok": all_ok, **totals, "imported": imported, "copy_media": copy_stats}
    (_RESEARCH_DIR / "staging" / "reports" / "trossen-fix-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
