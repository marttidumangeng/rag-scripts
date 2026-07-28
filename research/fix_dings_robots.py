"""Backfill Jiangsu DINGS (company 1512) Gripper series EOAT.

CRM name is the generic product-line label \"Gripper\". Official Gripper Series
(DMEG electric grippers) from DINGS Motion USA + ENG product catalog (May 2026).
www.dingsmotion.com has a broken SSL cert — prefer USA subsidiary URL for hero
CDN assets; keep OEM product-middle URL in sources when cited.
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

COMPANY_ID = 1512
COMPANY_SLUG = "jiangsu-dings-intelligent-control-technology"
COMPANY_NAME = "Jiangsu DINGS Intelligent Control Technology Co., Ltd."
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

PRODUCT_URL = "https://www.dingsmotionusa.com/robotic-grippers"
OEM_URL = "https://www.dingsmotion.com/products/products-middle-10.php"
CATALOG_URL = "http://fr.dingsmotion.com/downloads/catalog/Gripper_Product%20Catalog_ENG.pdf"

HERO = (
    "https://images.squarespace-cdn.com/content/v1/65098da04c5aa04f8f5ed336/"
    "e907ef1b-920c-4a14-913a-61209d4c4df2/Nema%2B17%2BGripper.png"
    "?content-type=image%2Fpng"
)
IMG_NEMA14 = (
    "https://images.squarespace-cdn.com/content/v1/65098da04c5aa04f8f5ed336/"
    "cc3d8735-68b2-44cc-86f3-1b7293f77fb6/Nema%2B14%2BGripper.png"
    "?content-type=image%2Fpng"
)
IMG_NEMA11 = (
    "https://images.squarespace-cdn.com/content/v1/65098da04c5aa04f8f5ed336/"
    "dff92caf-b7ea-482a-938c-6567f6857620/Nema%2B11%2BGripper.png"
    "?content-type=image%2Fpng"
)
IMG_NEMA8 = (
    "https://images.squarespace-cdn.com/content/v1/65098da04c5aa04f8f5ed336/"
    "036b2059-bd3b-4aad-9138-581469f41809/Nema%2B8%2BGripper.png"
    "?content-type=image%2Fpng"
)

TAGS = (
    "Industrial|Manufacturing|Pick-and-Place|Compact|Precision|"
    "Electric|Assembly|Manipulation|Modular"
)

# Official DINGS demo titles only (reject Hitbot / DH / hand-dynamometer junk).
VIDEOS = [
    "https://www.youtube.com/watch?v=5qQ36P3s4h4",
    "https://www.youtube.com/watch?v=VLIV5ufzotc",
]

ROBOT_DATA: dict[str, dict[str, Any]] = {
    "Gripper": {
        "url": PRODUCT_URL,
        "image": HERO,
        "images": [HERO, IMG_NEMA14, IMG_NEMA11, IMG_NEMA8],
        "description": (
            "DINGS Gripper Series (DMEG) is Jiangsu DINGS Intelligent Control's line of "
            "motor-driven electric robotic grippers: compact stepper-powered 2-finger and "
            "3-finger end effectors for precision pick-and-place and assembly automation."
        ),
        "features": (
            "Product family: Electric Gripper (DMEG part-number series). "
            "Frame sizes: 20 mm (NEMA 8), 28 mm (NEMA 11), 35 mm (NEMA 14), 42 mm (NEMA 17). "
            "2-finger parallel models (20/28 mm) and 3-finger centric models (35/42 mm). "
            "Stroke options: 6 mm (all sizes); 12 mm also on 28 mm class. "
            "Integrated non-captive lead-screw linear actuator with 2-phase 1.8° stepper. "
            "Example recommended gripping force ranges from catalog: ~6–70 N depending on "
            "motor stack and lead (max force ratings up to ~371 N on largest 42 mm config). "
            "Mass examples: ~0.15–0.46 kg depending on size/stack. "
            "Optional encoder (EK) and configurable lead-screw codes; 1-year warranty from shipment."
        ),
        "videos": VIDEOS,
        "tags": TAGS,
        "source_note": (
            f"Specs from ENG Gripper Product Catalog ({CATALOG_URL}, catalog issued May 2026) "
            f"and DINGS Motion USA robotic grippers page ({PRODUCT_URL}). "
            f"OEM CN listing also at {OEM_URL} (site SSL often broken). "
            "Heroes: official USA Squarespace NEMA 17/14/11/8 gripper product stills. "
            "YouTube: DINGS Electric Gripper + force-control stepper controller demos."
        ),
    },
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
    return {
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
        "movement_type_keys": "stationary",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "industrial",
        "tags": data.get("tags") or TAGS,
        "sources": [
            {"url": PRODUCT_URL, "type": "website", "title": "DINGS Motion USA Robotic Grippers"},
            {"url": CATALOG_URL, "type": "datasheet", "title": "Gripper Product Catalog ENG"},
            {"url": OEM_URL, "type": "website", "title": "dingsmotion.com Gripper middle"},
        ],
        "research_notes": data.get("source_note") or "DINGS Gripper series enrichment.",
    }


def patch_company_website(client: ResearchApiClient) -> None:
    try:
        co = client._get(f"companies/{COMPANY_ID}/")
    except Exception as exc:
        print(f"company fetch fail: {exc}")
        return
    if (co.get("website") or "").strip():
        print(f"company website already set: {co.get('website')}")
        return
    # Prefer USA site with valid SSL for operators; HQ brand is dingsmotion.com
    website = "https://www.dingsmotionusa.com/"
    try:
        client.patch_company(COMPANY_ID, {"website": website})
        print(f"company website -> {website}")
    except Exception as exc:
        try:
            client._patch(f"companies/{COMPANY_ID}/", {"website": website})
            print(f"company website -> {website}")
        except Exception as exc2:
            print(f"company website patch skipped: {exc}; {exc2}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix DINGS Gripper for company 1512")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--patch-company", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    if args.patch_company or args.apply:
        patch_company_website(client)

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
            "url": row.get("url"),
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
        })
        print(
            f"{robot['name']}: img={'yes' if row.get('image') else 'no'} "
            f"feat={len(row.get('features') or '')} "
            f"vids={len(row.get('video_urls') or [])} url={row.get('url')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "dings-fix-preview.json"
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

    tmp = Path(tempfile.mkdtemp(prefix="dings-fix-"))
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
