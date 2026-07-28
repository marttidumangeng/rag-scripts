"""Curated FarmWise (263) discover + enrich.

CONTEXT (2026-07-20):
  Live OEM catalog is Vulcan AI weeding *implement* only (farmwise.io/products).
  Titan autonomous weeder is off live catalog (already Discontinued on 2763).

REJECT:
  459 Vulcan Precision Weeding System — Chinese CJK shell; dupe of Vulcan 2762
  456 Titan Autonomous Weeding Robot — Chinese CJK shell; dupe of Titan 2763

ENRICH:
  2762 Vulcan — Available; OEM flyer 2025 specs; farmwise.io/products
  2763 Titan FT-35 — Discontinued; replace WRONG Carbon Robotics LaserWeeder
    CDN hero with genuine FarmWise Titan field photo (from former 456 gallery)

Usage:
  python discover_farmwise_robots.py
  python discover_farmwise_robots.py --apply --copy-media
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

COMPANY_ID = 263
COMPANY_SLUG = "farmwise"
COMPANY_NAME = "FarmWise"
US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4
REPORT = _RESEARCH_DIR / "staging" / "reports" / "farmwise-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

VULCAN_URL = "https://farmwise.io/products"
VULCAN_FLYER = "https://farmwise.io/assets/downloads/FarmWise_Vulcan_Flyer_2025.pdf"
VULCAN_HERO = "https://farmwise.io/assets/images/vulcan-3-bed-machine.webp"
VULCAN_GALLERY = "https://farmwise.io/assets/images/feature-1.webp"
# Genuine FarmWise Titan field shot (bytes from former 456 gallery); staged so
# copy-media can mint a robot-2763 owned path (same-CDN robot_456 URL 500s).
TITAN_HERO = (
    "https://cdn.robotaigeek.com/research-staging/farmwise/"
    "farmwise-titan-ft35-field.jpg"
)

REJECT = [
    {
        "id": 459,
        "name": "Vulcan Precision Weeding System",
        "reason": (
            "duplicate_of_2762: Chinese CJK feature shell of FarmWise Vulcan; "
            "keep Vulcan (2762) as canonical EN OEM record."
        ),
    },
    {
        "id": 456,
        "name": "Titan Autonomous Weeding Robot",
        "reason": (
            "duplicate_of_2763: Chinese CJK feature shell of FarmWise Titan; "
            "keep Titan FT-35 (2763) Discontinued as canonical (hero corrected)."
        ),
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 2762,
        "name": "FarmWise Vulcan",
        "action": "enrich",
        "status": "pending_review",
        "url": VULCAN_URL,
        "model_name": "Vulcan",
        "availability_status": AVAILABLE,
        "category_slugs": "agricultural-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "agriculture|farming",
        "industry_keys": "agriculture",
        "tags": (
            "Agriculture|Weeding|AI|Vision|Implement|Tractor|USA|Precision"
        ),
        "speed": 6.44,  # OEM flyer max 4 mph → km/h
        "images": [VULCAN_HERO, VULCAN_GALLERY],
        "videos": [],
        "video_queries": [
            "FarmWise Vulcan weeding",
            "FarmWise Vulcan AI weeder",
        ],
        "video_needles": ["farmwise", "vulcan"],
        "video_reject": ["titan", "carbon robotics", "laserweeder", "john deere see"],
        "description": (
            "FarmWise Vulcan is an AI precision weeding and cultivation implement "
            "for specialty crops. Tractor-pulled modular beds use computer vision "
            "and high-speed actuators to remove weeds at millimeter precision while "
            "protecting the crop."
        ),
        "features": (
            "AI precision weeding/cultivation implement (OEM farmwise.io/products + "
            "Vulcan Flyer 2025). OEM claims: covers 3–4+ acres/hour; weeds 25+ "
            "acres/day; operates 1.5–4 mph (typed speed 6.44 km/h max); 45+ crop "
            "types; millimeter precision; 24/7 edge learning / OTA updates. "
            "Brighter-than-sun lighting + high-frame-rate vision; in-cab interface; "
            "high-speed actuators; optional cultivation/bottom-breaking tooling "
            "mounts. Models include V380 / T380 / V368 / V440 bed configs. Sold/"
            "supported with RDO Equipment; financing via AgDirect / John Deere "
            "Financing. Made in USA."
        ),
        "purpose": "Tractor-mounted AI mechanical weeding and cultivation for specialty crops",
        "sources": [
            {"url": VULCAN_URL, "title": "FarmWise Products — Vulcan (OEM)"},
            {"url": VULCAN_FLYER, "title": "FarmWise Vulcan Flyer 2025 (OEM PDF)"},
            {"url": "https://farmwise.io/", "title": "FarmWise home"},
        ],
    },
    {
        "id": 2763,
        "name": "FarmWise Titan FT-35",
        "action": "enrich",
        "status": "pending_review",
        "url": "https://farmwise.io/",
        "model_name": "Titan FT-35",
        "availability_status": DISCONTINUED,
        "category_slugs": "agricultural-robots|autonomous-mobile-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "agriculture|farming",
        "industry_keys": "agriculture",
        "tags": (
            "Agriculture|Weeding|AI|Autonomous|Discontinued|Wheeled|USA"
        ),
        "images": [TITAN_HERO],
        "videos": [],
        "video_queries": [
            "FarmWise Titan autonomous weeding",
            "FarmWise Titan FT-35 robot",
        ],
        "video_needles": ["farmwise", "titan"],
        "video_reject": ["vulcan", "carbon robotics", "laserweeder"],
        "description": (
            "FarmWise Titan FT-35 was FarmWise's autonomous field weeding robot "
            "(plant-level AI detection and navigation). Superseded on the live OEM "
            "site by the Vulcan tractor implement; treated as discontinued."
        ),
        "features": (
            "Discontinued autonomous weeding AMR (historical FarmWise Titan / "
            "FT-35 line). Prior marketing cited AI crop-vs-weed detection, "
            "plant-level precision, autonomous navigation, and large-scale field "
            "operation. Live OEM catalog (2025) promotes Vulcan implement only — "
            "no Titan PDP. Replaced contaminated CDN hero that depicted a "
            "Carbon Robotics–style laser weeder with a verified FarmWise-branded "
            "Titan field photo."
        ),
        "purpose": "Historical autonomous robotic weeding for specialty crop fields",
        "sources": [
            {"url": "https://farmwise.io/", "title": "FarmWise home (Vulcan era)"},
            {"url": VULCAN_URL, "title": "Current OEM products (Vulcan)"},
        ],
        "notes_extra": (
            "[IMAGE FIXED 2026-07-20] Prior primary was wrong-brand orange "
            "laser-weeder (Carbon-like). Replaced with FarmWise Titan field still.\n"
        ),
    },
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=120)
        data = r.content
        if r.status_code != 200 or len(data) < 2000:
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


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "notes": f"[REJECTED 2026-07-20] {reason}\n---\n",
                "rejection_reason": reason[:500],
            },
        )
        return "patched-rejected"
    except Exception as e:  # noqa: BLE001
        return f"fail {e}"


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
    needles = [n.lower() for n in (spec.get("video_needles") or [])]
    reject = [b.lower() for b in (spec.get("video_reject") or [])]
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        channel = (v.get("channel") or v.get("author_name") or "").lower()
        blob = f"{title} {channel}"
        if any(b in blob for b in reject):
            continue
        if needles and not any(n in blob for n in needles):
            continue
        if "farmwise" not in blob:
            continue
        kept.append(v)
    return kept[:3]


def build_row(spec: dict[str, Any], used_hashes: set[str]) -> dict[str, Any]:
    images: list[str] = []
    for u in spec.get("images") or []:
        ok, md5, nbytes = download_ok(u)
        if not ok:
            print(f"  !! image fail {u[:90]}")
            continue
        if md5 in used_hashes:
            print(f"  !! skip cross-robot hash {md5[:12]}")
            continue
        used_hashes.add(md5)
        images.append(u)
        print(f"  img ok {md5[:12]} {nbytes}")

    kept = filter_videos(spec)
    print(f"  videos kept={len(kept)}")
    for v in kept:
        print(f"    - {(v.get('title') or '')[:80]}")

    notes = (
        "[AI Research] FarmWise curated discover 2026-07-20. "
        "Rejected Chinese Vulcan/Titan dupes; fixed Titan wrong-brand hero; "
        "Vulcan from OEM flyer 2025."
    )
    if spec.get("notes_extra"):
        notes = spec["notes_extra"] + notes

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
        "movement_type_keys": spec.get("movement_type_keys") or "wheeled",
        "category_slugs": spec.get("category_slugs") or "agricultural-robots",
        "use_keys": spec.get("use_keys") or "agriculture",
        "industry_keys": spec.get("industry_keys") or "agriculture",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] FarmWise 2026-07-20. Vulcan specs from OEM 2025 flyer; "
            "Titan discontinued / off live catalog; Carbon-lookalike hero purged."
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
    for k in (
        "weight_kg",
        "height_mm",
        "width_mm",
        "length_mm",
        "speed",
        "release_year",
        "payload_kg",
        "runtime_minutes",
        "charging_time_minutes",
        "dof",
    ):
        if spec.get(k) is not None:
            row[k] = spec[k]
    return row


def patch_fields(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": row.get("availability_status") or AVAILABLE,
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
    for k in (
        "weight_kg",
        "height_mm",
        "width_mm",
        "length_mm",
        "speed",
        "release_year",
        "payload_kg",
        "runtime_minutes",
        "charging_time_minutes",
        "dof",
    ):
        if row.get(k) is not None:
            body[k] = row[k]
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
        "rejects": REJECT,
        "apply": bool(args.apply),
    }
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    used_hashes: set[str] = set()

    for spec in PRODUCTS:
        print(f"Building {spec['name']} ({spec['action']})…")
        row = build_row(spec, used_hashes)
        if not row.get("images"):
            print(f"  !! FAIL CLOSED — no images for {spec['name']}")
        rows.append((spec, row))
        plan["robots"].append(
            {
                "name": spec["name"],
                "id": spec.get("id"),
                "action": spec["action"],
                "images_n": len(row.get("images") or []),
                "videos_n": len(row.get("video_urls") or []),
                "feat_len": len(row.get("features") or ""),
                "availability": row.get("availability_status"),
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
        if not row.get("images"):
            print(f"SKIP apply {spec['name']} — no verified images")
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
            status=spec.get("status") or "pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        rid = spec.get("id")
        if rid:
            patch_fields(client, int(rid), row)
            if args.copy_media and row.get("images"):
                print(f"copy-media {rid}:", copy_media(int(rid)))
            for item in plan["robots"]:
                if item["name"] == spec["name"]:
                    item["id"] = rid
                    item["import"] = result

    for rej in REJECT:
        print(f"Rejecting {rej['id']} {rej['name']}…")
        out = reject_robot(client, int(rej["id"]), rej["reason"])
        print(f"  → {out}")
        rej["result"] = out

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
