"""Curated Knightscope (211) enrich + cleanup.

ENRICH pending_review:
  K5 (3742) — rename from \"K5 Outdoor Patrols\"; replace GSX-banner features junk
  K7 (3743) — replace GSX-banner features junk; OEM marks Under Development

REJECT:
  K1 Hemisphere (3741) — stationary entry-point ECD, not a mobile robot (non_robot)

SKIP create:
  K3 — not on current OEM Force/Arsenal page (K5 covers outdoor; no live K3 PDP)
  K1 towers/capsule — stationary ECD devices
  Signals / H1 ASA — software / human agent platform

Usage:
  python discover_knightscope_robots.py
  python discover_knightscope_robots.py --apply --copy-media
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

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from youtube_metadata import enrich_video_list

COMPANY_ID = 211
COMPANY_SLUG = "knightscope"
COMPANY_NAME = "Knightscope"
US_ID = 20
REPORT = _RESEARCH_DIR / "staging" / "reports" / "knightscope-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

REJECT = [
    {
        "id": 3741,
        "name": "K1 Hemisphere",
        "reason": (
            "non_robot: K1 Hemisphere is a stationary entry-point sensing/ECD device "
            "(OEM Force page), not a mobile autonomous security robot"
        ),
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "K5",
        "id": 3742,
        "action": "enrich",
        "status": "pending_review",
        "rename_from": "K5 Outdoor Patrols",
        "url": "https://knightscope.com/products/k5",
        "model_name": "K5",
        "availability_status": 11,
        "category_slugs": "mobile-robot|service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "security|surveillance|other",
        "industry_keys": "security|commercial|government",
        "tags": (
            "Autonomous|Security|Surveillance|Wheeled|Mobile Robot|Patrol|"
            "Outdoor|Public Safety"
        ),
        # PDF K5V5C: 420 lb; H64.6" W34.9" L44.6"; up to 3 mph
        "weight_kg": 190.5,
        "height_mm": 1641.0,
        "width_mm": 886.0,
        "length_mm": 1133.0,
        "speed": "Up to 3 mph (OEM K5 datasheet)",
        "images": [
            "https://knightscope.com/hubfs/raw_assets/public/knightscope/assets/force/k5_night.jpg",
            "https://knightscope.com/hubfs/KSCP%20Website%20Images/The-Arsenal-k5.jpg",
        ],
        "videos": [
            "https://www.youtube.com/watch?v=DfNUex1SFS8",  # OEM datasheet cite
            "https://www.youtube.com/watch?v=6u5ZoV1WyOw",
        ],
        "video_needles": ["k5", "knightscope"],
        "video_reject": ["drown", "gone wrong", "kills", "removed from", "foiled", "serve robotics"],
        "description": (
            "The Knightscope K5 is an autonomous security robot (ASR) for structured outdoor "
            "patrol — parking lots, campuses, and walkways. It provides visible deterrence with "
            "360° HD video, thermal sensing, license-plate recognition, and two-way audio, "
            "and is listed as available for deployment on Knightscope's Force arsenal page."
        ),
        "features": (
            "Outdoor ASR for parking lots, campuses, and walkways at pedestrian speeds "
            "(OEM Force / products/k5). "
            "360° HD video with thermal imaging; people/device/license-plate detection; "
            "two-way audio and broadcast messaging; quad strobe lights; custom patrol paths "
            "(OEM Force page). "
            "Datasheet K5V5C: height 64.6 in, width 34.9 in, length 44.6 in; weight 420 lb; "
            "speed up to 3 mph; patrol ~2.5–3 h between charges; dock charge ~20–30 min; "
            "operating temp 0–115°F outdoor ambient; 4 HD cameras + IR thermal; 6 LiDAR + "
            "13 sonar; 4G LTE/5G cellular; ADA-compliant ramp navigation up to ~20% grade."
        ),
        "purpose": "Autonomous outdoor security patrol and real-time situational awareness",
        "sources": [
            {"url": "https://knightscope.com/products/k5", "title": "Knightscope Force — K5"},
            {
                "url": "https://knightscope.com/hubfs/K5V5C.pdf?hsLang=en",
                "title": "Knightscope K5 datasheet (K5V5C)",
            },
        ],
    },
    {
        "name": "K7",
        "id": 3743,
        "action": "enrich",
        "status": "pending_review",
        "url": "https://knightscope.com/products/k5",  # Force page hosts K7 under development
        "model_name": "K7",
        "availability_status": 11,
        "category_slugs": "mobile-robot|service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "security|surveillance|other",
        "industry_keys": "security|industrial|commercial|government",
        "tags": (
            "Autonomous|Security|Surveillance|Wheeled|Mobile Robot|Patrol|"
            "Outdoor|Industrial|Off-Road"
        ),
        "speed": "Up to 10 mph (OEM Force page)",
        "images": [
            "https://knightscope.com/hubfs/raw_assets/public/knightscope/assets/force/k7_substation.jpg",
            "https://knightscope.com/hubfs/raw_assets/public/knightscope/assets/photos/k7_united_states.jpg",
        ],
        "videos": [
            "https://www.youtube.com/watch?v=GWTAmTDTmDw",  # may remap — filtered by title
        ],
        "video_queries": [
            "Introducing the Knightscope K7 Autonomous Security Robot",
            "Perimeter Security Robot in Action: Meet the Knightscope K7",
        ],
        "video_needles": ["k7", "knightscope"],
        "video_reject": ["drown", "gone wrong", "kills", "serve robotics", "k5"],
        "description": (
            "The Knightscope K7 is a next-generation autonomous security robot for large outdoor "
            "environments — industrial sites, logistics hubs, and expansive commercial properties. "
            "OEM Force page lists it under development, with light-duty off-road capability and "
            "patrol speeds up to 10 mph."
        ),
        "features": (
            "Next-generation outdoor ASR for large industrial/logistics sites (OEM Force page; "
            "listed Under Development). "
            "Light-duty off-road capability; long-range navigation with speeds up to 10 mph; "
            "360° HD video with PTZ and thermal imaging; advanced detection of people, vehicles, "
            "and license plates; live talk-down capability (OEM Force page). "
            "Designed for continuous autonomous patrol across expansive properties."
        ),
        "purpose": "Large-area outdoor autonomous security patrol for industrial and logistics sites",
        "notes_extra": (
            "[STATUS NOTE] OEM Force page lists K7 under \"Under Development\" "
            "(roadmap subject to change).\n---\n"
        ),
        "sources": [
            {"url": "https://knightscope.com/products/k5", "title": "Knightscope Force — K7 section"},
            {"url": "https://knightscope.com/", "title": "Knightscope home"},
        ],
    },
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=90)
    except Exception:  # noqa: BLE001
        return False, "", 0
    if r.status_code != 200 or len(r.content) < 3000:
        return False, "", 0
    if r.content[:1] == b"<":
        return False, "", 0
    return True, hashlib.md5(r.content).hexdigest(), len(r.content)


def yt_search(query: str, limit: int = 8) -> list[str]:
    html = requests.get(
        "https://www.youtube.com/results",
        params={"search_query": query},
        headers=UA,
        timeout=30,
    ).text
    ids = list(dict.fromkeys(re.findall(r"watch\?v=([\w-]{11})", html)))[:limit]
    return [f"https://www.youtube.com/watch?v={i}" for i in ids]


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


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
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


def filter_videos(spec: dict[str, Any]) -> list[dict[str, Any]]:
    urls = list(spec.get("videos") or [])
    for q in spec.get("video_queries") or []:
        urls.extend(yt_search(q, limit=6))
    # dedupe preserve order
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
        if any(b in title for b in reject):
            continue
        if any(n in title for n in needles):
            # K7: require k7 in title to avoid K5 contamination
            if spec["name"] == "K7" and "k7" not in title:
                continue
            if spec["name"] == "K5" and "k7" in title and "k5" not in title:
                continue
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

    notes = "[AI Research] Knightscope curated enrich 2026-07-19. Rejected K1 Hemisphere (stationary)."
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
        "category_slugs": spec.get("category_slugs") or "mobile-robot",
        "use_keys": spec.get("use_keys") or "security",
        "industry_keys": spec.get("industry_keys") or "security",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or 11,
        "research_notes": (
            "[AI Research] Knightscope 2026-07-19. Cleared GSX marketing scrape from features; "
            "K5 datasheet + Force page; K7 under-development per OEM."
        ),
        "sources": [
            {"url": s["url"], "type": "website", "title": s.get("title") or s["url"]}
            for s in (spec.get("sources") or [{"url": spec["url"]}])
        ],
        "information_source_urls": [s["url"] for s in (spec.get("sources") or [{"url": spec["url"]}])],
        "notes": notes,
    }
    if spec.get("id"):
        row["id"] = spec["id"]
    for k in ("weight_kg", "height_mm", "width_mm", "length_mm", "speed", "release_year"):
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
        "tags": (row.get("tags") or "").split("|") if isinstance(row.get("tags"), str) else row.get("tags"),
    }
    for k in ("weight_kg", "height_mm", "width_mm", "length_mm", "speed", "release_year"):
        if row.get(k) is not None:
            body[k] = row[k]
    try:
        client._patch(f"robots/robots/{rid}/", body)
        print(f"  patched fields {rid}")
    except Exception as e:  # noqa: BLE001
        # tags as list may fail — retry without tags
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
