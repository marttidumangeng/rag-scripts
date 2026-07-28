"""Fix Realman Robotics (company 882) content-queue gaps.

Videos/specs/tags plus CDN repair: many robots had CDN *path strings* in
`image` with empty `s3_image` and CloudFront AccessDenied. copy-media skips
owned CDN sources (`is_owned_media_url`) then still returns success — always
HTTP-GET verify with `verify_cdn_images.py` after copy-media.

Default: replace heroes from OEM `docs/_realman_qa/heroes.json` + copy-media.
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

COMPANY_ID = 882
COMPANY_SLUG = "realman-beijing-intelligent-technology-co-ltd"
COMPANY_NAME = "Realman (Beijing) Intelligent Technology Co., Ltd."

_HEROES_JSON = _RESEARCH_DIR / "docs" / "_realman_qa" / "heroes.json"


def _load_oem_heroes() -> dict[int, str]:
    if not _HEROES_JSON.is_file():
        return {}
    raw = json.loads(_HEROES_JSON.read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    for k, v in raw.items():
        url = (v or {}).get("url") if isinstance(v, dict) else None
        if url:
            out[int(k)] = str(url).strip()
    return out


OEM_HEROES = _load_oem_heroes()

# Title-verified YouTube (oEmbed 2026-07-14).
YT_ECO_RM_SERIES = "https://www.youtube.com/watch?v=2ecQGCLOY3Q"  # Lab Automation | ECO & RM Series
YT_ECO65 = "https://www.youtube.com/watch?v=LvXvDEfAQaM"  # ECO65 series
YT_ECO63_POLISH = "https://www.youtube.com/watch?v=YFEaiHXNi5Y"  # ECO63 polishing
YT_RM75 = "https://www.youtube.com/watch?v=RLu4TGtKXu4"  # RM75 series
YT_RM75_FLAG = "https://www.youtube.com/watch?v=KPAI3PJAgTs"  # Flagship RM75 7-DOF
YT_RM65 = "https://www.youtube.com/watch?v=fMZ5sn5irpo"  # RM65-B brute force
YT_RX_LIGHT = "https://www.youtube.com/watch?v=CM9b4EGjb_E"  # 48V ultra-lightweight arm
YT_CES_ARMS = "https://www.youtube.com/watch?v=LF96dkzeNrY"  # CES 2026 arms
YT_DUAL_LIFT = "https://www.youtube.com/watch?v=CNOw9z1i2x4"  # Dual-arm lift towels
YT_DUAL_COMPOUND = "https://www.youtube.com/watch?v=1TE2TJ_tdNs"  # Compound dual-arm
YT_SINGLE_LIFT = "https://www.youtube.com/watch?v=8ErpQ8VB9ro"  # lifting dumbbells
YT_REALBOT = "https://www.youtube.com/watch?v=lDQr8GTxFJE"  # RealBOT material handling
YT_REALBOT_CES = "https://www.youtube.com/watch?v=NNje7gQCAEQ"  # RealBOT CES debut

TAGS_ECO = "6-Axis|Collaborative Robot|Lightweight|Industrial Arm|Pick-and-Place|Education"
TAGS_RM6 = "6-Axis|Collaborative Robot|Lightweight|Industrial|Manufacturing|Stationary"
TAGS_RM7 = "7-DoF|Collaborative Robot|Lightweight|Industrial Arm|Precision|Stationary"
TAGS_RX7 = "7-DoF|Collaborative Robot|Humanoid|Lightweight|Industrial Arm|Manipulation"
TAGS_LIFT = "Autonomous|Dual Arm|Lifting|Mobile Manipulator|Vision|Wheeled"
TAGS_SINGLE = "Autonomous|Compact|Logistics|Mobile Manipulator|Retail|Wheeled"
TAGS_CHASSIS = "Autonomous|Mobile Robot|Wheeled|Logistics|Research Platform"
TAGS_HUMAN = "Humanoid|Autonomous|Wheeled|Service|Research|AI"

# Specs cited from realman-robotics.com EN Technical Specifications tables.
ROBOT_FIXES: dict[int, dict[str, Any]] = {
    5220: {  # ECO62 — no_videos
        "name": "ECO62",
        "model_name": "ECO62",
        "url": "https://www.realman-robotics.com/en/products/eco62.html",
        "dof": 6,
        "payload_kg": 1.0,
        "reach_mm": 355.0,
        "weight_kg": 3.3,
        "weight": "3.3 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_ECO,
        "videos": [YT_ECO_RM_SERIES, YT_ECO65],
        "notes_force": (
            "OEM specs (eco62.html): 6 DoF, 355 mm working radius, 1 kg payload, 3.3 kg net weight. "
            "No ECO62-titled YouTube found — used official ECO & RM Series lab demo + ECO65 sibling series clip."
        ),
        "source_note": "realman-robotics.com/en/products/eco62.html Technical Specifications",
    },
    5221: {  # ECO63 — no_videos
        "name": "ECO63",
        "model_name": "ECO63",
        "url": "https://www.realman-robotics.com/en/products/eco63.html",
        "dof": 6,
        "payload_kg": 3.0,
        "reach_mm": 900.0,
        "weight_kg": 9.5,
        "weight": "9.5 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_ECO,
        "videos": [YT_ECO63_POLISH, YT_ECO_RM_SERIES],
        "notes_force": (
            "OEM specs (eco63.html): 6 DoF, 900 mm working radius, 3 kg payload, 9.5 kg net weight. "
            "Videos: ECO63 polishing + ECO & RM Series lab demo."
        ),
        "source_note": "realman-robotics.com/en/products/eco63.html Technical Specifications",
    },
    5222: {  # ECO65 — wrong shelf-scan video
        "name": "ECO65",
        "model_name": "ECO65",
        "url": "https://www.realman-robotics.com/en/products/eco65.html",
        "dof": 6,
        "payload_kg": 5.0,
        "reach_mm": 610.0,
        "weight_kg": 7.8,
        "weight": "7.8 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": "6-Axis|Assembly|Collaborative Robot|Factory Automation|Industrial Arm|Lightweight",
        "videos": [YT_ECO65, YT_ECO_RM_SERIES],
        "notes_force": (
            "OEM specs (eco65.html): 6 DoF, 610 mm working radius, 5 kg payload, 7.8 kg net weight. "
            "Replaced unrelated shelf-scanning clip with ECO65 series product demo."
        ),
        "source_note": "realman-robotics.com/en/products/eco65.html + LvXvDEfAQaM",
    },
    5228: {  # RM75 — no_videos
        "name": "RM75",
        "model_name": "RM75",
        "url": "https://www.realman-robotics.com/en/products/rm75.html",
        "dof": 7,
        "payload_kg": 5.0,
        "reach_mm": 610.0,
        "weight_kg": 7.8,
        "weight": "7.8 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_RM7,
        "videos": [YT_RM75, YT_RM75_FLAG],
        "notes_force": (
            "OEM specs (rm75.html): 7 DoF, 610 mm working radius, 5 kg payload, 7.8 kg net weight. "
            "Model-titled YouTube: RM75 series + flagship RM75 short."
        ),
        "source_note": "realman-robotics.com/en/products/rm75.html Technical Specifications",
    },
    5230: {  # RX71 — no_videos; mistagged 6-Axis
        "name": "RX71",
        "model_name": "RX71",
        "url": "https://www.realman-robotics.com/en/products/rx71.html",
        "dof": 7,
        "payload_kg": 1.0,
        "reach_mm": 474.0,
        "weight_kg": 3.8,
        "weight": "3.8 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_RX7,
        "videos": [YT_RX_LIGHT, YT_CES_ARMS],
        "notes_force": (
            "OEM specs (rx71.html): 7 DoF humanoid wrist, 474 mm working radius (incl. force sensor), "
            "1 kg payload, ~3.8 kg net weight. No RX71-titled YouTube — used ultra-lightweight arm + CES arms demos. "
            "Tags corrected from 6-Axis → 7-DoF."
        ),
        "source_note": "realman-robotics.com/en/products/rx71.html Technical Specifications",
    },
    5231: {  # RX75 — no_videos
        "name": "RX75",
        "model_name": "RX75",
        "url": "https://www.realman-robotics.com/en/products/rx75.html",
        "dof": 7,
        "payload_kg": 5.0,
        "reach_mm": 709.0,
        "weight_kg": 8.2,
        "weight": "8.2 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_RX7,
        "videos": [YT_RX_LIGHT, YT_CES_ARMS],
        "notes_force": (
            "OEM specs (rx75.html): 7 DoF, 709 mm working radius, 5 kg payload, 8.2 kg net weight. "
            "No RX75-titled YouTube — used ultra-lightweight arm + CES arms demos."
        ),
        "source_note": "realman-robotics.com/en/products/rx75.html Technical Specifications",
    },
    # Soft typed-spec backfills (already had videos)
    5227: {
        "name": "RM65",
        "model_name": "RM65",
        "url": "https://www.realman-robotics.com/en/products/rm65.html",
        "dof": 6,
        "payload_kg": 5.0,
        "reach_mm": 610.0,
        "weight_kg": 7.2,
        "weight": "7.2 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_RM6,
        "videos": [YT_RM65, YT_ECO_RM_SERIES],
        "notes_force": (
            "OEM specs (rm65.html): 6 DoF, 610 mm working radius, 5 kg payload, 7.2 kg net weight."
        ),
        "source_note": "realman-robotics.com/en/products/rm65.html Technical Specifications",
    },
    5229: {
        "name": "RML63",
        "model_name": "RML63",
        "url": "https://www.realman-robotics.com/en/products/rml63.html",
        "dof": 6,
        "payload_kg": 3.0,
        "reach_mm": 900.0,
        "weight_kg": 10.0,
        "weight": "10 kg",
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": "6-Axis|Industrial Arm|Manufacturing|Pick-and-Place|Stationary|extended reach",
        "videos": [YT_ECO_RM_SERIES, YT_CES_ARMS],
        "notes_force": (
            "EN storefront has no Technical Specifications table — payload/reach/weight from CRM "
            "feature bullets (900 mm / 3 kg / 10 kg) matching ECO63-class long-reach line. "
            "Replaced weak shelf-scan/tea clips with ECO & RM Series + CES arms demos."
        ),
        "source_note": "realman-robotics.com/en/products/rml63.html features (no spec table)",
    },
    5219: {
        "name": "Dual-Arm Lift",
        "model_name": "Dual-Arm Lift",
        "url": "https://www.realman-robotics.com/en/products/dual-arm-lift.html",
        "dof": None,
        "payload_kg": 5.0,  # per arm
        "weight_kg": 157.0,
        "weight": "157 kg",
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_LIFT,
        "videos": [YT_DUAL_LIFT, YT_DUAL_COMPOUND],
        "notes_force": (
            "OEM specs: total ≈157 kg; single-arm payload 5 kg each (Dual RM65-B-V). "
            "payload_kg typed as per-arm 5 kg (not platform mass)."
        ),
        "source_note": "realman-robotics.com/en/products/dual-arm-lift.html",
    },
    5232: {
        "name": "Single-Arm Lift",
        "model_name": "Single-Arm Lift",
        "url": "https://www.realman-robotics.com/en/products/single-arm-lift.html",
        "payload_kg": 5.0,
        "weight_kg": 100.0,
        "weight": "100 kg",
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_SINGLE,
        "videos": [YT_SINGLE_LIFT, YT_CES_ARMS],
        "notes_force": (
            "OEM specs: total ≈100 kg; single-arm payload 5 kg (integrated RM65-B-V)."
        ),
        "source_note": "realman-robotics.com/en/products/single-arm-lift.html",
    },
    5223: {
        "name": "Four-Steer Four-Drive Chassis",
        "model_name": "Four-Steer Four-Drive Chassis",
        "url": "https://www.realman-robotics.com/en/products/four-steer-chassis.html",
        "payload_kg": 80.0,
        "weight_kg": 65.0,
        "weight": "65 kg",
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_CHASSIS,
        "videos": [YT_CES_ARMS, YT_REALBOT_CES],
        "notes_force": (
            "OEM specs: ~65 kg chassis weight, 80 kg rated payload. "
            "Replaced training-center facility tour with CES product-line videos."
        ),
        "source_note": "realman-robotics.com/en/products/four-steer-chassis.html",
    },
    5233: {
        "name": "Two-Wheel Differential Chassis",
        "model_name": "Two-Wheel Differential Chassis",
        "url": "https://www.realman-robotics.com/en/products/dual-wheel-chassis.html",
        "payload_kg": 80.0,
        "weight_kg": 60.0,
        "weight": "60 kg",
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": "Autonomous|Mobile Robot|Wheeled|Education|Research|Data Collection",
        "videos": [YT_CES_ARMS, YT_REALBOT_CES],
        "notes_force": (
            "OEM specs: ~60 kg chassis weight, 80 kg rated payload. "
            "Replaced facility/tour clips with CES product-line videos."
        ),
        "source_note": "realman-robotics.com/en/products/dual-wheel-chassis.html",
    },
    5224: {
        "name": "RealBot-01",
        "model_name": "RealBot-01",
        "url": "https://www.realman-robotics.com/en/products/realbot-humanoid.html",
        "dof": 21,
        "payload_kg": 5.0,
        "weight_kg": 125.0,
        "weight": "125 kg",
        "reach_mm": 2100.0,  # vertical reach
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_HUMAN,
        "videos": [YT_REALBOT, YT_REALBOT_CES],
        "notes_force": (
            "OEM specs: ≈125 kg; 21 active DoF; 5 kg single-arm payload; vertical reach 2100 mm. "
            "reach_mm typed as vertical reach."
        ),
        "source_note": "realman-robotics.com/en/products/realbot-humanoid.html",
    },
    5225: {
        "name": "RealBot-L2",
        "model_name": "RealBot-L2",
        "url": "https://www.realman-robotics.com/en/products/realbot-l2.html",
        "dof": 17,
        "payload_kg": 5.0,
        "weight_kg": 120.0,
        "weight": "120 kg",
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": "Autonomous|Dual Arm|Full-Size|Humanoid|Service Robot|Wheeled",
        "videos": [YT_REALBOT, YT_REALBOT_CES],
        "notes_force": (
            "OEM specs: ≈120 kg; 17 active DoF; 5 kg per arm. "
            "Replaced facility tour with RealBOT factory/CES demos."
        ),
        "source_note": "realman-robotics.com/en/products/realbot-l2.html",
    },
    5226: {
        "name": "RealBot-S2",
        "model_name": "RealBot-S2",
        "url": "https://www.realman-robotics.com/en/products/realbot-s2.html",
        "dof": 20,
        "payload_kg": 5.0,
        "weight_kg": 125.0,
        "weight": "125 kg",
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": "Autonomous|Data Collection|Humanoid|Research|Retail|Wheeled",
        "videos": [YT_REALBOT_CES, YT_REALBOT],
        "notes_force": (
            "OEM specs: ≈125 kg; 20 active DoF; 5 kg per arm."
        ),
        "source_note": "realman-robotics.com/en/products/realbot-s2.html",
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


def build_row(
    robot: dict[str, Any],
    fix: dict[str, Any],
    *,
    oem_image: str | None = None,
    replace_media: bool = False,
) -> dict[str, Any]:
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
    if replace_media and oem_image:
        row["image"] = oem_image
        row["images"] = [oem_image]
    elif fix.get("images"):
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
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            body: dict[str, Any] = {}
            try:
                body = resp.json() if resp.content else {}
            except Exception:
                body = {}
            # Prefer JSON success flag when present (post-2026-07-14 worker returns False on skip).
            success = bool(body.get("success")) if "success" in body else resp.ok
            if resp.ok and success:
                ok += 1
            else:
                fail += 1
                print(
                    f"copy-media fail {rid}: HTTP {resp.status_code} body={body}",
                    flush=True,
                )
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.2)
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Realman company 882 content-queue")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument(
        "--keep-media",
        action="store_true",
        help="Do not replace heroes (default replaces from OEM heroes.json to repair broken CDN)",
    )
    parser.add_argument(
        "--replace-media",
        action="store_true",
        help=argparse.SUPPRESS,  # deprecated alias — replace is now default
    )
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument(
        "--verify-cdn",
        action="store_true",
        help="After apply+copy-media, HTTP-GET verify owned CDN URLs (recommended)",
    )
    args = parser.parse_args()
    do_replace = not args.keep_media

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
        oem = OEM_HEROES.get(rid) or (fix.get("image") or "").strip()
        if do_replace and not oem:
            print(f"ERROR dry-run gate fail {rid}: need OEM hero in heroes.json", file=sys.stderr)
            return 1
        row = build_row(robot, fix, oem_image=oem, replace_media=do_replace)
        if len(row.get("features") or "") < 40:
            print(f"ERROR dry-run gate fail {rid}: need features", file=sys.stderr)
            return 1
        if not row.get("video_urls"):
            print(f"ERROR dry-run gate fail {rid}: need videos", file=sys.stderr)
            return 1
        if not (row.get("tags") or ""):
            print(f"ERROR dry-run gate fail {rid}: need tags", file=sys.stderr)
            return 1
        if do_replace and not (row.get("image") or ""):
            print(f"ERROR dry-run gate fail {rid}: need image", file=sys.stderr)
            return 1
        targets.append(
            {
                "id": rid,
                "name": robot.get("name"),
                "replace_media": do_replace,
                "image": (row.get("image") or "")[:100],
                "features_len": len(row.get("features") or ""),
                "vids": len(row.get("video_urls") or []),
                "payload": row.get("payload_kg"),
                "row": row,
            }
        )
        print(
            f"  {rid} {robot.get('name')}: "
            f"img={'OEM' if do_replace else 'keep'} "
            f"vids={len(row.get('video_urls') or [])} "
            f"payload={row.get('payload_kg')} reach={row.get('reach_mm')} dof={row.get('dof')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "realman-fix-preview.json"
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
        print(f"Preview: {preview}. Re-run with --apply")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="realman-fix-"))
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
        need = [t["id"] for t in targets]
        ok, fail = trigger_copy_media(need)
        copy_stats = {"ok": ok, "fail": fail, "ids": need}
        print(f"copy-media ok={ok} fail={fail}")
        if fail:
            all_ok = False

    cdn_verify = None
    if args.verify_cdn:
        from verify_cdn_images import main as verify_main

        old_argv = sys.argv
        try:
            sys.argv = ["verify_cdn_images.py", "--company-id", str(COMPANY_ID)]
            if args.only:
                sys.argv = [
                    "verify_cdn_images.py",
                    "--ids",
                    *[str(i) for i in args.only],
                ]
            rc = verify_main()
        finally:
            sys.argv = old_argv
        cdn_verify = {"ok": rc == 0, "exit": rc}
        if rc != 0:
            all_ok = False
            print("CDN verify FAILED — do not trust copy-media OK alone", file=sys.stderr)

    if args.mark_done and all_ok:
        done_path = _RESEARCH_DIR / "state" / "content_queue_done.json"
        done: dict[str, Any] = {}
        if done_path.is_file():
            done = json.loads(done_path.read_text(encoding="utf-8"))
        ids: set[int] = set()
        for key in ("companies", "company_ids"):
            for x in done.get(key) or []:
                try:
                    ids.add(int(x))
                except (TypeError, ValueError):
                    continue
        ids.add(COMPANY_ID)
        merged = sorted(ids)
        done["companies"] = merged
        done["company_ids"] = merged
        done.setdefault("notes", {})[str(COMPANY_ID)] = (
            "2026-07-14 Realman: videos/specs + CDN repair (OEM heroes, HTTP-verified)"
        )
        done_path.parent.mkdir(parents=True, exist_ok=True)
        done_path.write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
        print(f"marked done company {COMPANY_ID} (n={len(merged)})")

    out = {
        "ok": all_ok,
        **totals,
        "imported": imported,
        "copy_media": copy_stats,
        "cdn_verify": cdn_verify,
    }
    (_RESEARCH_DIR / "staging" / "reports" / "realman-fix-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
