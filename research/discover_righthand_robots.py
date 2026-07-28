"""Curated RightHand Robotics (258) enrich.

ENRICH pending_review:
  RightPick (3808) → rename RightPick 4; replace nav-scrape features junk;
  wrong aerial movement → stationary; add country/uses/industries; OEM heroes

SKIP create:
  RightPick Fleet Management — software
  RightCare — service program, not a robot SKU
  Prior-gen RightPick 3 — no live OEM PDP; current catalog is RightPick / RightPick 4

Usage:
  python discover_righthand_robots.py
  python discover_righthand_robots.py --apply --copy-media
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from youtube_metadata import enrich_video_list

COMPANY_ID = 258
COMPANY_SLUG = "righthand-robotics"
COMPANY_NAME = "RightHand Robotics"
US_ID = 20
REPORT = _RESEARCH_DIR / "staging" / "reports" / "righthand-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# Prefer files.svdcdn.com origins — transforms.svdcdn.com returns 401 without signed params.
PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "RightPick 4",
        "id": 3808,
        "action": "enrich",
        "status": "pending_review",
        "rename_from": "RightPick",
        "url": "https://righthandrobotics.com/products",
        "model_name": "RightPick 4",
        "availability_status": 11,
        "category_slugs": "warehouse-robots|arm",
        "movement_type_keys": "stationary",
        "use_keys": "picking|material-handling|logistics|intralogistics|handling",
        "industry_keys": "logistics|retail|manufacturing",
        "tags": (
            "Autonomous|Warehouse|Logistics|Piece Picking|Industrial|"
            "Stationary|AI|Gripper|Order Fulfillment"
        ),
        # Item payload capacity (not robot mass) — OEM/tech-sheet reprint via NED
        "payload_kg": 3.0,
        "speed": "As fast as 3-second pick cycle (OEM products page)",
        "images": [
            "https://rh-robotics.files.svdcdn.com/production/assets/img/images/RP4_OG_image.jpg",
            "https://rh-robotics.files.svdcdn.com/production/assets/img/bgimages/RightHand-Robotics-Staples-20231128-3669_cr_2024-05-31-171556_tylp.jpg",
            "https://rh-robotics.files.svdcdn.com/production/assets/img/bgimages/RP4_Heavy-20240121-0034.MP4.11_11_11_02.Still001_ed_2024-05-31-172505_wjum.jpg",
            "https://rh-robotics.files.svdcdn.com/production/assets/img/bgimages/RightHand-Robotics-Automated-Piece-Picking_2024-05-31-172516_vnvc.jpg",
            "https://rh-robotics.files.svdcdn.com/production/assets/img/images/top-nav-rightpick-thumb-2.jpg",
        ],
        "videos": [
            "https://www.youtube.com/watch?v=0YQvGqWqQ0E",  # may fail filter — search fills
        ],
        "video_queries": [
            "RightHand Robotics RightPick 4",
            "RightPick piece picking RightHand Robotics",
        ],
        "video_needles": ["rightpick", "righthand", "right hand robotics"],
        "video_reject": [
            "unboxing",
            "review scam",
            "fanuc only",
            "universal robots tutorial",
        ],
        "description": (
            "RightPick 4 is RightHand Robotics' AI-powered autonomous piece-picking system "
            "for warehouse and distribution order fulfillment. It combines a proprietary "
            "hybrid gripper (compliant fingers + suction), an industrial vision system, and "
            "RightPick AI for model-free picking across a wide SKU range with minimal human "
            "intervention."
        ),
        "features": (
            "Autonomous AI piece-picking workcell for warehouse/DC order fulfillment "
            "(OEM products page). "
            "Proprietary hybrid gripper with three compliant fingers plus suction; "
            "optional Suction Cup Swapper switches cup types in real time for wider SKU "
            "coverage (OEM products page). "
            "Industrial machine-vision cameras designed for piece-picking; RightPick AI "
            "model-free item recognition with fleet learning across deployed robots "
            "(OEM products page). "
            "OEM claims: pick & place across millions of SKUs; as fast as 3-second cycle "
            "time; 24/7 autonomous order fill; optional in-hand barcode scanning "
            "(OEM products page). "
            "RightPick 4 item handling (tech-sheet / OEM-cited reprint): item weight up to "
            "3 kg (7 lb); item size about 1–30 cm (0.4–12 in); operating temp 10–40°C."
        ),
        "purpose": (
            "Autonomous robotic piece-picking for warehouse order fulfillment and "
            "goods-to-person workflows"
        ),
        "sources": [
            {
                "url": "https://righthandrobotics.com/products",
                "title": "RightHand Robotics — RightPick products",
            },
            {
                "url": "https://righthandrobotics.com/resources/the-rightpick-4-system-tech-sheet",
                "title": "RightPick 4 System Tech Sheet (OEM resource)",
            },
        ],
    },
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=90)
        data = r.content
        if r.status_code != 200 or len(data) < 2000:
            return False, "", len(data)
        if data[:1] in (b"{", b"<") and b"JFIF" not in data[:32] and not data.startswith(
            b"\x89PNG"
        ):
            return False, "", len(data)
        if not (
            data.startswith(b"\xff\xd8")
            or data.startswith(b"\x89PNG")
            or data[:4] == b"RIFF"
        ):
            return False, "", len(data)
        return True, hashlib.md5(data).hexdigest(), len(data)
    except requests.RequestException:
        return False, "", 0


def yt_search(query: str, limit: int = 6) -> list[str]:
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    try:
        html = requests.get(url, headers=UA, timeout=30).text
    except requests.RequestException:
        return []
    ids = re.findall(r"\"videoId\":\"([a-zA-Z0-9_-]{11})\"", html)
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        out.append(f"https://www.youtube.com/watch?v={i}")
        if len(out) >= limit:
            break
    return out


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not api:
        api = os.environ.get("RESEARCH_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return "no-secret"
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    for attempt in range(5):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return f"ok {resp.text[:80]}"
            if resp.status_code not in (502, 503, 504):
                return f"HTTP {resp.status_code}"
        except requests.RequestException:
            pass
        time.sleep(2**attempt)
    return "fail"


def filter_videos(spec: dict[str, Any]) -> list[dict[str, Any]]:
    urls = list(spec.get("videos") or [])
    for q in spec.get("video_queries") or []:
        urls.extend(yt_search(q, limit=6))
    seen_u: set[str] = set()
    uniq = []
    for u in urls:
        if u not in seen_u:
            seen_u.add(u)
            uniq.append(u)
    vids = enrich_video_list(uniq)
    needles = [n.lower() for n in (spec.get("video_needles") or [spec["name"].lower()])]
    reject = [b.lower() for b in (spec.get("video_reject") or [])]
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        channel = (v.get("channel") or v.get("author_name") or "").lower()
        blob = f"{title} {channel}"
        if any(b in blob for b in reject):
            continue
        if any(n in blob for n in needles):
            kept.append(v)
    return kept[:3]


def build_row(spec: dict[str, Any]) -> dict[str, Any]:
    images: list[str] = []
    seen: set[str] = set()
    for u in spec.get("images") or []:
        ok, md5, nbytes = download_ok(u)
        if not ok:
            print(f"  !! image fail {u}")
            continue
        if md5 in seen:
            continue
        seen.add(md5)
        images.append(u)
        print(f"  img ok {md5[:12]} {nbytes}")

    kept = filter_videos(spec)
    print(f"  videos kept={len(kept)}")
    for v in kept:
        print(f"    - {(v.get('title') or '')[:80]}")

    notes = (
        "[AI Research] RightHand Robotics curated enrich 2026-07-19. "
        "Renamed RightPick → RightPick 4; cleared nav-scrape features; "
        "fixed aerial→stationary; OEM files.svdcdn.com heroes."
    )

    row: dict[str, Any] = {
        "name": spec["name"],
        "model_name": spec.get("model_name") or spec["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "manufacturer_country_codes": "US",
        "description": spec["description"],
        "purpose": spec["purpose"],
        "features": spec["features"],
        "url": spec["url"],
        "image": images[0] if images else "",
        "images": images,
        "video_urls": kept,
        "movement_type_keys": spec.get("movement_type_keys") or "stationary",
        "category_slugs": spec.get("category_slugs") or "warehouse-robots",
        "use_keys": spec.get("use_keys") or "picking|logistics",
        "industry_keys": spec.get("industry_keys") or "logistics",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or 11,
        "research_notes": (
            "[AI Research] RightHand 2026-07-19. Products page + RightPick 4 tech-sheet "
            "resource; item payload 3 kg from OEM-cited tech sheet reprint (not robot mass)."
        ),
        "sources": [
            {"url": s["url"], "type": "website", "title": s.get("title") or s["url"]}
            for s in (spec.get("sources") or [{"url": spec["url"]}])
        ],
        "information_source_urls": [
            s["url"] for s in (spec.get("sources") or [{"url": spec["url"]}])
        ],
        "notes": notes,
    }
    if spec.get("id"):
        row["id"] = spec["id"]
    for k in ("weight_kg", "height_mm", "width_mm", "length_mm", "speed", "release_year", "payload_kg"):
        if spec.get(k) is not None:
            row[k] = spec[k]
    return row


def patch_fields(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": row.get("availability_status") or 11,
        "name": row.get("name"),
        "model_name": row.get("model_name"),
        "description": row.get("description"),
        "features": row.get("features"),
        "purpose": row.get("purpose"),
        "url": row.get("url"),
        "source_locale": "en",
        "notes": row.get("notes") or "",
        "tags": (row.get("tags") or "").split("|")
        if isinstance(row.get("tags"), str)
        else row.get("tags"),
    }
    for k in ("weight_kg", "height_mm", "width_mm", "length_mm", "speed", "release_year", "payload_kg"):
        if row.get(k) is not None:
            body[k] = row[k]
    # Clear bogus robot mass if prior AI put item payload in weight_kg
    body["weight_kg"] = None
    try:
        client._patch(f"robots/robots/{rid}/", body)
        print(f"  patched fields {rid}")
    except Exception as e:  # noqa: BLE001
        body.pop("tags", None)
        try:
            client._patch(f"robots/robots/{rid}/", body)
            print(f"  patched fields {rid} (no tags)")
        except Exception as e2:  # noqa: BLE001
            print(f"  patch warn {rid}: {e} / {e2}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    staging_dir = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG
    staging_dir.mkdir(parents=True, exist_ok=True)
    plan: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "robots": [],
        "apply": bool(args.apply),
    }
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for spec in PRODUCTS:
        print(f"Building {spec['name']} ({spec['action']})…")
        row = build_row(spec)
        rows.append((spec, row))
        plan["robots"].append(
            {
                "name": spec["name"],
                "id": spec.get("id"),
                "images_n": len(row.get("images") or []),
                "videos_n": len(row.get("video_urls") or []),
            }
        )

    if not args.apply:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps({"plan": plan, "rows": [r for _, r in rows]}, indent=2),
            encoding="utf-8",
        )
        print(f"Dry-run → {REPORT}")
        return 0

    for spec, row in rows:
        slug = re.sub(r"[^a-z0-9]+", "-", spec["name"].lower()).strip("-")
        path = staging_dir / f"{slug}.json"
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        result = import_staging(
            path,
            dry_run=False,
            patch=True,
            force_overwrite=True,
            replace_media=bool(row.get("images")),
            status=spec.get("status") or "pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        rid = spec.get("id")
        if rid:
            patch_fields(client, rid, row)
            if args.copy_media and row.get("images"):
                print(f"copy-media {rid}:", copy_media(rid))
            for item in plan["robots"]:
                if item["name"] == spec["name"]:
                    item["import"] = result

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
