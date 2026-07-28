"""Curated Iron Ox (271) enrich — Grover Discontinued.

CONTEXT (2026-07-20):
  Single pending: 2979 Grover — empty features; off-domain therobotshq URL;
  manufacturer country blank; ironox.com is a dead park-page (114 B lander).
  Company ceased produce/ops ~2024 (rebrand Inevitable Tech); Grover not sold.

Cite: Iron Ox PR Newswire launch 2021-11-02 (official company press).
  payload >1000 lb modules → payload_kg=454; 6×6 ft grow modules; LiDAR+cameras.

Usage:
  python discover_ironox_robots.py
  python discover_ironox_robots.py --apply --copy-media
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

COMPANY_ID = 271
COMPANY_SLUG = "iron-ox"
COMPANY_NAME = "Iron Ox"
US_ID = 20
DISCONTINUED = 4
REPORT = _RESEARCH_DIR / "staging" / "reports" / "ironox-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

PR_URL = (
    "https://www.prnewswire.com/news-releases/"
    "iron-ox-launches-grover-an-all-new-autonomous-mobile-robot-301413565.html"
)
AGFUNDER = (
    "https://agfundernews.com/iron-ox-raises-50m-in-breakthrough-energy-led-series-c-round"
)
HERO = "https://cdn.robotaigeek.com/robots/original/robot-2979-grover-v1783651153.jpg"

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 2979,
        "name": "Iron Ox Grover",
        "model_name": "Grover",
        "action": "enrich",
        "status": "pending_review",
        "url": PR_URL,
        "availability_status": DISCONTINUED,
        "category_slugs": "agricultural-robots|autonomous-mobile-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "agriculture|farming",
        "industry_keys": "agriculture",
        "tags": (
            "Agriculture|Greenhouse|AMR|Hydroponic|Discontinued|USA|Indoor"
        ),
        "payload_kg": 454,  # OEM PR: lift more than 1,000 lb modules
        "release_year": 2021,
        "images": [HERO],
        "videos": [],
        "video_queries": [
            "Iron Ox Grover robot",
            "Iron Ox Grover greenhouse",
        ],
        "video_needles": ["iron ox", "grover"],
        "video_reject": ["iron ox forge", "iron ox gym"],
        "description": (
            "Grover was Iron Ox's autonomous mobile greenhouse robot that lifted "
            "and transported ~1,000 lb hydroponic plant modules between growing, "
            "scanning, watering, and harvest stations. Iron Ox ceased commercial "
            "operations; Grover is discontinued / unsupported."
        ),
        "features": (
            "Discontinued greenhouse AMR (Iron Ox PR Newswire launch 2021-11-02). "
            "OEM claimed: lifts more than 1,000 lb (typed payload_kg 454) 6×6 ft "
            "hydroponic plant modules; differential drive; multiple LiDAR; upward "
            "and forward-facing cameras; integrated lift to move modules to a "
            "scanning booth for inspection then watering/nutrients/harvest. "
            "Supported leafy greens to strawberries in Iron Ox CEA facilities "
            "(San Carlos / Gilroy CA; Lockhart TX planned). ironox.com now a dead "
            "park lander; company produce ops ended ~2024 after Inevitable Tech "
            "pivot — record kept historical Discontinued. Replaced aggregator "
            "therobotshq product URL with official PR."
        ),
        "purpose": (
            "Historical autonomous transport of hydroponic grow modules in "
            "Iron Ox greenhouses"
        ),
        "sources": [
            {"url": PR_URL, "title": "Iron Ox launches Grover (PR Newswire, 2021)"},
            {
                "url": AGFUNDER,
                "title": "Iron Ox Series C / facility context (AgFunderNews)",
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
                return f"ok {resp.text[:100]}"
            if resp.status_code not in (502, 503, 504, 500):
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
        if "iron ox" not in blob and "ironox" not in blob:
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
        "[AI Research] Iron Ox Grover 2026-07-20. Discontinued — company dead; "
        "cited PR Newswire launch; removed therobotshq URL."
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
        "availability_status": spec.get("availability_status") or DISCONTINUED,
        "research_notes": (
            "[AI Research] Iron Ox 2026-07-20. Grover Discontinued; PR Newswire "
            "payload/module cites; soft dims (no public L/W/H)."
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
    for k in ("payload_kg", "release_year", "weight_kg", "length_mm", "width_mm", "height_mm"):
        if spec.get(k) is not None:
            row[k] = spec[k]
    return row


def patch_fields(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": row.get("availability_status") or DISCONTINUED,
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
    for k in ("payload_kg", "release_year", "weight_kg", "length_mm", "width_mm", "height_mm"):
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
            replace_media=False,
            status=spec.get("status") or "pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        rid = spec.get("id")
        if rid:
            patch_fields(client, int(rid), row)
            if args.copy_media and row.get("images"):
                img0 = (row.get("images") or [""])[0]
                if f"robot-{rid}-" in img0:
                    print(f"copy-media {rid}: skip (already owned CDN)")
                else:
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
