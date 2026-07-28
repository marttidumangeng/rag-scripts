"""Curated Stryker (350) enrich — Mako 4 + Total Knee / Hip / Partial Knee apps.

CONTEXT (2026-07-20):
  4 pending with empty features, missing US country, stale Released availability,
  polluted tags. Three apps shared one identical 12MB family PNG hash.
  Published MAKO SmartRobotics (225) left alone (CJK) unless stakeholder asks.

KEEP / ENRICH:
  4308 Mako 4 System — 4th-gen platform (OEM overview + Mako 4 PDF)
  2385 Mako SmartRobotics Total Knee — US PDP
  2386 Mako SmartRobotics Total Hip — US PDP (Advanced Primary/Revision on Mako 4)
  3288 Mako SmartRobotics Partial Knee — US PDP

Heroes (unique md5):
  research-staging/stryker/mako4-family-hero.jpg
  research-staging/stryker/mako-total-knee-hero.jpg
  research-staging/stryker/mako-total-hip-hero.jpg
  research-staging/stryker/mako-partial-knee-hero.jpg

Soft: cart typed specs from OEM Mako Technical User Guide Table 1
(Model 3.11x.x Mako arm column): 394 kg; 610×889×1423 mm storage; 6 DOF.

Usage:
  python discover_stryker_robots.py
  python discover_stryker_robots.py --apply --copy-media
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

COMPANY_ID = 350
COMPANY_SLUG = "stryker"
COMPANY_NAME = "Stryker"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "stryker-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

OVERVIEW = (
    "https://www.stryker.com/us/en/joint-replacement/systems/"
    "Mako_SmartRobotics_Overview.html"
)
TK_URL = "https://www.stryker.com/us/en/joint-replacement/systems/mako-total-knee.html"
TH_URL = "https://www.stryker.com/us/en/joint-replacement/systems/mako-total-hip.html"
PK_URL = (
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-partial-knee.html"
)
MAKO4_PDF = (
    "https://www.stryker.com/content/dam/stryker/joint-replacement/systems/"
    "mako-spine/JR-MKOSYM-AD-1533699-EN_US.pdf"
)
TECH_GUIDE = "https://cdn.stryker.com/SYKGCSDOC-2-50913"

# OEM Mako Technical User Guide Table 1 — Mako robotic-arm cart column
# (Model 3.11x.x). Storage LxWxH 24x35x56 in; weight 866 lb; arm 6 DOF.
MAKO_CART_SPECS = {
    "weight_kg": 394,
    "length_mm": 610,
    "width_mm": 889,
    "height_mm": 1423,
    "dof": 6,
}

MAKO4_HERO = (
    "https://cdn.robotaigeek.com/research-staging/stryker/mako4-family-hero.jpg"
)
TK_HERO = (
    "https://cdn.robotaigeek.com/research-staging/stryker/mako-total-knee-hero.jpg"
)
TH_HERO = (
    "https://cdn.robotaigeek.com/research-staging/stryker/mako-total-hip-hero.jpg"
)
PK_HERO = (
    "https://cdn.robotaigeek.com/research-staging/stryker/mako-partial-knee-hero.jpg"
)

COMMON_TAGS = (
    "Surgical Robot|Healthcare|Orthopedics|Stationary|USA|Medical Robot"
)

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4308,
        "name": "Stryker Mako 4",
        "model_name": "Mako 4",
        "action": "enrich",
        "status": "pending_review",
        "url": OVERVIEW,
        "availability_status": AVAILABLE,
        "category_slugs": "medical-robots",
        "movement_type_keys": "stationary",
        "use_keys": "surgery",
        "industry_keys": "healthcare",
        "tags": COMMON_TAGS + "|Mako 4",
        "weight_kg": 394,
        "length_mm": 610,
        "width_mm": 889,
        "height_mm": 1423,
        "dof": 6,
        "images": [MAKO4_HERO],
        "video_queries": [
            "Stryker Mako 4 SmartRobotics",
            "Stryker Mako 4 system",
        ],
        "video_needles": ["mako", "stryker"],
        "video_reject": ["intuitive", "da vinci", "zimmer", "rosa knee"],
        "description": (
            "Mako 4 is Stryker's fourth-generation Mako SmartRobotics™ system — "
            "one integrated platform for orthopedic robotic-arm assisted "
            "procedures across Total Hip, Total Knee, Partial Knee, Spine, and "
            "Shoulder applications, built around the Q Guidance System hub."
        ),
        "features": (
            "OEM Stryker Mako SmartRobotics Overview + Mako 4 brochure "
            "(JR-MKOSYM-AD-1533699): fourth-generation single system designed "
            "for more applications vs prior gens — Total Hip, Total Knee, "
            "Partial Knee, Spine, and Shoulder on one platform. Integrates "
            "Stryker Q Guidance System (FP8000 camera, multi-specialty "
            "guidance hub) with AccuStop™ haptic technology and 3D CT-based "
            "planning. MICS 3 power tools for bone prep on hip/knee apps; "
            "Copilot depth stop for spine pedicle work. OEM Mako Technical "
            "User Guide Table 1 (Mako robotic-arm cart; Model 3.11x.x): "
            "394 kg; storage 610x889x1423 mm; 6 DOF. Hero: OEM Mako 4 Family "
            "studio still (five-unit gray lineup)."
        ),
        "purpose": (
            "Fourth-generation orthopedic robotic-arm assisted surgery platform"
        ),
        "sources": [
            {"url": OVERVIEW, "title": "Mako SmartRobotics Overview"},
            {"url": MAKO4_PDF, "title": "Mako 4 brochure PDF"},
            {"url": TECH_GUIDE, "title": "Mako Technical User Guide Table 1"},
        ],
    },
    {
        "id": 2385,
        "name": "Stryker Mako Total Knee",
        "model_name": "Mako Total Knee",
        "action": "enrich",
        "status": "pending_review",
        "url": TK_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "medical-robots",
        "movement_type_keys": "stationary",
        "use_keys": "surgery",
        "industry_keys": "healthcare",
        "tags": COMMON_TAGS + "|Knee|Total Knee Arthroplasty",
        "weight_kg": 394,
        "length_mm": 610,
        "width_mm": 889,
        "height_mm": 1423,
        "dof": 6,
        "images": [TK_HERO],
        "video_queries": [
            "Stryker Mako Total Knee SmartRobotics",
            "Mako Total Knee Functional Knee Positioning",
        ],
        "video_needles": ["mako", "total knee", "stryker"],
        "video_reject": ["hip", "partial knee", "intuitive", "zimmer"],
        "description": (
            "Mako Total Knee is Stryker's robotic-arm assisted total knee "
            "arthroplasty application on Mako SmartRobotics™, combining 3D "
            "CT-based planning, dynamic joint balancing, and AccuStop™ haptic "
            "boundaries with Triathlon® implants for Functional Knee "
            "Positioning™."
        ),
        "features": (
            "OEM stryker.com Mako Total Knee (US): 3D CT-based implant "
            "planning, Digital Tensioner for objective ligament assessment, "
            "dynamic joint balancing, and AccuStop™ haptic saw boundaries "
            "that eliminate cutting guides while protecting soft tissue vs "
            "manual blocks. Designed for Functional Knee Positioning™ with "
            "Triathlon. OEM cites 1M+ worldwide Mako Total Knee procedures "
            "and leadership share of Triathlon knees implanted with Mako "
            "(internal sales data). Soft: no public OEM typed cart dims/"
            "weight/speed. Hero: single-unit crop from OEM Mako 4 Family "
            "studio still (distinct hash vs sibling apps)."
        ),
        "purpose": "Robotic-arm assisted total knee arthroplasty (TKA)",
        "sources": [
            {"url": TK_URL, "title": "Mako Total Knee"},
            {"url": OVERVIEW, "title": "Mako SmartRobotics Overview"},
            {"url": TECH_GUIDE, "title": "Mako Technical User Guide Table 1"},
        ],
    },
    {
        "id": 2386,
        "name": "Stryker Mako Total Hip",
        "model_name": "Mako Total Hip",
        "action": "enrich",
        "status": "pending_review",
        "url": TH_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "medical-robots",
        "movement_type_keys": "stationary",
        "use_keys": "surgery",
        "industry_keys": "healthcare",
        "tags": COMMON_TAGS + "|Hip|Total Hip Arthroplasty",
        "weight_kg": 394,
        "length_mm": 610,
        "width_mm": 889,
        "height_mm": 1423,
        "dof": 6,
        "images": [TH_HERO],
        "video_queries": [
            "Stryker Mako Total Hip SmartRobotics",
            "Mako Total Hip Advanced Primary Revision",
        ],
        "video_needles": ["mako", "total hip", "stryker"],
        "video_reject": ["total knee", "partial knee", "intuitive", "zimmer"],
        "description": (
            "Mako Total Hip is Stryker's robotic-arm assisted total hip "
            "arthroplasty application — CT-based Functional Hip Positioning™, "
            "AccuStop™ haptic reaming/cup impaction, and (on Mako 4) Advanced "
            "Primary and Revision planning for complex and revision hips."
        ),
        "features": (
            "OEM stryker.com Mako Total Hip (US): 3D CT planning with pelvic "
            "tilt / range-of-motion impingement analysis, single-stage "
            "reaming constrained to planned center of rotation, and AccuStop™ "
            "haptic cup impaction. Mako Total Hip with Advanced Primary and "
            "Revision (Mako 4 only) adds screw/augment planning, Restoration® "
            "Modular stem planning, bone mapping, and robotic-assisted "
            "augment/cup reaming — first-to-market robotically enabled "
            "revision hip on Mako per OEM. Soft: no public OEM typed cart "
            "dims/weight/speed. Hero: single-unit crop from OEM Mako 4 "
            "Family studio still (distinct hash vs siblings)."
        ),
        "purpose": "Robotic-arm assisted total hip arthroplasty (THA)",
        "sources": [
            {"url": TH_URL, "title": "Mako Total Hip"},
            {"url": OVERVIEW, "title": "Mako SmartRobotics Overview"},
            {"url": TECH_GUIDE, "title": "Mako Technical User Guide Table 1"},
        ],
    },
    {
        "id": 3288,
        "name": "Stryker Mako Partial Knee",
        "model_name": "Mako Partial Knee",
        "action": "enrich",
        "status": "pending_review",
        "url": PK_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "medical-robots",
        "movement_type_keys": "stationary",
        "use_keys": "surgery",
        "industry_keys": "healthcare",
        "tags": COMMON_TAGS + "|Knee|Partial Knee Arthroplasty",
        "weight_kg": 394,
        "length_mm": 610,
        "width_mm": 889,
        "height_mm": 1423,
        "dof": 6,
        "images": [PK_HERO],
        "video_queries": [
            "Stryker Mako Partial Knee SmartRobotics",
            "Mako Partial Knee arthroplasty",
        ],
        "video_needles": ["mako", "partial knee", "stryker"],
        "video_reject": ["total knee", "total hip", "intuitive", "zimmer"],
        "description": (
            "Mako Partial Knee is Stryker's robotic-arm assisted partial knee "
            "arthroplasty application on Mako SmartRobotics™, enabling "
            "intraoperative soft-tissue tensioning and AccuStop™ haptic "
            "bone prep toward natural knee kinematics."
        ),
        "features": (
            "OEM stryker.com Mako Partial Knee (US): dynamically balance soft "
            "tissue tensioning intraoperatively with the goal of recreating "
            "natural knee kinematics; AccuStop™ haptic technology to reduce "
            "damage to surrounding soft tissue vs manual; component placement "
            "guided to 3D patient-specific preoperative plans. Soft: no "
            "public OEM typed cart dims/weight/speed on PDP. Hero: single-"
            "unit crop from OEM Mako 4 Family studio still (distinct hash)."
        ),
        "purpose": "Robotic-arm assisted partial knee arthroplasty (PKA)",
        "sources": [
            {"url": PK_URL, "title": "Mako Partial Knee"},
            {"url": OVERVIEW, "title": "Mako SmartRobotics Overview"},
            {"url": TECH_GUIDE, "title": "Mako Technical User Guide Table 1"},
        ],
    },
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=90)
        data = r.content or b""
        if r.status_code != 200 or len(data) < 1000:
            return False, "", len(data)
        if data[:3] != b"\xff\xd8\xff" and data[:8] != b"\x89PNG\r\n\x1a\n":
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
        if "mako" not in blob and "stryker" not in blob:
            continue
        kept.append(v)
    return kept[:3]


def force_en_translations(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"stryker-en-force-{rid}-20260720-{loc}",
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
    for u in spec.get("images") or []:
        ok, md5, nbytes = download_ok(u)
        if not ok:
            print(f"  !! image fail {u[:90]}")
            continue
        if md5 in used_hashes:
            print(f"  !! skip cross-robot hash {md5[:12]} — {u[-40:]}")
            continue
        used_hashes.add(md5)
        images.append(u)
        print(f"  img ok {md5[:12]} {nbytes}")

    kept = filter_videos(spec)
    print(f"  videos kept={len(kept)}")
    for v in kept:
        print(f"    - {(v.get('title') or '')[:80]}")

    notes = (
        "[AI Research] Stryker enrich 2026-07-20. EN features from US OEM PDPs; "
        "replaced shared identical CDN hero hash across apps; Available; US; "
        "typed cart specs from OEM Mako Technical User Guide Table 1 "
        f"(Model 3.11x.x): 394 kg; 610x889x1423 mm; 6 DOF. {TECH_GUIDE}"
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
        "category_slugs": spec.get("category_slugs") or "medical-robots",
        "use_keys": spec.get("use_keys") or "surgery",
        "industry_keys": spec.get("industry_keys") or "healthcare",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Stryker 2026-07-20. Cart specs from tech guide "
            f"Table 1; availability Available; country US. {TECH_GUIDE}"
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
    for k in ("weight_kg", "length_mm", "width_mm", "height_mm", "dof", "payload_kg", "speed"):
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
        "s3_image": None,
    }
    for k in ("weight_kg", "length_mm", "width_mm", "height_mm", "dof", "payload_kg", "speed"):
        if row.get(k) is not None:
            body[k] = row[k]
    try:
        client._patch(f"robots/robots/{rid}/", body)
        print(f"  patched fields {rid}")
    except Exception as e:  # noqa: BLE001
        # tags sometimes reject unknown catalog names
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
    used_hashes: set[str] = set()

    for spec in PRODUCTS:
        print(f"Building {spec['name']} ({spec['action']})...")
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
        print(f"Dry-run -> {REPORT}")
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
            force_en_translations(client, int(rid), row)
            if args.copy_media and row.get("images"):
                print(f"copy-media {rid}:", copy_media(int(rid)))
            for item in plan["robots"]:
                if item["name"] == spec["name"]:
                    item["id"] = rid
                    item["import"] = result

    # Re-PATCH availability after bulk-import (can wipe)
    for spec, _row in rows:
        rid = spec.get("id")
        if not rid:
            continue
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {"availability_status": AVAILABLE, "s3_image": None},
            )
            print(f"  re-PATCH avail {rid}")
        except Exception as e:  # noqa: BLE001
            print(f"  re-PATCH warn {rid}: {e}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
