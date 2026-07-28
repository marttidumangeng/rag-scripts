"""Backfill Infinium Robotics (company 783) Infinium Scan: photo, features, specs, videos, tags.

Discovery: official site only markets one named robot product (Infinium Scan).
/packages are pricing models (scheduled vs on-demand), not additional robots.
About page mentions swarming UAS displays as a capability without a separate product page —
do not invent a second robot without a named OEM product URL.
"""

from __future__ import annotations

import argparse
import hashlib
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

COMPANY_ID = 783
COMPANY_SLUG = "infinium-robotics"
COMPANY_NAME = "Infinium Robotics"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TAGS = (
    "Warehouse Automation|Drone|UAV|AMR|Autonomous|Indoor Logistics|"
    "Warehouse|Industrial"
)
WHITEPAPER_URL = (
    "https://infiniumrobotics.com/whitepaper-on-applications-of-drones-in-warehouse-operations/"
)

ROBOT_DATA: dict[str, dict[str, Any]] = {
    "Infinium Scan": {
        "url": "https://infiniumrobotics.com/infinium-scan/",
        "image": "https://infiniumrobotics.com/wp-content/uploads/2025/09/Back-Profile-Photo-of-Infinium-Scan-768x1024.jpg",
        "images": [
            "https://infiniumrobotics.com/wp-content/uploads/2025/09/Back-Profile-Photo-of-Infinium-Scan-768x1024.jpg",
            "https://infiniumrobotics.com/wp-content/uploads/2025/09/Infinium-Scan-in-the-Warehouse-34-e1758023882887.jpg",
            "https://infiniumrobotics.com/wp-content/uploads/2025/09/Infinium-Scan-Photo-from-Back-Beacon-805x1024.jpg",
        ],
        "description": (
            "Infinium Scan is Infinium Robotics' autonomous indoor warehouse inventory system: "
            "a tethered self-flying drone paired with a ground robot that navigates aisles, "
            "scans pallet locations, and feeds real-time analytics into warehouse management systems."
        ),
        "purpose": (
            "Automated warehouse inventory cycle counting\n"
            "High-rack inspection and pallet barcode scanning"
        ),
        "features": (
            "Hybrid tethered drone + autonomous ground robot for indoor stocktaking. "
            "Self-flying, no pilot required; automatically avoids obstacles and humans. "
            "Tethered design for continuous power (operational flight time cited as unlimited). "
            "Blue LED / floor beacon on the ground robot for OSH-aware staff awareness. "
            "Operates without Wi‑Fi (no warehouse dead-zones). "
            "Individual box/carton counting; typical pallet-location scan time 2–5 seconds. "
            "Flies above 30 ft / 10 m for high-rack inspection in GPS-denied indoor spaces. "
            "Compatible with the vast majority of WMS platforms; real-time inventory analytics. "
            "Claimed >20× faster and up to 10× cheaper than manual counts; ROI cited as short as ~9 months."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=oBlmGOwxHsE",
            "https://www.youtube.com/watch?v=b-uYgxdcJHY",
            "https://www.youtube.com/watch?v=auEk2rGw-4U",
        ],
        "family_key": "infinium:scan",
        "family_name": "Infinium Scan",
        "variant_code": "INFINIUM-SCAN",
        "variant_label": "Scan",
        "source_note": (
            "Product copy/specs from infiniumrobotics.com/infinium-scan/ "
            "(pallet scan 2–5 s, >30 ft / 10 m, tethered unlimited flight, no Wi‑Fi, WMS compatibility). "
            "Hero: official warehouse photo of tethered Scan system. "
            "YouTube: showcase, autonomous landing, CES 2018 live demo. "
            "Catalog discovery: only named product on OEM site; /packages are commercial plans."
            " PDP, OEM whitepaper page, homepage, and official product videos were checked; "
            "no citeable physical mass, overall dimensions, payload, locomotion speed, battery "
            "capacity, or numeric runtime suitable for Robot typed fields is published. The "
            "2–5 second scan time, >10 m operating height, and 0.7 m aisle width describe the "
            "application/environment, not robot dimensions or locomotion."
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


def validate_media(urls: list[str]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    valid: list[str] = []
    audit: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for url in dict.fromkeys(urls):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=45)
            body = resp.content
            magic_ok = body.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF"))
            digest = hashlib.md5(body).hexdigest()
            duplicate = digest in seen
            audit[url] = {
                "status": resp.status_code, "bytes": len(body), "md5": digest,
                "magic_ok": magic_ok, "duplicate": duplicate,
            }
            if resp.status_code == 200 and magic_ok and len(body) >= 10_000 and not duplicate:
                valid.append(url)
                seen.add(digest)
        except requests.RequestException as exc:
            audit[url] = {"error": str(exc)}
    return valid, audit


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
    images, media_audit = validate_media([
        u for u in [data.get("image") or "", *(data.get("images") or [])] if u
    ])
    hero = images[0] if images else ""

    videos = enrich_video_list(data.get("videos") or [])
    return {
        "name": robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "SG",
        "description": data["description"],
        "purpose": data["purpose"],
        "features": data["features"],
        "url": data["url"],
        "image": hero,
        "images": images,
        "video_urls": videos,
        "movement_type_keys": "hybrid",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics",
        "tags": TAGS,
        "availability_status": 11,
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": data["url"],
        "model_name": robot["name"],
        "variant_code": data["variant_code"],
        "variant_label": data["variant_label"],
        "product_url_scope": "exact_variant",
        "sources": [
            {"url": data["url"], "type": "website", "title": robot["name"]},
            {"url": WHITEPAPER_URL, "type": "paper", "title": "Warehouse drone applications whitepaper"},
        ],
        "information_source_urls": [data["url"], WHITEPAPER_URL],
        "research_notes": data.get("source_note") or "Infinium Scan enrichment.",
        "_media_audit": media_audit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Infinium Robotics robots for company 783")
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
    print(
        "discovery: OEM site lists only Infinium Scan as a named robot product; "
        "/packages are pricing plans, not additional robots."
    )

    plan = []
    staging: dict[int, dict] = {}
    for robot in robots:
        data = ROBOT_DATA.get(robot["name"])
        if not data:
            print(f"SKIP {robot['id']} {robot['name']}: no curated data")
            continue
        row = build_row(robot, data)
        media_audit = row.pop("_media_audit")
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
            "family_key": row.get("family_key"),
            "availability_status": row.get("availability_status"),
            "media_audit": media_audit,
        })
        print(
            f"{robot['name']}: img={'yes' if row.get('image') else 'no'} "
            f"feat={len(row.get('features') or '')} "
            f"vids={len(row.get('video_urls') or [])} url={row.get('url')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "infinium-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if any(
        not p["image"] or not p["features_len"] or not p["videos"] or not p["tags"]
        or not p["family_key"] or p["availability_status"] != 11
        for p in plan
    ):
        print("ERROR: incomplete enrichment", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="infinium-fix-"))
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
        data = ROBOT_DATA[row["name"]]
        video_result = client.bulk_import_robots(
            [row],
            update_existing=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_videos=True,
        )
        if video_result.get("error_count"):
            all_ok = False
            print(f"VIDEO REPLACE FAIL {rid}: {video_result}", file=sys.stderr)
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "pending_review",
                "availability_status": 11,
                "family_key": data["family_key"],
                "family_name": data["family_name"],
                "family_url": data["url"],
                "model_name": row["name"],
                "variant_code": data["variant_code"],
                "variant_label": data["variant_label"],
                "product_url_scope": "exact_variant",
                "purpose": data["purpose"],
                "information_source_urls": [
                    {
                        "url": source["url"],
                        "title": source["title"],
                        "source_type": source["type"],
                    }
                    for source in row["sources"]
                ],
            },
        )
        for k in totals:
            totals[k] += result.get(k, 0) or 0

    print(json.dumps({"ok": all_ok, **totals}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
