"""Curated Realbotix (311) enrich — B / M / F Series.

CONTEXT (2026-07-20):
  3 pending with empty features (4053 B, 4054 F, 4055 M). Aria (5307) already published — skip.
  OEM: realbotix.com/robots — Manufactured in USA (About).
  B-Series: AI bust, 17 DOF / 17 motors. Prior hero was full-body pedestal → replaced with bust.
  M-Series: modular paneled upper body, 39 DOF, suitcase-packable, stationary waist-down.
  F-Series: full body + motorized wheeled base, 44 DOF, battery 4–8 h.

Usage:
  python discover_realbotix_robots.py
  python discover_realbotix_robots.py --apply --copy-media
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

COMPANY_ID = 311
COMPANY_SLUG = "realbotix"
COMPANY_NAME = "Realbotix"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "realbotix-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

ROBOTS_URL = "https://www.realbotix.com/robots"
ABOUT_URL = "https://www.realbotix.com/about"
HOME = "https://www.realbotix.com/"

B_HERO = "https://cdn.robotaigeek.com/research-staging/realbotix/b-series-bust-hero.webp"
M_HERO = "https://cdn.robotaigeek.com/research-staging/realbotix/m-series-seated-hero.webp"
F_HERO = "https://cdn.robotaigeek.com/research-staging/realbotix/f-series-fullbody-hero.jpg"

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4053,
        "name": "Realbotix B-Series",
        "model_name": "B-Series",
        "url": ROBOTS_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "humanoid",
        "movement_type_keys": "stationary",
        "use_keys": "entertainment|helping|reception",
        "industry_keys": "others",
        "tags": "Humanoid|Bust|AI|Companionship|Facial|USA|Stationary",
        "dof": 17,
        "release_year": 2025,  # CES 2025 first public humanoid unveil (BusinessWire)
        "images": [B_HERO],
        "video_queries": ["Realbotix B-Series bust", "Realbotix robotic bust"],
        "video_needles": ["realbotix", "b-series", "bust"],
        "video_reject": ["tesla", "figure ai", "boston dynamics"],
        "description": (
            "Realbotix B-Series is an AI-enabled robotic bust with lifelike silicone "
            "skin and facial actuation for expressions, conversation, and display/"
            "companionship use. Economical entry in the Realbotix lineup."
        ),
        "features": (
            "AI-enabled robotic bust (OEM realbotix.com/robots). Powered by 17 "
            "motors / 17 degrees of freedom for subtle facial expressions. Choose "
            "pre-designed or fully customized face; connects with various AI "
            "platforms including Realbotix proprietary companionship AI. Patented "
            "silicone skin; interchangeable face options on the Realbotix platform. "
            "Homepage list price from $20k+. Manufactured in the USA (OEM About). "
            "Hero replaced: prior full-body pedestal image was wrong form-factor "
            "for a bust — now a shoulders-up bust still."
        ),
        "purpose": "Lifelike AI robotic bust for companionship, reception, and events",
        "sources": [
            {"url": ROBOTS_URL, "title": "Realbotix Robots — B/M/F Series (OEM)"},
            {"url": ABOUT_URL, "title": "Realbotix About — Made in USA"},
            {"url": HOME, "title": "Realbotix home"},
        ],
    },
    {
        "id": 4055,
        "name": "Realbotix M-Series",
        "model_name": "M-Series",
        "url": ROBOTS_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "humanoid",
        "movement_type_keys": "stationary",
        "use_keys": "entertainment|helping|reception",
        "industry_keys": "others",
        "tags": "Humanoid|Modular|AI|Companionship|USA|Stationary",
        "dof": 39,
        "release_year": 2025,
        "images": [M_HERO],
        "video_queries": ["Realbotix M-Series robot", "Realbotix modular robot"],
        "video_needles": ["realbotix", "m-series", "modular"],
        "video_reject": ["tesla", "figure ai", "boston dynamics"],
        "description": (
            "Realbotix M-Series is a modular humanoid with a paneled upper body, "
            "stationary from the waist down, offering broad upper-body motion and "
            "suitcase-packable travel for events and deployments."
        ),
        "features": (
            "Modular paneled-body humanoid (OEM realbotix.com/robots). 39 degrees "
            "of freedom for upper-body movement; stationary waist-down. Designed to "
            "pack in a suitcase for travel. Customizable/interchangeable face and "
            "modular body panels; AI-agnostic + Realbotix companionship AI; iris "
            "micro-cameras for face/voice recognition (platform claims). Homepage "
            "list price from $95k+. Manufactured in the USA."
        ),
        "purpose": "Portable modular humanoid for events, education, and companionship",
        "sources": [
            {"url": ROBOTS_URL, "title": "Realbotix Robots — B/M/F Series (OEM)"},
            {"url": ABOUT_URL, "title": "Realbotix About — Made in USA"},
            {"url": HOME, "title": "Realbotix home"},
        ],
    },
    {
        "id": 4054,
        "name": "Realbotix F-Series",
        "model_name": "F-Series",
        "url": ROBOTS_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "humanoid",
        "movement_type_keys": "wheeled",
        "use_keys": "entertainment|helping|reception",
        "industry_keys": "others",
        "tags": "Humanoid|Wheeled|AI|Companionship|Full-body|USA",
        "dof": 44,
        "runtime_minutes": 240,  # OEM estimated battery life 4–8 hours → cite min
        "release_year": 2025,
        "images": [F_HERO],
        "video_queries": ["Realbotix F-Series robot", "Realbotix full body robot"],
        "video_needles": ["realbotix", "f-series", "full"],
        "video_reject": ["tesla", "figure ai", "boston dynamics"],
        "description": (
            "Realbotix F-Series is the full-bodied flagship humanoid with a "
            "motorized wheeled base and onboard battery, offering 44 DOF for "
            "multi-axis lifelike interaction."
        ),
        "features": (
            "Full-bodied humanoid with motorized wheel base + built-in battery "
            "(OEM realbotix.com/robots). 44 degrees of freedom for simultaneous "
            "multi-part motion. Battery estimated 4–8 hours (typed runtime_minutes "
            "240 as OEM minimum); plug-in or battery operation. Wheeled base "
            "remote-controlled (OEM: only full-bodied model offers this mobility). "
            "Interchangeable face/body panels; AI-agnostic. Homepage list price "
            "from $125k+. Manufactured in the USA. Hero upgraded from tiny CGI "
            "thumb to full-body product still."
        ),
        "purpose": "Full-bodied wheeled humanoid for service, events, and companionship",
        "sources": [
            {"url": ROBOTS_URL, "title": "Realbotix Robots — B/M/F Series (OEM)"},
            {"url": ABOUT_URL, "title": "Realbotix About — Made in USA"},
            {"url": HOME, "title": "Realbotix home"},
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
        if "realbotix" not in blob and "realbot" not in blob:
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
        "[AI Research] Realbotix enrich 2026-07-20. B/M/F from OEM robots page; "
        "fixed B-Series form-factor hero; F-Series runtime min 4 h."
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
        "category_slugs": spec.get("category_slugs") or "humanoid",
        "use_keys": spec.get("use_keys") or "entertainment",
        "industry_keys": spec.get("industry_keys") or "others",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Realbotix 2026-07-20. DOF/runtime from OEM robots page."
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
    for k in ("dof", "runtime_minutes", "payload_kg", "weight_kg", "release_year"):
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
    for k in ("dof", "runtime_minutes", "payload_kg", "weight_kg", "release_year"):
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
        print(f"Building {spec['name']}…")
        row = build_row(spec, used_hashes)
        if not row.get("images"):
            print(f"  !! FAIL CLOSED — no images for {spec['name']}")
        rows.append((spec, row))
        plan["robots"].append(
            {
                "name": spec["name"],
                "id": spec.get("id"),
                "images_n": len(row.get("images") or []),
                "videos_n": len(row.get("video_urls") or []),
                "feat_len": len(row.get("features") or ""),
                "availability": row.get("availability_status"),
                "dof": row.get("dof"),
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
            status="pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        rid = spec.get("id")
        if rid:
            patch_fields(client, int(rid), row)
            if args.copy_media:
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
