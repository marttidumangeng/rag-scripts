"""Backfill RealMan Robotics (company 1473) content-queue gaps.

Duplicate OEM shell vs company 882 (Realman Beijing). Eleven pending arms are
Standard / Six-Axis Force / Vision variants of ECO62/65, RM65/75, RML63, RX75 —
all missing images, tags, videos; features are tag-like fragments.

Heroes: OEM `/prop/products-images/...` Unicode paths (标准版 / 六维力版 / 视觉版).
Specs/videos/tags mirrored from fix_realman_robots.py (882) + rx75.html variant notes.
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

COMPANY_ID = 1473
COMPANY_SLUG = "realman-robotics"
COMPANY_NAME = "RealMan Robotics"
COMPANY_WEBSITE = "https://www.realman-robotics.com/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

_PROP = "https://www.realman-robotics.com/prop/products-images"

# Title-verified YouTube (same set as company 882 fixer).
YT_ECO_RM_SERIES = "https://www.youtube.com/watch?v=2ecQGCLOY3Q"
YT_ECO65 = "https://www.youtube.com/watch?v=LvXvDEfAQaM"
YT_RM75 = "https://www.youtube.com/watch?v=RLu4TGtKXu4"
YT_RM75_FLAG = "https://www.youtube.com/watch?v=KPAI3PJAgTs"
YT_RM65 = "https://www.youtube.com/watch?v=fMZ5sn5irpo"
YT_RX_LIGHT = "https://www.youtube.com/watch?v=CM9b4EGjb_E"
YT_CES_ARMS = "https://www.youtube.com/watch?v=LF96dkzeNrY"

TAGS_ECO = "6-Axis|Collaborative Robot|Lightweight|Industrial Arm|Pick-and-Place|Education"
TAGS_RM6 = "6-Axis|Collaborative Robot|Lightweight|Industrial|Manufacturing|Stationary"
TAGS_RM7 = "7-DoF|Collaborative Robot|Lightweight|Industrial Arm|Precision|Stationary"
TAGS_RX7 = "7-DoF|Collaborative Robot|Humanoid|Lightweight|Industrial Arm|Manipulation"
TAGS_FORCE = "Force Sensing|Collaborative Robot|Industrial Arm|Precision|Manufacturing"
TAGS_VISION = "7-DoF|Vision|Collaborative Robot|Humanoid|Lightweight|Manipulation"

ROBOT_DATA: dict[str, dict[str, Any]] = {
    "RM65 Standard": {
        "url": "https://www.realman-robotics.com/en/products/rm65.html",
        "image": f"{_PROP}/机械臂/RM系列/RM65/RM65-标准版/65-.213.png",
        "description": (
            "RealMan RM65 Standard is a 6-DoF ultra-lightweight collaborative arm "
            "for lab automation, inspection, and light industrial pick-and-place."
        ),
        "features": (
            "Variant: Standard (no integrated six-axis force sensor tip). "
            "6 DoF; 5 kg payload; 610 mm working radius; ~7.2 kg net weight. "
            "Ultra-lightweight humanoid-style joints; drag-teach and collaborative safety. "
            "Tool flange with status indicator; dual-arm system ready."
        ),
        "dof": 6,
        "payload_kg": 5.0,
        "reach_mm": 610.0,
        "weight_kg": 7.2,
        "weight": "7.2 kg",
        "tags": TAGS_RM6,
        "videos": [YT_RM65, YT_ECO_RM_SERIES],
        "source_note": (
            "Specs: realman-robotics.com/en/products/rm65.html Technical Specifications. "
            "Hero: OEM RM65-标准版/65-.213.png."
        ),
    },
    "RM65 Six-Axis Force": {
        "url": "https://www.realman-robotics.com/en/products/rm65.html",
        "image": f"{_PROP}/机械臂/RM系列/RM65/RM65-六维力版/65-.922.png",
        "description": (
            "RealMan RM65 Six-Axis Force adds an integrated six-axis force/torque tip "
            "on the same 6-DoF ultra-lightweight RM65 collaborative platform."
        ),
        "features": (
            "Variant: Six-Axis Force (integrated F/T sensor tip). "
            "Base platform: 6 DoF; 5 kg payload; 610 mm working radius; ~7.2 kg net weight. "
            "Integrated force sensing for compliant assembly, polishing, and contact tasks. "
            "Shares RM65 Standard kinematics; force tip selected from OEM 六维力版 gallery."
        ),
        "dof": 6,
        "payload_kg": 5.0,
        "reach_mm": 610.0,
        "weight_kg": 7.2,
        "weight": "7.2 kg",
        "tags": f"{TAGS_FORCE}|6-Axis|Lightweight",
        "videos": [YT_RM65, YT_ECO_RM_SERIES],
        "source_note": (
            "Specs base table: rm65.html. Hero: OEM RM65-六维力版/65-.922.png "
            "(folder-verified; vertical render may share art with RM75 force still)."
        ),
    },
    "RM75 Standard": {
        "url": "https://www.realman-robotics.com/en/products/rm75.html",
        "image": f"{_PROP}/机械臂/RM系列/RM75/RM75-标准版/65-.217.png",
        "description": (
            "RealMan RM75 Standard is a 7-DoF ultra-lightweight collaborative arm "
            "with redundant degrees of freedom for complex manipulation."
        ),
        "features": (
            "Variant: Standard. "
            "7 DoF redundancy; 5 kg payload; 610 mm working radius; ~7.8 kg net weight. "
            "Ultra-lightweight flagship RM-series arm; humanoid wrist flexibility for dual-arm cells."
        ),
        "dof": 7,
        "payload_kg": 5.0,
        "reach_mm": 610.0,
        "weight_kg": 7.8,
        "weight": "7.8 kg",
        "tags": TAGS_RM7,
        "videos": [YT_RM75, YT_RM75_FLAG],
        "source_note": (
            "Specs: realman-robotics.com/en/products/rm75.html. "
            "Hero: OEM RM75-标准版/65-.217.png."
        ),
    },
    "RM75 Six-Axis Force": {
        "url": "https://www.realman-robotics.com/en/products/rm75.html",
        "image": f"{_PROP}/机械臂/RM系列/RM75/RM75-六维力版/65-.922.png",
        "description": (
            "RealMan RM75 Six-Axis Force is the 7-DoF RM75 platform with integrated "
            "six-axis force sensing at the tool tip."
        ),
        "features": (
            "Variant: Six-Axis Force. "
            "Base platform: 7 DoF; 5 kg payload; 610 mm working radius; ~7.8 kg net weight. "
            "Integrated F/T tip for force-controlled assembly and surface contact. "
            "Hero from OEM RM75-六维力版 gallery."
        ),
        "dof": 7,
        "payload_kg": 5.0,
        "reach_mm": 610.0,
        "weight_kg": 7.8,
        "weight": "7.8 kg",
        "tags": f"{TAGS_FORCE}|7-DoF|Lightweight",
        "videos": [YT_RM75, YT_RM75_FLAG],
        "source_note": (
            "Specs: rm75.html. Hero: OEM RM75-六维力版/65-.922.png "
            "(byte-identical to RM65 force still on CDN — same OEM vertical render)."
        ),
    },
    "RML63 Standard": {
        "url": "https://www.realman-robotics.com/en/products/rml63.html",
        "image": f"{_PROP}/机械臂/RML系列/RML63/RML63-标准版/63.120.png",
        "description": (
            "RealMan RML63 Standard is a long-reach 6-DoF collaborative arm "
            "for expanded workspace pick-and-place and inspection."
        ),
        "features": (
            "Variant: Standard. "
            "6 DoF long-reach line; ~3 kg payload; ~900 mm reach; ~10 kg class mass "
            "(EN page has no full Technical Specifications table — values from CRM/OEM feature bullets "
            "matching ECO63-class long reach). "
            "Expanded workspace relative to RM65/ECO65."
        ),
        "dof": 6,
        "payload_kg": 3.0,
        "reach_mm": 900.0,
        "weight_kg": 10.0,
        "weight": "10 kg",
        "tags": "6-Axis|Industrial Arm|Manufacturing|Pick-and-Place|Stationary|Lightweight",
        "videos": [YT_ECO_RM_SERIES, YT_CES_ARMS],
        "source_note": (
            "rml63.html features (no EN spec table); soft typed specs per company-882 lesson. "
            "Hero: OEM RML63-标准版/63.120.png."
        ),
    },
    "RML63 Six-Axis Force": {
        "url": "https://www.realman-robotics.com/en/products/rml63.html",
        "image": f"{_PROP}/机械臂/RML系列/RML63/RML63-六维力版/63.910.png",
        "description": (
            "RealMan RML63 Six-Axis Force is the long-reach RML63 with integrated "
            "six-axis force sensing."
        ),
        "features": (
            "Variant: Six-Axis Force. "
            "Base platform: 6 DoF; ~3 kg payload; ~900 mm reach; ~10 kg class. "
            "Integrated F/T tip for compliant contact at extended reach. "
            "Hero from OEM RML63-六维力版 gallery."
        ),
        "dof": 6,
        "payload_kg": 3.0,
        "reach_mm": 900.0,
        "weight_kg": 10.0,
        "weight": "10 kg",
        "tags": f"{TAGS_FORCE}|6-Axis|Pick-and-Place",
        "videos": [YT_ECO_RM_SERIES, YT_CES_ARMS],
        "source_note": (
            "Soft typed specs as RML63 Standard. Hero: OEM RML63-六维力版/63.910.png."
        ),
    },
    "ECO65 Standard": {
        "url": "https://www.realman-robotics.com/en/products/eco65.html",
        "image": f"{_PROP}/机械臂/ECO系列/ECO65/ECO65-标准版/正视图-标准版.png",
        "description": (
            "RealMan ECO65 Standard is a cost-effective 6-DoF collaborative arm "
            "with full mechanical brakes for education and light factory automation."
        ),
        "features": (
            "Variant: Standard. "
            "6 DoF; 5 kg payload; 610 mm working radius; 7.8 kg net weight. "
            "Full mechanical brakes; collaborative design; orange-accent ECO styling."
        ),
        "dof": 6,
        "payload_kg": 5.0,
        "reach_mm": 610.0,
        "weight_kg": 7.8,
        "weight": "7.8 kg",
        "tags": "6-Axis|Assembly|Collaborative Robot|Factory Automation|Industrial Arm|Lightweight",
        "videos": [YT_ECO65, YT_ECO_RM_SERIES],
        "source_note": (
            "Specs: eco65.html Technical Specifications. "
            "Hero: OEM ECO65-标准版/正视图-标准版.png."
        ),
    },
    "ECO65 Six-Axis Force": {
        "url": "https://www.realman-robotics.com/en/products/eco65.html",
        "image": f"{_PROP}/机械臂/ECO系列/ECO65/ECO65-六维力版/正视图-6维力版.png",
        "description": (
            "RealMan ECO65 Six-Axis Force adds integrated six-axis force sensing "
            "to the ECO65 collaborative platform."
        ),
        "features": (
            "Variant: Six-Axis Force. "
            "Base platform: 6 DoF; 5 kg payload; 610 mm working radius; 7.8 kg net weight. "
            "Full mechanical brakes plus integrated F/T tip. "
            "Hero from OEM ECO65-六维力版 front view."
        ),
        "dof": 6,
        "payload_kg": 5.0,
        "reach_mm": 610.0,
        "weight_kg": 7.8,
        "weight": "7.8 kg",
        "tags": f"{TAGS_FORCE}|6-Axis|Factory Automation|Lightweight",
        "videos": [YT_ECO65, YT_ECO_RM_SERIES],
        "source_note": (
            "Specs: eco65.html. Hero: OEM ECO65-六维力版/正视图-6维力版.png."
        ),
    },
    "ECO62 Standard": {
        "url": "https://www.realman-robotics.com/en/products/eco62.html",
        "image": (
            f"{_PROP}/机械臂/ECO系列/ECO62/ECO62-标准版/"
            "20240918-结构渲染.bip.669.png"
        ),
        "description": (
            "RealMan ECO62 Standard is an ultra-compact 6-DoF collaborative arm "
            "for low payload education and bench automation."
        ),
        "features": (
            "Variant: Standard. "
            "6 DoF; 1 kg payload; 355 mm working radius; 3.3 kg net weight. "
            "Ultra-compact, low power draw; ECO-series orange joint accents."
        ),
        "dof": 6,
        "payload_kg": 1.0,
        "reach_mm": 355.0,
        "weight_kg": 3.3,
        "weight": "3.3 kg",
        "tags": TAGS_ECO,
        "videos": [YT_ECO_RM_SERIES, YT_ECO65],
        "source_note": (
            "Specs: eco62.html Technical Specifications. "
            "Hero: OEM ECO62-标准版 structure render. "
            "No ECO62-titled YouTube — used ECO & RM Series + ECO65 sibling."
        ),
    },
    "RX75 Standard": {
        "url": "https://www.realman-robotics.com/en/products/rx75.html",
        "image": f"{_PROP}/机械臂/RX系列/RX75-标准版/2.185.png",
        "description": (
            "RealMan RX75 Standard is a 7-DoF humanoid-wrist collaborative arm "
            "with built-in six-axis force sensing and dual-arm-ready design."
        ),
        "features": (
            "Variant: Standard (709 mm reach class). "
            "7-DoF humanoid wrist; integrated six-axis force (200 N / 7 N·m class, 0.5%FS per OEM). "
            "5 kg payload; 709 mm working radius; 8.2 kg net weight. "
            "Dual-arm ready side-mount geometry. "
            "Hero: OEM RX75-标准版 dual-arm pose still."
        ),
        "dof": 7,
        "payload_kg": 5.0,
        "reach_mm": 709.0,
        "weight_kg": 8.2,
        "weight": "8.2 kg",
        "tags": TAGS_RX7,
        "videos": [YT_RX_LIGHT, YT_CES_ARMS],
        "source_note": (
            "Specs: rx75.html (Standard 709 mm · 8.2 kg). "
            "Hero: OEM RX75-标准版/2.185.png. "
            "No RX75-titled YouTube — ultra-lightweight arm + CES demos."
        ),
    },
    "RX75 Vision": {
        "url": "https://www.realman-robotics.com/en/products/rx75.html",
        "image": f"{_PROP}/机械臂/RX系列/RX75-视觉版/带视觉.png",
        "description": (
            "RealMan RX75 Vision is the RX75 platform with Intel RealSense D405 "
            "end-effector vision and extended reach versus Standard."
        ),
        "features": (
            "Variant: Vision (Intel RealSense D405 at end-effector). "
            "7-DoF humanoid wrist; integrated six-axis force on both RX75 versions. "
            "5 kg payload; 732 mm working radius; 8.4 kg net weight (OEM Vision row). "
            "Vision-ready depth perception for intelligent pick and inspection. "
            "Hero: OEM RX75-视觉版/带视觉.png."
        ),
        "dof": 7,
        "payload_kg": 5.0,
        "reach_mm": 732.0,
        "weight_kg": 8.4,
        "weight": "8.4 kg",
        "tags": TAGS_VISION,
        "videos": [YT_RX_LIGHT, YT_CES_ARMS],
        "source_note": (
            "Specs: rx75.html Vision row (D405 · 732 mm · 8.4 kg). "
            "Hero: OEM RX75-视觉版/带视觉.png."
        ),
    },
}


def verify_image(url: str) -> bool:
    try:
        resp = requests.head(url, headers=HEADERS, timeout=25, allow_redirects=True)
        if resp.status_code != 200:
            resp = requests.get(url, headers=HEADERS, timeout=45, stream=True)
            resp.close()
        return resp.status_code == 200
    except requests.RequestException:
        return False


def build_row(robot: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    hero = (data.get("image") or "").strip()
    if not hero or not verify_image(hero):
        raise RuntimeError(f"hero unavailable for {robot.get('name')}: {hero}")
    videos = enrich_video_list(list(data.get("videos") or []))
    row: dict[str, Any] = {
        "name": robot["name"],
        "model_name": robot.get("model_name") or robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CN",
        "description": data["description"],
        "purpose": data["description"],
        "features": data["features"],
        "url": data["url"],
        "image": hero,
        "images": [hero],
        "video_urls": videos,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": data.get("tags") or "",
        "research_notes": data.get("source_note") or "",
        "source_locale": "en",
        "sources": [
            {
                "url": data["url"],
                "type": "website",
                "title": f"RealMan {robot['name']} product page",
            },
            {
                "url": COMPANY_WEBSITE,
                "type": "website",
                "title": "RealMan Robotics",
            },
        ],
    }
    for key in ("dof", "payload_kg", "reach_mm", "weight_kg", "weight"):
        if data.get(key) is not None and data.get(key) != "":
            row[key] = data[key]
    return row


def patch_company_website(client: ResearchApiClient) -> None:
    try:
        co = client._get(f"companies/{COMPANY_ID}/")
    except Exception as exc:
        print(f"company fetch fail: {exc}")
        return
    if (co.get("website") or "").strip():
        print(f"company website already set: {co.get('website')}")
        return
    try:
        client.patch_company(COMPANY_ID, {"website": COMPANY_WEBSITE})
        print(f"company website -> {COMPANY_WEBSITE}")
    except Exception as exc:
        try:
            client._patch(f"companies/{COMPANY_ID}/", {"website": COMPANY_WEBSITE})
            print(f"company website -> {COMPANY_WEBSITE}")
        except Exception as exc2:
            print(f"company website patch skipped: {exc}; {exc2}")


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("WARN: missing INTERNAL_API_SECRET or API base for copy-media")
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
                print(f"copy-media OK {rid}")
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code} body={body}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.2)
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix RealMan company 1473 content-queue")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--patch-company", action="store_true")
    parser.add_argument("--only", type=str, nargs="*")
    args = parser.parse_args()

    client = ResearchApiClient()
    if args.patch_company or args.apply:
        patch_company_website(client)

    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    ]
    print(f"targets: {len(robots)}")

    plan: list[dict[str, Any]] = []
    staging: dict[int, dict[str, Any]] = {}
    for robot in robots:
        name = robot["name"]
        if args.only and name not in args.only and str(robot["id"]) not in (args.only or []):
            continue
        data = ROBOT_DATA.get(name)
        if not data:
            print(f"SKIP {robot['id']} {name}: no curated data")
            continue
        try:
            row = build_row(robot, data)
        except RuntimeError as exc:
            print(f"ERROR {robot['id']} {name}: {exc}", file=sys.stderr)
            return 1
        staging[int(robot["id"])] = row
        plan.append(
            {
                "id": robot["id"],
                "name": name,
                "url": row.get("url"),
                "image": bool(row.get("image")),
                "image_url": row.get("image"),
                "features_len": len(row.get("features") or ""),
                "videos": len(row.get("video_urls") or []),
                "tags": row.get("tags"),
                "dof": row.get("dof"),
                "payload_kg": row.get("payload_kg"),
                "reach_mm": row.get("reach_mm"),
            }
        )
        print(
            f"{name}: img=yes feat={len(row.get('features') or '')} "
            f"vids={len(row.get('video_urls') or [])} "
            f"dof={row.get('dof')} payload={row.get('payload_kg')} reach={row.get('reach_mm')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "realman-1473-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if any(
        not p["image"] or p["features_len"] < 40 or not p["videos"] or not p["tags"]
        for p in plan
    ):
        print("ERROR: incomplete enrichment", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="realman-1473-"))
    imported: list[int] = []
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0}
    all_ok = True
    for item in plan:
        rid = int(item["id"])
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
        print(f"IMPORT OK {rid} {row['name']}")

    print(json.dumps({"ok": all_ok, **totals, "imported": imported}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
