"""Curated Figure AI (36) enrich — Figure 03.

CONTEXT (2026-07-20):
  Pending 2502 Figure 03: empty country, no family_*, Prototype avail, weight=0,
  no typed height/payload/speed/runtime/year despite OEM figure.ai/figure specs.

ENRICH:
  2502 Figure 03 — Available; US; Humanoid; family figure:figure
    OEM: 5'8" / 61 kg / 20 kg payload / 5 hr / 1.2 m/s; debut 2025-10-09

SKIP published unless asked: Figure 01/02, Helix 02 (AI), CJK shell 485.

Usage:
  python discover_figure_robots.py
  python discover_figure_robots.py --apply --copy-media
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

COMPANY_ID = 36
COMPANY_SLUG = "figure-ai"
COMPANY_NAME = "Figure AI"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "figure-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

PRODUCT_URL = "https://www.figure.ai/figure"
INTRO_URL = "https://www.figure.ai/news/introducing-figure-03"
FAMILY_KEY = "figure:figure"
FAMILY_NAME = "Figure"
FAMILY_URL = PRODUCT_URL
HERO = (
    "https://cdn.robotaigeek.com/research-staging/figure/figure03-studio-hero.jpg"
)

# OEM figure.ai/figure: Height 5'8", Payload 20KG, Weight 61KG, Runtime 5HR, Speed 1.2M/S
# 5'8" = 1727.2 mm; 1.2 m/s = 4.32 km/h; runtime 300 min
# Debut: Introducing Figure 03 — October 09, 2025

PRODUCT = {
    "id": 2502,
    "name": "Figure 03",
    "model_name": "Figure 03",
    "variant_code": "F.03",
    "variant_label": "03",
    "url": PRODUCT_URL,
    "release_year": 2025,
    "weight_kg": 61,
    "height_mm": 1727,
    "payload_kg": 20,
    "speed": 4.32,
    "runtime_minutes": 300,
    "image": HERO,
}


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=120)
        data = r.content or b""
        if r.status_code != 200 or len(data) < 2000:
            return False, "", len(data)
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


def filter_videos() -> list[dict[str, Any]]:
    urls: list[str] = []
    for q in (
        "Figure AI Figure 03",
        "Figure 03 humanoid Helix",
        "Introducing Figure 03",
    ):
        urls.extend(yt_search(q, limit=6))
    seen: set[str] = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    vids = enrich_video_list(uniq)
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        channel = (v.get("channel") or v.get("author_name") or "").lower()
        blob = f"{title} {channel}"
        if "figure 02" in blob and "figure 03" not in blob:
            continue
        if "figure 01" in blob and "figure 03" not in blob:
            continue
        if "figure 03" not in blob and "figure03" not in blob.replace(" ", ""):
            if "figure ai" not in blob:
                continue
        kept.append(v)
    return kept[:3]


def force_en_translations(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"figure-en-force-{rid}-20260720-{loc}",
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


def build_row(used_hashes: set[str]) -> dict[str, Any]:
    spec = PRODUCT
    images: list[str] = []
    ok, md5, nbytes = download_ok(spec["image"])
    if not ok:
        print(f"  !! image fail")
    elif md5 in used_hashes:
        print(f"  !! hash collision {md5[:12]}")
    else:
        used_hashes.add(md5)
        images.append(spec["image"])
        print(f"  img ok {md5[:12]} {nbytes}")

    kept = filter_videos()
    print(f"  videos kept={len(kept)}")
    for v in kept:
        print(f"    - {(v.get('title') or '')[:80]}")

    features = (
        "OEM figure.ai/figure + Introducing Figure 03 (2025-10-09): third-generation "
        "general-purpose humanoid for home and commercial work, redesigned for Helix "
        "VLA and high-volume BotQ manufacturing. Specs on product page: height 5'8\" "
        f"({spec['height_mm']} mm), weight {spec['weight_kg']} kg, payload "
        f"{spec['payload_kg']} kg, runtime 5 hr ({spec['runtime_minutes']} min), "
        f"speed 1.2 m/s ({spec['speed']} km/h), electric system. Soft textiles + "
        "multi-density foam for home safety; 9% less mass than Figure 02; actuators "
        "up to 2× faster with improved torque density; mmWave data offload; "
        "in-torso battery (2.3 kWh class per F.03 battery post). Soft: no public MSRP."
    )
    description = (
        "Figure 03 is Figure AI's third-generation general-purpose humanoid robot, "
        "built for Helix AI, household tasks, and scalable commercial deployment."
    )
    notes = (
        "[AI Research] Figure enrich 2026-07-20. US; Available; family figure:figure; "
        "typed height/weight/payload/speed/runtime from OEM product page; "
        "release_year 2025 from Introducing Figure 03 (2025-10-09)."
    )
    return {
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
        "purpose": "General-purpose humanoid for home and commercial labor",
        "features": features,
        "url": PRODUCT_URL,
        "image": images[0] if images else "",
        "images": images,
        "video_urls": kept,
        "movement_type_keys": "legged",
        "category_slugs": "humanoid",
        "use_keys": "helping|cleaning|manipulation",
        "industry_keys": "household|manufacturing",
        "tags": "Humanoid|Bipedal|Electric|Service|Helix|USA|General-Purpose",
        "source_locale": "en",
        "availability_status": AVAILABLE,
        "family_key": FAMILY_KEY,
        "family_name": FAMILY_NAME,
        "family_url": FAMILY_URL,
        "product_url_scope": "exact_variant",
        "release_year": 2025,
        "weight_kg": spec["weight_kg"],
        "height_mm": spec["height_mm"],
        "payload_kg": spec["payload_kg"],
        "speed": spec["speed"],
        "runtime_minutes": spec["runtime_minutes"],
        "research_notes": notes,
        "sources": [
            {"url": PRODUCT_URL, "type": "website", "title": "Figure 03 product"},
            {"url": INTRO_URL, "type": "press", "title": "Introducing Figure 03 2025-10-09"},
            {
                "url": "https://www.figure.ai/news/f-03-battery-development",
                "type": "press",
                "title": "F.03 battery development",
            },
        ],
        "information_source_urls": [
            PRODUCT_URL,
            INTRO_URL,
            "https://www.figure.ai/news/f-03-battery-development",
        ],
        "notes": notes,
    }


def patch_fields(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": AVAILABLE,
        "name": row["name"],
        "model_name": row["model_name"],
        "variant_code": row["variant_code"],
        "variant_label": row["variant_label"],
        "description": row["description"],
        "features": row["features"],
        "purpose": row["purpose"],
        "url": row["url"],
        "source_locale": "en",
        "notes": row["notes"],
        "family_key": FAMILY_KEY,
        "family_name": FAMILY_NAME,
        "family_url": FAMILY_URL,
        "product_url_scope": "exact_variant",
        "release_year": 2025,
        "weight_kg": row["weight_kg"],
        "height_mm": row["height_mm"],
        "payload_kg": row["payload_kg"],
        "speed": row["speed"],
        "runtime_minutes": row["runtime_minutes"],
        "tags": row["tags"].split("|") if isinstance(row["tags"], str) else row["tags"],
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
    used: set[str] = set()
    print("Building Figure 03...")
    row = build_row(used)
    plan = {
        "company_id": COMPANY_ID,
        "apply": bool(args.apply),
        "robot": {
            "id": 2502,
            "images_n": len(row.get("images") or []),
            "videos_n": len(row.get("video_urls") or []),
            "feat_len": len(row.get("features") or ""),
            "weight_kg": row.get("weight_kg"),
            "payload_kg": row.get("payload_kg"),
            "release_year": row.get("release_year"),
        },
    }

    if not args.apply:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"plan": plan, "row": row}, indent=2), encoding="utf-8")
        print(f"Dry-run -> {REPORT}")
        return 0

    if not row.get("images"):
        print("FAIL CLOSED — no image")
        return 1

    staging = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / "figure-03.json"
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
    print("import:", result)
    patch_fields(client, 2502, row)
    force_en_translations(client, 2502, row)
    if args.copy_media:
        print("copy-media:", copy_media(2502))

    # Re-PATCH soft-required typed columns after import
    client._patch(
        "robots/robots/2502/",
        {
            "availability_status": AVAILABLE,
            "weight_kg": 61,
            "height_mm": 1727,
            "payload_kg": 20,
            "speed": 4.32,
            "runtime_minutes": 300,
            "release_year": 2025,
            "family_key": FAMILY_KEY,
            "family_name": FAMILY_NAME,
            "family_url": FAMILY_URL,
            "s3_image": None,
        },
    )
    print("re-PATCH specs/avail/family ok")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
