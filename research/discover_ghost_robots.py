"""Curated Ghost Robotics (168) discovery + enrich.

KEEP / ENRICH:
  Vision 60 (207) published — Chinese narrative; OEM specs from /vision-60

REJECT:
  Vision 60 Q-UGV (4955) — duplicate of 207 (same OEM URL)
  Ghost Robotics Spirit 40 (4956) — not on live OEM catalog; aggregator URL;
    historical Spirit 40 existed (Ghost SOU PDF) but no OEM-hosted product page
    or verified hero in this pass → reject discontinued/out-of-catalog

Usage:
  python discover_ghost_robots.py
  python discover_ghost_robots.py --apply --copy-media
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from PIL import Image

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from youtube_metadata import enrich_video_list

COMPANY_ID = 168
COMPANY_SLUG = "ghost-robotics"
COMPANY_NAME = "Ghost Robotics"
US_ID = 20
REPORT = _RESEARCH_DIR / "staging" / "reports" / "ghost-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# OEM Webflow AVIF → wsrv JPEG (stable public URLs for copy-media)
def wsrv(url: str, w: int = 1600) -> str:
    return f"https://wsrv.nl/?url={quote(url, safe='')}&output=jpg&w={w}"


V60_OEM = [
    wsrv(
        "https://cdn.prod.website-files.com/67b418349cd29a4f7829b4a5/67d917d1281ea63102b65004_Images.avif"
    ),
    wsrv(
        "https://cdn.prod.website-files.com/67b418349cd29a4f7829b4a5/67d91652b0261c57f838257a_Images-2.avif"
    ),
    wsrv(
        "https://cdn.prod.website-files.com/67b418349cd29a4f7829b4a5/680bddcd945ccc256a487006_ghost-robotics-slide-3.avif"
    ),
]

VIDEOS = [
    "https://www.youtube.com/watch?v=RdDERZeghR0",  # MILITARY TECH: VISION 60 Q-UGV
    "https://www.youtube.com/watch?v=OQhYJ6I9c1I",  # Vision 60 ice balancing
    "https://www.youtube.com/watch?v=Qi0FGqliGXw",  # Swamp Dog Tyndall AFB
]

REJECT = [
    {
        "id": 4955,
        "name": "Vision 60 Q-UGV",
        "reason": "duplicate: keep Vision 60 (207); same OEM /vision-60 page",
    },
    {
        "id": 4956,
        "name": "Ghost Robotics Spirit 40",
        "reason": (
            "discontinued: Spirit 40 not on live ghostrobotics.io catalog "
            "(only Vision 60); aggregator URL therobotshq; no OEM-hosted hero"
        ),
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "Vision 60",
        "id": 207,
        "action": "enrich",
        "status": "published",
        "url": "https://www.ghostrobotics.io/vision-60",
        "model_name": "Vision 60",
        "availability_status": 11,
        "category_slugs": "quadruped|mobile-robot",
        "movement_type_keys": "legged",
        "use_keys": "inspection|security|research|other",
        "industry_keys": "defense|security|industrial|research",
        "tags": (
            "Quadruped|Autonomous|Legged|Mobile Robot|Defense|Security|"
            "Inspection|All-Terrain|Modular"
        ),
        "weight_kg": 51.0,
        "payload_kg": 10.0,
        "height_mm": 685.0,
        "length_mm": 950.0,
        "width_mm": 570.0,
        "speed": "0.9–2.4 m/s (OEM walk/sprint)",
        "images": V60_OEM,
        "videos": VIDEOS,
        "description": (
            "Vision 60 is Ghost Robotics' flagship Quadrupedal Unmanned Ground Vehicle "
            "(Q-UGV) for defense, public safety, and commercial inspection. "
            "It is an all-electric, IP67 modular platform with field-replaceable legs "
            "and open payload architecture for sensors, CBRN, manipulators, and radios."
        ),
        "features": (
            "Q-UGV quadruped: IP67; operating temp −40°C to 55°C (OEM /vision-60 specs). "
            "Endurance ~3.15 h continuous walking at 0.9 m/s / ~10 km, or ~21 h standby; "
            "~3 h standard charge (OEM specs). "
            "Speed: standard walk 0.9 m/s; fast-walk up to 1.2 m/s; sprint ~2.4 m/s "
            "(OEM specs; marketing also cites up to 2.5 m/s). "
            "Payload 10 kg (22 lb) with payload-compensation mode (OEM). "
            "Key dims: L950 × W570 × H685 mm standing; ride height 419 mm; tare 51 kg (OEM). "
            "Compute NVIDIA Xavier 32 GB; 5× RGB + 4× RealSense D435; dual-antenna RTK GPS (OEM). "
            "Comms: integrated 2.4/5.8 GHz Wi-Fi & 4G/LTE; GigE for external radios (OEM). "
            "Autonomy: perception-aided mobility, record-playback, Mission Control GPS/"
            "GPS-denied modes (OEM). Export EAR-99 / industrial robots HS (OEM)."
        ),
        "purpose": (
            "All-terrain quadruped UGV for defense ISR, perimeter security, "
            "and hazardous-site inspection"
        ),
        "sources": [
            {
                "url": "https://www.ghostrobotics.io/vision-60",
                "title": "Ghost Robotics — Vision 60",
            },
            {"url": "https://www.ghostrobotics.io/", "title": "Ghost Robotics home"},
        ],
    },
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=90)
    except Exception:  # noqa: BLE001
        return False, "", 0
    if r.status_code != 200 or len(r.content) < 2000:
        return False, "", 0
    if r.content[:1] == b"<":
        return False, "", 0
    return True, hashlib.md5(r.content).hexdigest(), len(r.content)


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


def force_translation_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"ghost-en-force-{rid}-20260719-{loc}",
                "translated_fields": {
                    "description": row.get("description") or "",
                    "features": row.get("features") or "",
                    "purpose": row.get("purpose") or "",
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
        print(f"  translation-sync {rid}: {resp.status_code} {resp.text[:100]}")
    except requests.RequestException as e:
        print(f"  translation-sync warn {rid}: {e}")


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    """Prefer admin reject; fall back to research PATCH status=rejected + notes."""
    session = os.environ.get("ADMIN_SESSION_ID", "").strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not api:
        api = os.environ.get("RESEARCH_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if session and api:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
        try:
            resp = requests.post(
                url,
                headers={"Cookie": f"sessionid={session}"},
                json={"reason": reason},
                timeout=60,
            )
            if resp.ok:
                return f"admin-ok {resp.text[:60]}"
            print(f"  admin reject HTTP {resp.status_code}; falling back to PATCH")
        except requests.RequestException as e:
            print(f"  admin reject err {e}; falling back to PATCH")
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "notes": f"[REJECTED 2026-07-19] {reason}\n---\n",
                "rejection_reason": reason[:500],
            },
        )
        return "patched-rejected"
    except Exception as e:  # noqa: BLE001
        return f"fail {e}"


def build_row(spec: dict[str, Any]) -> dict[str, Any]:
    images: list[str] = []
    seen: set[str] = set()
    for u in spec.get("images") or []:
        ok, md5, nbytes = download_ok(u)
        if not ok:
            print(f"  !! image fail {u[:80]}")
            continue
        if md5 in seen:
            continue
        seen.add(md5)
        images.append(u)
        print(f"  img ok {md5[:12]} {nbytes}")

    vids = enrich_video_list(list(spec.get("videos") or []))
    # title gate: must mention vision/ghost
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        if "ghost" in title or "vision 60" in title or "vision-60" in title or "v60" in title:
            kept.append(v)
    print(f"  videos kept={len(kept)}")
    for v in kept[:3]:
        print(f"    - {(v.get('title') or '')[:80]}")

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
        "video_urls": kept[:3],
        "movement_type_keys": spec.get("movement_type_keys") or "legged",
        "category_slugs": spec.get("category_slugs") or "quadruped",
        "use_keys": spec.get("use_keys") or "inspection",
        "industry_keys": spec.get("industry_keys") or "defense",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or 11,
        "research_notes": (
            "[AI Research] Ghost Robotics discovery 2026-07-19. "
            "Live OEM catalog is Vision 60 only; rejected Spirit 40 + Vision 60 Q-UGV dupe."
        ),
        "sources": [
            {"url": s["url"], "type": "website", "title": s.get("title") or s["url"]}
            for s in (spec.get("sources") or [{"url": spec["url"]}])
        ],
        "information_source_urls": [s["url"] for s in (spec.get("sources") or [{"url": spec["url"]}])],
        "notes": "[AI Research] Ghost curated discovery.",
    }
    if spec.get("id"):
        row["id"] = spec["id"]
    for k in (
        "release_year",
        "weight_kg",
        "payload_kg",
        "height_mm",
        "length_mm",
        "width_mm",
        "speed",
    ):
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
    }
    for k in (
        "release_year",
        "weight_kg",
        "payload_kg",
        "height_mm",
        "length_mm",
        "width_mm",
        "speed",
    ):
        if row.get(k) is not None:
            body[k] = row[k]
    try:
        client._patch(f"robots/robots/{rid}/", body)
        print(f"  patched fields {rid}")
    except Exception as e:  # noqa: BLE001
        print(f"  patch warn {rid}: {e}")


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

    for spec in PRODUCTS:
        print(f"Building {spec['name']} ({spec['action']})…")
        row = build_row(spec)
        rows.append((spec, row))
        plan["robots"].append(
            {
                "name": spec["name"],
                "action": spec["action"],
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
            patch=bool(spec.get("id")),
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
            force_translation_en(client, rid, row)
            if args.copy_media and row.get("images"):
                print(f"copy-media {rid}:", copy_media(rid))
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
