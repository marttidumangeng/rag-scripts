"""Backfill Jaten Robot (company 1461) pending_review robots.

OEM site: https://jaten-robotics.com/ — Guangdong Jaten Robot & Automation Co., Ltd.

Hard lessons:
- Many CRM detail.html?id= values were reassigned: page title no longer matches robot name.
- Resolve URLs via AGV list SSR cards (`onclick=onDetail('ID')` + cardTitle).
- Five CRM models (-335-MG0 payload ladder except R2SDM1500, plus MN100-164 and
  SDM1000/2000/3000-D228) have ZERO hits on the live catalog / Serper — skip until
  official pages resurface (do not invent heroes or specs).
- OEM AGV-31-MC500 detail hero is a tiny corrupted JPEG; prefer Red Dot award photo
  or distributor still labeled "31". Prefer OEM upload heroes when healthy.
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

COMPANY_ID = 1461
COMPANY_SLUG = "jaten-robot"
COMPANY_NAME = "Jaten Robot Co., Ltd."
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

TAGS_LIFT = (
    "AGV|AMR|Autonomous Mobile Robot|Warehouse Automation|Logistics|"
    "Intralogistics|Material Handling|Wheeled|Industrial|Autonomous"
)
TAGS_TOW = (
    "AGV|AMR|Autonomous Mobile Robot|Warehouse Automation|Logistics|"
    "Intralogistics|Material Handling|Wheeled|Industrial|Autonomous"
)
TAGS_PIGGY = (
    "AGV|AMR|Autonomous Mobile Robot|Warehouse Automation|Logistics|"
    "Intralogistics|Material Handling|Wheeled|Industrial"
)

# Curated Jaten demos (oEmbed titles reference Jaten / factory AGV). Reject competitor clips.
JATEN_VIDEOS = [
    "https://www.youtube.com/watch?v=ZUCj8KkxOkU",  # Outdoor handling AGV
    "https://www.youtube.com/watch?v=xL6YiRfujbA",  # Jaten AGVs library books
    "https://www.youtube.com/watch?v=uIgpMO-F6CM",  # Factory AGV
]

ROBOT_DATA: dict[str, dict[str, Any]] = {
    "R2SDM1500-335-MG0": {
        "url": "https://jaten-robotics.com/index/Agv/detail.html?id=1001025",
        "image": "https://jaten-robotics.com/upload/20240711/4f174e697112a8527018b5717d4cf960.png",
        "images": [
            "https://jaten-robotics.com/upload/20240711/4f174e697112a8527018b5717d4cf960.png",
        ],
        "description": (
            "R2SDM1500-335-MG0 is Jaten's composite-navigation under-ride AGV for "
            "warehousing and automotive logistics: bi-directional travel, rotate-in-place, "
            "online rearward charging, and lifting/carrying loads up to 1500 kg."
        ),
        "features": (
            "Navigation: QR code + natural (composite) navigation. "
            "Delivery mode: carrying and lifting. "
            "Rated load: 1500 kg. "
            "Dimensions (L x W x H): 1190 x 860 x 280 mm. "
            "Speed: ≤0.8 m/s. Climbing ability: ≤2%. "
            "Lifting height: ≤60 mm. Turning: rotate in place. "
            "Travel: forward, backward, turn. "
            "Battery: 48 V, 45 Ah. Charging: online (rear/back charging). "
            "Application: warehousing, automobile factories, and similar indoor logistics ≤1500 kg."
        ),
        "payload_kg": 1500.0,
        "dimensions_mm": "1190 x 860 x 280",
        "videos": JATEN_VIDEOS,
        "tags": TAGS_LIFT,
        "source_note": (
            "EN PDP + AGV list card id=1001025 on jaten-robotics.com "
            "(specs: navigation, 1500 kg, L1190xW860xH280 mm, ≤0.8 m/s, 48V/45Ah, rear online charge). "
            "Hero: OEM upload 20240711/4f174e69…png (visually verified under-ride AMR)."
        ),
    },
    "SDM300-339-MGD": {
        "url": "https://jaten-robotics.com/index/Agv/detail.html?id=1001026",
        "image": "https://jaten-robotics.com/upload/20240711/6983ebaa9021919cd9ce2cf0a1dd7716.png",
        "images": [
            "https://jaten-robotics.com/upload/20240711/6983ebaa9021919cd9ce2cf0a1dd7716.png",
        ],
        "description": (
            "SDM300-339-MGD is Jaten's backpack lifting AGV with QR + natural composite "
            "navigation, unidirectional travel with in-place rotation, online charging, "
            "and a 300 kg rated load for light manufacturing and electronics logistics."
        ),
        "features": (
            "Navigation: QR code + natural navigation. "
            "Delivery mode: carrying and lifting (backpack). "
            "Rated load: 300 kg. "
            "Dimensions (L x W x H): 800 x 545 x 300 mm. "
            "Speed: ≤1 m/s. Climbing ability: ≤2%. "
            "Lifting height: ≤60 mm. Turning: rotate in place. "
            "Travel: forward, turn (unidirectional operation). "
            "Battery: 48 V, 24 Ah. Charging: online. "
            "Application: warehousing, light manufacturing, electronics factories ≤300 kg."
        ),
        "payload_kg": 300.0,
        "dimensions_mm": "800 x 545 x 300",
        "videos": JATEN_VIDEOS,
        "tags": TAGS_LIFT,
        "source_note": (
            "EN PDP + list card id=1001026 on jaten-robotics.com. "
            "Hero: OEM upload 20240711/6983ebaa…png (JATEN-branded chassis, visually verified)."
        ),
    },
    "MN30-164": {
        "url": "https://jaten-robotics.com/index/Agv/detail.html?id=1000003",
        "image": "https://jaten-robotics.com/upload/20220319/9c5b78baba4908f79223c4f36bd467d3.jpg",
        "images": [
            "https://jaten-robotics.com/upload/20220319/9c5b78baba4908f79223c4f36bd467d3.jpg",
            "https://weber.ru/upload/iblock/5c7/rukryo1hewr91dtikkjrlf6uwzwz2ssm/MN30_164-_30kg_.png",
        ],
        "description": (
            "MN30-164 is Jaten's compact magnetic-navigation piggyback AGV for light "
            "indoor material moves, with a 30 kg rated load inside a 660 x 430 x 200 mm footprint."
        ),
        "features": (
            "Navigation: magnetic navigation. "
            "Delivery mode: piggyback. "
            "Rated load: 30 kg. "
            "Dimensions (L x W x H): 660 x 430 x 200 mm. "
            "Form factor: compact wheeled chassis for light piggyback transport."
        ),
        "payload_kg": 30.0,
        "dimensions_mm": "660 x 430 x 200",
        "videos": JATEN_VIDEOS,
        "tags": TAGS_PIGGY,
        "source_note": (
            "List/detail id=1000003 on jaten-robotics.com (magnetic/piggyback/30 kg/L660xW430xH200). "
            "Primary hero: OEM cardImg upload; secondary distributor still from weber.ru MN30 page."
        ),
    },
    "AGV-31-MC500": {
        "url": "https://jaten-robotics.com/index/Agv/detail.html?id=1000002",
        "image": "https://www.red-dot.org/fileadmin/user_upload/projects_pim/2016/PD/24-05527-2016PD-1.jpg",
        "images": [
            "https://www.red-dot.org/fileadmin/user_upload/projects_pim/2016/PD/24-05527-2016PD-1.jpg",
            "https://weber.ru/upload/iblock/efa/lfmkjcumkdzctqgfeolxdgts6kdhvucm/AGV_31_MC500-_500kg_.jpg",
        ],
        "description": (
            "AGV-31-MC500 (White Dolphin) is Jaten's magnetic-navigation lurking/towing AGV: "
            "compact 1410 x 450 x 270 mm chassis, 500 kg tow capacity, Red Dot Award 2016, "
            "and broad use in automotive, electronics, and appliance plants."
        ),
        "features": (
            "Navigation: magnetic navigation. "
            "Delivery mode: lurking and towing. "
            "Rated load: 500 kg. "
            "Dimensions (L x W x H): 1410 x 450 x 270 mm. "
            "Self-weight: 150 kg (Hannover/Jaten catalog). "
            "Speed: ≤32 m/min. Climbing ability: ≤2%. "
            "Turning radius: R700 mm. "
            "Battery: DC 24 V 80 Ah (lead-acid). Charging: offline (24 V, 2 groups), brushless motor. "
            "Travel: forward, turn. "
            "Awards: Red Dot Award 2016; shown at Hannover Messe 2016/2017."
        ),
        "payload_kg": 500.0,
        "weight_kg": 150.0,
        "dimensions_mm": "1410 x 450 x 270",
        "videos": JATEN_VIDEOS,
        "tags": TAGS_TOW,
        "source_note": (
            "OEM PDP id=1000002 (specs) + Hannover catalog White Dolphin sheet (150 kg self-weight, Red Dot). "
            "OEM detail hero JPEG is corrupted (~7 KB glitch) — primary hero is official Red Dot "
            "project photo for AGV-31-MC500; secondary weber.ru still labeled JATEN 31."
        ),
    },
    "SDM500-D228": {
        "url": "https://jaten-robotics.com/index/Agv/detail.html?id=1000001",
        "image": "https://jaten-robotics.com/upload/20220319/9a320dcb97f746691c3cfd4c2eb4642a.jpg",
        "images": [
            "https://jaten-robotics.com/upload/20220319/9a320dcb97f746691c3cfd4c2eb4642a.jpg",
        ],
        "description": (
            "SDM500-D228 is Jaten's natural + QR-code hybrid navigation lifting AGV on the "
            "D228 platform: 990 x 776 x 305 mm, 500 kg rated load, in-place rotation, and online charging."
        ),
        "features": (
            "Navigation: natural navigation + QR code navigation. "
            "Delivery mode: carrying and lifting. "
            "Rated load: 500 kg. "
            "Dimensions (L x W x H): 990 x 776 x 305 mm. "
            "Self-weight: ≤244 kg including battery (OEM D228 brochure). "
            "Supports one- or two-way travel and in-situ rotation; online charging. "
            "Application: warehousing, manufacturing, printing, automotive, power logistics ≤500 kg."
        ),
        "payload_kg": 500.0,
        "weight_kg": 244.0,
        "dimensions_mm": "990 x 776 x 305",
        "videos": JATEN_VIDEOS,
        "tags": TAGS_LIFT,
        "source_note": (
            "OEM PDP id=1000001 + jaten-robotics.com D228 brochure PDF "
            "(upload/20231006/7e459a2d…pdf). Hero: OEM cardImg with JATEN D228 side plate."
        ),
    },
}

SKIP_REASONS: dict[str, str] = {
    "SDM300-335-MG0": "Not on live jaten-robotics.com AGV catalog; CRM detail id=1001022 now serves LN3000-CDD30B-30-JTS",
    "SDM100-335-MG0": "Not on live catalog; CRM id=1001020 now serves LN2000-MFA2035-JTS",
    "SDM1000-335-MG0": "Not on live catalog; CRM id=1001024 now serves R2SDM600-368-QGO",
    "SDM500-335-MG0": "Not on live catalog; CRM id=1001023 now serves MD1000-D376-LER",
    "SDM200-335-MG0": "Not on live catalog; CRM id=1001021 now serves LN3000-CDD30B-20-JTS",
    "MN100-164": "Not on live catalog; CRM id=1000004 now serves LN1600-L16; existing CDN hero labeled D-52 (wrong model)",
    "SDM2000-D228": "Not on live catalog; CRM id=1000005 now serves IN2500-37",
    "SDM1000-D228": "Not on live catalog; CRM id=1000000 empty/dead",
    "SDM3000-D228": "Not on live catalog; CRM id=1000006 now serves AGV-D62-MC1000",
}


def verify_image(url: str) -> bool:
    try:
        resp = requests.head(url, headers=HEADERS, timeout=25, allow_redirects=True)
        if resp.status_code == 405 or "image" not in (resp.headers.get("content-type") or "").lower():
            resp = requests.get(url, headers=HEADERS, timeout=45, stream=True)
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
                break
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("WARN: missing INTERNAL_API_SECRET or API base for copy-media")
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
                print(f"copy-media OK {rid}")
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.15)
    return ok, fail


def build_row(robot: dict, data: dict[str, Any]) -> dict[str, Any]:
    images = [u for u in (data.get("images") or []) if verify_image(u)]
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
        "purpose": data["description"],
        "features": data["features"],
        "url": data["url"],
        "image": hero,
        "images": images,
        "video_urls": videos,
        "movement_type_keys": "wheeled",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics",
        "tags": data.get("tags") or TAGS_LIFT,
        "sources": [
            {"url": data["url"], "type": "website", "title": robot["name"]},
        ],
        "research_notes": data.get("source_note") or "Jaten AGV enrichment.",
        "notes": f"[AI Research] Payload: {data.get('payload_kg')} kg" if data.get("payload_kg") else "",
    }
    if data.get("payload_kg") is not None:
        row["payload_kg"] = data["payload_kg"]
    if data.get("weight_kg") is not None:
        row["weight_kg"] = data["weight_kg"]
    if data.get("dimensions_mm"):
        row["dimensions_mm"] = data["dimensions_mm"]
    return row


def patch_company_website(client: ResearchApiClient) -> None:
    """Set empty company website to OEM domain when missing."""
    try:
        co = client._get(f"companies/{COMPANY_ID}/")
    except Exception as exc:
        print(f"company fetch fail: {exc}")
        return
    if (co.get("website") or "").strip():
        print(f"company website already set: {co.get('website')}")
        return
    website = "https://jaten-robotics.com/"
    try:
        client._patch(f"companies/{COMPANY_ID}/", {"website": website})
        print(f"company website -> {website}")
    except Exception as exc:
        # Some deployments only allow admin forms; non-fatal.
        print(f"company website patch skipped: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Jaten robots for company 1461")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--patch-company", action="store_true", help="Set company website if empty")
    args = parser.parse_args()

    client = ResearchApiClient()
    if args.patch_company or args.apply:
        patch_company_website(client)

    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") != "published"
    ]
    print(f"targets pending/non-published: {len(robots)}")

    plan = []
    staging: dict[int, dict] = {}
    for robot in robots:
        name = robot["name"]
        if name in SKIP_REASONS:
            print(f"SKIP {robot['id']} {name}: {SKIP_REASONS[name]}")
            continue
        data = ROBOT_DATA.get(name)
        if not data:
            print(f"SKIP {robot['id']} {name}: no curated data")
            continue
        row = build_row(robot, data)
        staging[int(robot["id"])] = row
        plan.append({
            "id": robot["id"],
            "name": name,
            "url": row.get("url"),
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
            "payload_kg": row.get("payload_kg"),
            "dimensions_mm": row.get("dimensions_mm"),
        })
        print(
            f"{name}: img={'yes' if row.get('image') else 'no'} "
            f"feat={len(row.get('features') or '')} "
            f"vids={len(row.get('video_urls') or [])} url={row.get('url')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "jaten-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps({"plan": plan, "skipped": SKIP_REASONS}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if any(not p["image"] or not p["features_len"] or not p["videos"] or not p["tags"] for p in plan):
        print("ERROR: incomplete enrichment", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="jaten-fix-"))
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
        print(f"IMPORT OK {rid} {row['name']}")

    print(json.dumps({"ok": all_ok, **totals, "imported": imported}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
