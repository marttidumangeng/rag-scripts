"""Curated Carbon Robotics (266) enrich — LaserWeeder G2 size ladder.

CONTEXT (2026-07-20):
  5 pending G2 SKUs: empty manufacturer_countries, stale Released availability,
  polluted tags (Humanoid/Drone/Warehouse), wrong Service-Robots category,
  missing family_*, partial weight only, no L/W/H despite OEM Unit Specs on each PDP.

KEEP / ENRICH (pending_review):
  2699 G2 200 (4 module)
  2700 G2 300 (6 module)
  2701 G2 400 (8 module)
  2702 G2 600 (12 module)
  2703 G2 1200 (16 module)

SKIP published unless asked:
  385 LaserWeeder™ (CJK brand shell)
  384 Carbon ATK (Autonomy Kit)

Soft: coverage ac/hr is not vehicle speed — leave speed blank. Release year
2025 from OEM BusinessWire G2 debut (2025-02-10).

Usage:
  python discover_carbon_robots.py
  python discover_carbon_robots.py --apply --copy-media
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

COMPANY_ID = 266
COMPANY_SLUG = "carbon-robotics"
COMPANY_NAME = "Carbon Robotics"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "carbon-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

FAMILY_URL = "https://carbonrobotics.com/laserweeder-g2"
FAMILY_KEY = "carbon:laserweeder-g2"
FAMILY_NAME = "LaserWeeder G2"
COMMON_TAGS = "Agriculture|Weeding|Laser|AI|Vision|Implement|Tractor|USA|Precision"

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 2699,
        "name": "Carbon LaserWeeder G2 200",
        "model_name": "LaserWeeder G2 200",
        "variant_code": "G2-200",
        "variant_label": "4 Module",
        "url": "https://carbonrobotics.com/laserweeder-g2-200",
        "release_year": 2025,
        "weight_kg": 1769,
        "width_mm": 2540,
        "length_mm": 2820,
        "height_mm": 2180,
        "modules": 4,
        "lasers": "8 × 240W",
        "cameras": 12,
        "cover": "0.40–0.70 ac/hr (0.16–0.28 ha/hr)",
        "weeds_min": 3333,
        "hp_min": 110,
        "image": (
            "https://cdn.robotaigeek.com/robots/original/"
            "robot-2699-laserweeder-g2-200---4-module-v1783650955.png"
        ),
        "blurb": (
            "Smallest, lightest G2 for smaller farms and easier moves between fields."
        ),
    },
    {
        "id": 2700,
        "name": "Carbon LaserWeeder G2 300",
        "model_name": "LaserWeeder G2 300",
        "variant_code": "G2-300",
        "variant_label": "6 Module",
        "url": "https://carbonrobotics.com/laserweeder-g2-300",
        "release_year": 2025,
        "weight_kg": 2540,
        "width_mm": 3500,
        "length_mm": 2360,
        "height_mm": 3600,
        "modules": 6,
        "lasers": "12 × 240W",
        "cameras": 18,
        "cover": "0.75–1.50 ac/hr (0.30–0.61 ha/hr)",
        "weeds_min": 5000,
        "hp_min": 110,
        "image": (
            "https://cdn.robotaigeek.com/robots/original/"
            "robot-2700-laserweeder-g2-300---6-module-v1783650956.png"
        ),
        "blurb": (
            "Configured for a wide range of global field layouts and wheel spacing."
        ),
    },
    {
        "id": 2701,
        "name": "Carbon LaserWeeder G2 400",
        "model_name": "LaserWeeder G2 400",
        "variant_code": "G2-400",
        "variant_label": "8 Module",
        "url": "https://carbonrobotics.com/laserweeder-g2-400",
        "release_year": 2025,
        "weight_kg": 2722,
        "width_mm": 4570,
        "length_mm": 2160,
        "height_mm": 3430,
        "modules": 8,
        "lasers": "16 × 240W",
        "cameras": 24,
        "cover": "0.80–1.60 ac/hr (0.32–0.65 ha/hr)",
        "weeds_min": 6667,
        "hp_min": 145,
        "image": (
            "https://cdn.robotaigeek.com/robots/original/"
            "robot-2701-laserweeder-g2-400---8-module-v1783650957.png"
        ),
        "blurb": "Mid-sized unit for diverse crop types and field layouts.",
    },
    {
        "id": 2702,
        "name": "Carbon LaserWeeder G2 600",
        "model_name": "LaserWeeder G2 600",
        "variant_code": "G2-600",
        "variant_label": "12 Module",
        "url": "https://carbonrobotics.com/laserweeder-g2-600",
        "release_year": 2025,
        "weight_kg": 3266,
        "width_mm": 6380,
        "length_mm": 2160,
        "height_mm": 3430,
        "modules": 12,
        "lasers": "24 × 240W",
        "cameras": 36,
        "cover": "1.50–3.00 ac/hr (0.61–1.21 ha/hr)",
        "weeds_min": 10000,
        "hp_min": 145,
        "image": (
            "https://cdn.robotaigeek.com/robots/original/"
            "robot-2702-laserweeder-g2-600---12-module-v1783650957.png"
        ),
        "blurb": "Next-generation flagship — faster and lighter than prior G1-era units.",
    },
    {
        "id": 2703,
        "name": "Carbon LaserWeeder G2 1200",
        "model_name": "LaserWeeder G2 1200",
        "variant_code": "G2-1200",
        "variant_label": "16 Module",
        "url": "https://carbonrobotics.com/laserweeder-g2-1200",
        "release_year": 2025,
        "weight_kg": 8165,
        "width_mm": 12140,
        "length_mm": 2840,
        "height_mm": 3300,
        "modules": 16,
        "lasers": "32 × 240W",
        "cameras": 48,
        "cover": "3–6 ac/hr (1.21–2.43 ha/hr)",
        "weeds_min": None,
        "hp_min": 150,
        "image": (
            "https://cdn.robotaigeek.com/robots/original/"
            "robot-2703-laserweeder-g2-1200---16-module-v1783650958.png"
        ),
        "blurb": (
            "Large-scale ~40 ft unit designed for organic corn and soybean farms."
        ),
    },
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=120)
        data = r.content or b""
        if r.status_code != 200 or len(data) < 2000:
            return False, "", len(data)
        # CDN may serve WebP under .png names (RIFF....WEBP) or JPEG/PNG.
        is_jpeg = data[:3] == b"\xff\xd8\xff"
        is_png = data[:8] == b"\x89PNG\r\n\x1a\n"
        is_webp = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        if not (is_jpeg or is_png or is_webp):
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
    out: list[str] = []
    seen: set[str] = set()
    for vid in ids:
        if vid in seen:
            continue
        seen.add(vid)
        out.append(f"https://www.youtube.com/watch?v={vid}")
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
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or os.environ.get("RESEARCH_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    for attempt in range(5):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return f"ok {resp.text[:100]}"
            if resp.status_code not in (502, 503, 504, 500):
                return f"HTTP {resp.status_code}"
        except requests.RequestException:
            pass
        time.sleep(2**attempt)
    return "fail"


def filter_videos(spec: dict[str, Any]) -> list[dict[str, Any]]:
    urls: list[str] = []
    code = (spec.get("variant_code") or "").lower()
    queries = [
        f"Carbon Robotics LaserWeeder {code}",
        "Carbon Robotics LaserWeeder G2",
        "LaserWeeder G2 carbon robotics",
    ]
    for q in queries:
        urls.extend(yt_search(q, limit=5))
    seen_u: set[str] = set()
    uniq = []
    for u in urls:
        if u not in seen_u:
            seen_u.add(u)
            uniq.append(u)
    vids = enrich_video_list(uniq)
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        channel = (v.get("channel") or v.get("author_name") or "").lower()
        blob = f"{title} {channel}"
        if "farmwise" in blob or "john deere see" in blob:
            continue
        if "laserweeder" not in blob and "carbon robotics" not in blob:
            continue
        kept.append(v)
    return kept[:3]


def force_en_translations(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"carbon-en-force-{rid}-20260720-{loc}",
                "translated_fields": {
                    "description": row.get("description") or "",
                    "features": row.get("features") or "",
                    "purpose": row.get("purpose") or "",
                    "name": row.get("name") or "",
                },
            }
            for loc in ("zh-CN", "zh-TW")
        ]
    }
    try:
        resp = client._session.post(
            client._url("robots/robots/translation-sync/?force=1"),
            json=sync,
            timeout=60,
        )
        print(f"  translation-sync {rid}: {resp.status_code} {resp.text[:120]}")
    except requests.RequestException as e:
        print(f"  translation-sync warn {rid}: {e}")


def build_row(spec: dict[str, Any], used_hashes: set[str]) -> dict[str, Any]:
    images: list[str] = []
    u = spec["image"]
    ok, md5, nbytes = download_ok(u)
    if not ok:
        print(f"  !! image fail {u[:90]}")
    elif md5 in used_hashes:
        print(f"  !! skip cross-robot hash {md5[:12]}")
    else:
        used_hashes.add(md5)
        images.append(u)
        print(f"  img ok {md5[:12]} {nbytes}")

    kept = filter_videos(spec)
    print(f"  videos kept={len(kept)}")
    for v in kept:
        print(f"    - {(v.get('title') or '')[:80]}")

    weeds = spec.get("weeds_min")
    weeds_txt = f" Max weeds shot/min {weeds:,}." if weeds else ""
    features = (
        f"OEM carbonrobotics.com {spec['variant_code']} Unit Specs + Technology: "
        f"tractor-mounted LaserWeeder G2 with {spec['modules']} sealed weeding "
        f"modules ({spec['lasers']} diode lasers, {spec['cameras']} high-res "
        f"cameras, high-intensity LED bedtop lights, NVIDIA GPUs, 100+ AI crop "
        f"models). AccuStop-class laser weeding: sub-mm accuracy, kills up to "
        f"99% of weeds; coverage {spec['cover']}.{weeds_txt} "
        f"Overall dims {spec['width_mm']/1000:.2f} W × {spec['length_mm']/1000:.2f} "
        f"D × {spec['height_mm']/1000:.2f} H m; weight {spec['weight_kg']:,} kg. "
        f"CAT 3 3-point hitch; min tractor ~{spec['hp_min']} hp; PTO generator "
        f"power; iPad Operator App + Carbon Ops Center + Companion App. "
        f"{spec['blurb']} Soft: coverage rate is not a vehicle speed column — "
        f"speed left blank."
    )
    description = (
        f"{spec['name']} is Carbon Robotics' tractor-mounted AI laser weeding "
        f"implement ({spec['variant_label']}) in the LaserWeeder G2 family — "
        f"{spec['blurb']}"
    )
    notes = (
        "[AI Research] Carbon enrich 2026-07-20. US country; Available; "
        "Agricultural-Robots taxonomy; family carbon:laserweeder-g2; typed "
        "W/D/H + weight from OEM Unit Specs; scrubbed junk tags; kept distinct "
        f"OEM CDN heroes."
    )
    row: dict[str, Any] = {
        "id": spec["id"],
        "name": spec["name"],
        "model_name": spec["model_name"],
        "variant_code": spec["variant_code"],
        "variant_label": spec["variant_label"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "manufacturer_country_codes": "US",
        "description": description,
        "purpose": "Tractor-mounted AI laser weeding implement for row crops",
        "features": features,
        "url": spec["url"],
        "image": images[0] if images else "",
        "images": images,
        "video_urls": kept,
        "movement_type_keys": "wheeled",
        "category_slugs": "agricultural-robots",
        "use_keys": "agriculture|farming",
        "industry_keys": "agriculture",
        "tags": COMMON_TAGS,
        "source_locale": "en",
        "availability_status": AVAILABLE,
        "family_key": FAMILY_KEY,
        "family_name": FAMILY_NAME,
        "family_url": FAMILY_URL,
        "product_url_scope": "exact_variant",
        "weight_kg": spec["weight_kg"],
        "width_mm": spec["width_mm"],
        "length_mm": spec["length_mm"],
        "height_mm": spec["height_mm"],
        "release_year": spec.get("release_year"),
        "research_notes": (
            "[AI Research] Carbon 2026-07-20. Specs from each G2 PDP Unit Specs; "
            "release_year 2025 from BusinessWire G2 debut 2025-02-10."
        ),
        "sources": [
            {"url": spec["url"], "type": "website", "title": spec["model_name"]},
            {"url": FAMILY_URL, "type": "website", "title": "LaserWeeder G2 family"},
            {
                "url": (
                    "https://www.businesswire.com/news/home/20250210556114/en/"
                    "Carbon-Robotics-Introduces-Faster-Lighter-and-Modular-"
                    "LaserWeeder-G2-Product-Line"
                ),
                "type": "press",
                "title": "LaserWeeder G2 debut BusinessWire 2025-02-10",
            },
        ],
        "information_source_urls": [
            spec["url"],
            FAMILY_URL,
            (
                "https://www.businesswire.com/news/home/20250210556114/en/"
                "Carbon-Robotics-Introduces-Faster-Lighter-and-Modular-"
                "LaserWeeder-G2-Product-Line"
            ),
        ],
        "notes": notes,
    }
    return row


def patch_fields(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": AVAILABLE,
        "name": row.get("name"),
        "model_name": row.get("model_name"),
        "variant_code": row.get("variant_code"),
        "variant_label": row.get("variant_label"),
        "description": row.get("description"),
        "features": row.get("features"),
        "purpose": row.get("purpose"),
        "url": row.get("url"),
        "source_locale": "en",
        "notes": row.get("notes") or "",
        "family_key": FAMILY_KEY,
        "family_name": FAMILY_NAME,
        "family_url": FAMILY_URL,
        "product_url_scope": "exact_variant",
        "weight_kg": row.get("weight_kg"),
        "width_mm": row.get("width_mm"),
        "length_mm": row.get("length_mm"),
        "height_mm": row.get("height_mm"),
        "release_year": row.get("release_year"),
        "tags": (row.get("tags") or "").split("|")
        if isinstance(row.get("tags"), str)
        else row.get("tags"),
        "s3_image": None,
    }
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
    plan: dict[str, Any] = {"company_id": COMPANY_ID, "robots": [], "apply": bool(args.apply)}
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    used_hashes: set[str] = set()

    for spec in PRODUCTS:
        print(f"Building {spec['name']}...")
        row = build_row(spec, used_hashes)
        if not row.get("images"):
            print(f"  !! FAIL CLOSED — no images for {spec['name']}")
        rows.append((spec, row))
        plan["robots"].append(
            {
                "name": spec["name"],
                "id": spec["id"],
                "images_n": len(row.get("images") or []),
                "videos_n": len(row.get("video_urls") or []),
                "feat_len": len(row.get("features") or ""),
                "weight_kg": row.get("weight_kg"),
                "width_mm": row.get("width_mm"),
            }
        )

    if not args.apply:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps({"plan": plan, "rows": [r for _, r in rows]}, indent=2),
            encoding="utf-8",
        )
        print(f"Dry-run -> {REPORT}")
        return 0

    for spec, row in rows:
        if not row.get("images"):
            print(f"SKIP {spec['name']}")
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", spec["name"].lower()).strip("-")
        path = staging_dir / f"{slug}.json"
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        result = import_staging(
            path,
            dry_run=False,
            patch=True,
            force_overwrite=True,
            replace_media=True,
            status="pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        rid = int(spec["id"])
        patch_fields(client, rid, row)
        force_en_translations(client, rid, row)
        if args.copy_media:
            print(f"copy-media {rid}:", copy_media(rid))

    for spec, row in rows:
        rid = int(spec["id"])
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "availability_status": AVAILABLE,
                    "weight_kg": row["weight_kg"],
                    "width_mm": row["width_mm"],
                    "length_mm": row["length_mm"],
                    "height_mm": row["height_mm"],
                    "family_key": FAMILY_KEY,
                    "family_name": FAMILY_NAME,
                    "family_url": FAMILY_URL,
                    "s3_image": None,
                },
            )
            print(f"  re-PATCH specs/avail {rid}")
        except Exception as e:  # noqa: BLE001
            print(f"  re-PATCH warn {rid}: {e}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
