"""Curated Harvest CROO Robotics (268) enrich.

CONTEXT (2026-07-20):
  Single pending: 4048 Harvest CROO Harvester — empty features, no uses/availability/videos.
  OEM: autonomous B8 strawberry pick-to-pack platform (16 picking robots + LIDAR + AI vision).
  No public typed dims/speed on OEM site → soft no_specs after real pass.
  Replace CV-overlay primary with aerial field hero of the white B8 chassis.

Usage:
  python discover_harvestcroo_robots.py
  python discover_harvestcroo_robots.py --apply --copy-media
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

COMPANY_ID = 268
COMPANY_SLUG = "harvest-croo-robotics"
COMPANY_NAME = "Harvest CROO Robotics"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "harvestcroo-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

TECH_URL = "https://www.harvestcroorobotics.com/technology"
SERVICES_URL = "https://www.harvestcroorobotics.com/services"
PRESS_URL = (
    "https://www.harvestcroorobotics.com/press/"
    "harvest-croo-demonstrates-commercially-viable-automated-robotic-strawberry-harvesting"
)
HERO = (
    "https://cdn.robotaigeek.com/research-staging/harvestcroo/"
    "harvest-croo-b8-aerial-field.webp"
)
GALLERY = (
    "https://cdn.robotaigeek.com/research-staging/harvestcroo/"
    "harvest-croo-b8-picking-modules.webp"
)

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4048,
        "name": "Harvest CROO B8 Harvester",
        "model_name": "B8",
        "action": "enrich",
        "status": "pending_review",
        "url": TECH_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "agricultural-robots|autonomous-mobile-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "agriculture|farming",
        "industry_keys": "agriculture",
        "tags": (
            "Agriculture|Harvesting|Strawberry|Autonomous|AI|Vision|USA|Specialty-crops"
        ),
        "images": [HERO, GALLERY],
        "videos": [],
        "video_queries": [
            "Harvest CROO strawberry harvester",
            "Harvest CROO B8 robotics",
        ],
        "video_needles": ["harvest croo", "harvestcroo", "croo"],
        "video_reject": ["john deere", "farmwise", "carbon robotics", "monarch"],
        "description": (
            "Harvest CROO B8 is a fully autonomous strawberry harvester that "
            "navigates field rows with LIDAR while 16 onboard picking robots use "
            "AI vision to select ripe berries and support pick-to-pack operations."
        ),
        "features": (
            "Autonomous B8 strawberry harvester (OEM harvestcroorobotics.com/"
            "technology + services; Apr 2025 commercial-viability press). Platform "
            "carries 16 independently working picking robots under the chassis. "
            "Harvester-mounted LIDAR provides 360° 3D field views for row "
            "navigation and collision avoidance with plants, people, and "
            "obstacles. AI/ML vision scans each berry for ripeness/health before "
            "picking without damaging fruit. Pick-inspect-clean-pack service model "
            "with ops-center fleet monitoring, plant-level analytics, scheduling, "
            "and autonomous pack/process/reject inspection. Modular/scalable "
            "ecosystem; OEM cites 13+ patents; Florida field trials reported "
            "human-parity picking rates (Wish Farms / Duette). Made in USA "
            "(Tampa HQ). No public typed length/width/height/speed on OEM pages — "
            "left blank after Spec/FAQ/technology pass."
        ),
        "purpose": (
            "Autonomous pick-to-pack strawberry harvesting for commercial growers"
        ),
        "sources": [
            {"url": TECH_URL, "title": "Harvest CROO Technology (OEM)"},
            {"url": SERVICES_URL, "title": "Harvest CROO Harvesting Service (OEM)"},
            {"url": PRESS_URL, "title": "Commercial viability press (OEM, Apr 2025)"},
            {
                "url": "https://www.harvestcroorobotics.com/faq",
                "title": "Harvest CROO FAQ",
            },
        ],
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
                return f"ok {resp.text[:120]}"
            if resp.status_code not in (502, 503, 504, 500):
                return f"HTTP {resp.status_code} {resp.text[:80]}"
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
        if "croo" not in blob and "harvest croo" not in blob:
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
        "[AI Research] Harvest CROO enrich 2026-07-20. Renamed to B8; replaced "
        "CV-overlay hero with aerial field chassis; no public typed dims."
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
        "movement_type_keys": spec.get("movement_type_keys") or "wheeled",
        "category_slugs": spec.get("category_slugs") or "agricultural-robots",
        "use_keys": spec.get("use_keys") or "agriculture",
        "industry_keys": spec.get("industry_keys") or "agriculture",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Harvest CROO 2026-07-20. B8 features from OEM technology/"
            "services/press; soft no_specs (no public dims/speed)."
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
            plan["robots"] = [
                {**x, "import": result} if x.get("id") == rid else x for x in plan["robots"]
            ]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
