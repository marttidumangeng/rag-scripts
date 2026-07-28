"""Backfill EVE Energy (company 975) battery cells: photo (50E), videos, tags.

Preserves existing descriptions/features/weights from EVEMALL product pages.
resource.evemall.com images require a Referer (host Referer works for server copy-media).
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
from urllib.parse import urlparse

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

COMPANY_ID = 975
COMPANY_SLUG = "eve-energy-co-ltd"
COMPANY_NAME = "EVE Energy Co.  Ltd."
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
}

# Exact TagCatalog names.
TAGS_BY_NAME: dict[str, str] = {
    "Cylindrical NCM Cell 21700 50E": (
        "Electric|Industrial|Manufacturing|Modular|Portable|Consumer|"
        "Industrial Automation|Factory"
    ),
    "Cylindrical NCM Cell 21700 50PL": (
        "Electric|Industrial|Manufacturing|Modular|Consumer|Portable|"
        "Industrial Automation|Factory"
    ),
    "LF105 Prismatic LiFePO4 Battery Cell": (
        "Electric|Industrial|Manufacturing|Modular|Factory|"
        "Industrial Automation|high-payload|Portable"
    ),
}

ROBOT_DATA: dict[str, dict[str, Any]] = {
    "Cylindrical NCM Cell 21700 50E": {
        "url": "https://www.evemall.eu/consumer-battery/cylindrical-ncm-cell/21700-50e",
        "image": "https://resource.evemall.com/Public/Uploads/uploadfile2/images/20250114/2170050E.jpg",
        "images": [
            "https://resource.evemall.com/Public/Uploads/uploadfile2/images/20250114/2170050E.jpg",
            "https://resource.evemall.com/Public/Uploads/uploadfile2/images/20250114/2170050E2.jpg",
        ],
        "description": (
            "EVE's 21700 50E cylindrical NCM cell delivers 3.65V and 5000mAh across 1000 cycles, "
            "supporting electric vehicles, robotics battery packs, and portable power stations."
        ),
        "purpose": (
            "To provide high-performance power for electric vehicles, robotics, and portable energy storage."
        ),
        "features": (
            "5000mAh Nominal Capacity,3.65V Nominal Voltage,1000 Nominal Cycles,"
            "264 Wh/kg Energy Density,72g Max Weight,≤20 mΩ AC Internal Resistance"
        ),
        "weight_kg": 0.072,
        "dimensions_mm": "21x70",
        "videos": [
            "https://www.youtube.com/watch?v=4mVK9eWz5BE",
            "https://www.youtube.com/watch?v=y6rl-sFWOqw",
        ],
        "source_note": (
            "Specs/features from evemall.eu 21700-50e. Hero: official EVE NCM 21700 50E product render "
            "on resource.evemall.com. YouTube: 50E portable ESS cell + INR21700-50E discharge demo."
        ),
    },
    "Cylindrical NCM Cell 21700 50PL": {
        "url": "https://www.evemall.eu/consumer-battery/cylindrical-ncm-cell/21700-50pl",
        "image": "https://resource.evemall.com/Public/Uploads/uploadfile2/images/20251119/50PL1-176353127545.jpg",
        "images": [
            "https://resource.evemall.com/Public/Uploads/uploadfile2/images/20251119/50PL1-176353127545.jpg",
            "https://resource.evemall.com/Public/Uploads/uploadfile2/images/20251119/50PL3-176353128756.jpg",
        ],
        "description": (
            "EVE's 21700 50PL cylindrical NCM cell delivers 3.6V and 5000mAh capacity, "
            "supporting power tools and gardening equipment with full-rate battery output."
        ),
        "purpose": "To power various consumer and industrial tools requiring high-rate discharge.",
        "features": (
            "5000mAh Nominal Capacity,3.60V Nominal Voltage,400 Nominal Cycles,"
            "264 Wh/kg Energy Density,68g Max Weight,≤5 mΩ AC Internal Resistance. "
            "High-rate / tabless design; EVEMALL cites continuous discharge up to 70A for power-tool duty."
        ),
        "weight_kg": 0.068,
        "dimensions_mm": "21x70",
        "videos": [
            "https://www.youtube.com/watch?v=VdcpMhxh8Rg",
            "https://www.youtube.com/watch?v=cDJB3hhDVOE",
        ],
        "source_note": (
            "Specs from evemall.eu 21700-50pl (incl. high-rate / up to 70A continuous discharge claim). "
            "Hero: official EVE INR21700/50PL wrap photo. YouTube: EVE 21700 50PL + EVE factory line overview."
        ),
    },
    "LF105 Prismatic LiFePO4 Battery Cell": {
        "url": "https://www.evemall.eu/power-battery/prismatic-lfp-cell/lf105",
        "image": "https://resource.evemall.com/Public/Uploads/uploadfile2/images/20250124/LF1052.jpg",
        "images": [
            "https://resource.evemall.com/Public/Uploads/uploadfile2/images/20250124/LF1052.jpg",
            "https://resource.evemall.com/Public/Uploads/uploadfile2/images/20250423/LF105LFPyingwen-174539943524.jpg",
        ],
        "description": (
            "EVE Energy's LF105 delivers 3.2V and 105Ah capacity in a prismatic LiFePO4 cell "
            "suited for utility ESS, UPS, marine, and engineering machinery applications."
        ),
        "purpose": (
            "To provide reliable power for various energy storage and heavy-duty applications."
        ),
        "features": (
            "105Ah Nominal Capacity,3.20V Nominal Voltage,4000 Nominal Cycles,"
            "1980±60g Weight,130.3x36.3x200.5mm Size,0.5C/0.5C Charge/Discharge Multiplier. "
            "Applications cited on EVEMALL: residential/commercial ESS, telecom ESS, AGV, "
            "golf cart, forklift, marine, bus."
        ),
        "weight_kg": 1.98,
        "dimensions_mm": "130.3x36.3x200.5",
        "videos": [
            "https://www.youtube.com/watch?v=NAYCI90bx00",
            "https://www.youtube.com/watch?v=NzhT183tRf0",
        ],
        "source_note": (
            "Specs/features from evemall.eu lf105 (105Ah / 3.2V / 4000 cycles / 130.3×36.3×200.5 mm). "
            "Hero: official EVE LF105 prismatic cell photo. YouTube: LF105 Grade A review + CATL vs EVE 105Ah comparison."
        ),
    },
}


def _image_headers(url: str) -> dict[str, str]:
    headers = dict(HEADERS)
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
    return headers


def verify_image(url: str) -> bool:
    try:
        resp = requests.head(url, headers=_image_headers(url), timeout=20, allow_redirects=True)
        if resp.status_code in (403, 405) or "image" not in (resp.headers.get("content-type") or "").lower():
            resp = requests.get(url, headers=_image_headers(url), timeout=30, stream=True)
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
        "manufacturer_country_code": "CN",
        "description": data["description"],
        "purpose": data.get("purpose") or data["description"],
        "features": data["features"],
        "url": data["url"],
        "image": hero,
        "images": images,
        "video_urls": videos,
        "movement_type_keys": "stationary",
        "category_slugs": "service-robots",
        "sub_category_slug": "industrial",
        "weight_kg": data.get("weight_kg"),
        "dimensions_mm": data.get("dimensions_mm") or "",
        "tags": TAGS_BY_NAME.get(robot["name"]) or "Industrial|Manufacturing|Electric|Modular",
        "sources": [{"url": data["url"], "type": "website", "title": robot["name"]}],
        "research_notes": data.get("source_note") or "EVE Energy cell enrichment.",
    }
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix EVE Energy battery cells for company 975")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") != "published"
    ]
    print(f"targets: {len(robots)}")

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
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
        })
        print(
            f"{robot['name']}: img={'yes' if row.get('image') else 'no'} "
            f"feat={len(row.get('features') or '')} "
            f"vids={len(row.get('video_urls') or [])} tags={bool(row.get('tags'))}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "eve-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if any(not p["image"] or not p["features_len"] or not p["videos"] or not p["tags"] for p in plan):
        print("ERROR: incomplete enrichment", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="eve-fix-"))
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
