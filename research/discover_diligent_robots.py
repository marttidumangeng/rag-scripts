"""Curated Diligent Robotics (29) enrich — Moxi + Moxi 2.0.

CONTEXT (2026-07-20):
  2 pending with Chinese CJK features / short EN. Moxi 2.0 url was a Squarespace
  image CDN path — replace with OEM blog. Soft no public OEM typed dims/weight/
  speed (FAQ + press: human-sized, ~4 ft, rising pillar; RaaS only).

ENRICH:
  58 Moxi — Available; hospital mobile manipulator (fleet gen)
  412 Moxi 2.0 — Available (unveiled 2025-10-28; NVIDIA IGX Thor / 10x compute)

Heroes staged to research-staging/diligent/ after visual QA.

Usage:
  python discover_diligent_robots.py
  python discover_diligent_robots.py --apply --copy-media
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

COMPANY_ID = 29
COMPANY_SLUG = "diligent-robotics"
COMPANY_NAME = "Diligent Robotics"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "diligent-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

MOXI_URL = "https://www.diligentrobots.com/moxi"
HOME = "https://www.diligentrobots.com/"
FAQ = "https://www.diligentrobots.com/faq"
MOXI2_BLOG = "https://www.diligentrobots.com/blog/moxi2-0"
SERVE_ACQUIRE = (
    "https://www.diligentrobots.com/blog/"
    "serve-robotics-to-acquire-diligent-robotics-expanding-physical-ai"
)

MOXI_HERO = (
    "https://cdn.robotaigeek.com/research-staging/diligent/moxi-studio-hero.jpg"
)
MOXI2_HERO = (
    "https://cdn.robotaigeek.com/research-staging/diligent/moxi2-studio-hero.jpg"
)

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 58,
        "name": "Diligent Moxi",
        "model_name": "Moxi",
        "action": "enrich",
        "status": "pending_review",
        "url": MOXI_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "delivery|helping|transport",
        "industry_keys": "healthcare",
        "tags": "Healthcare|Hospital|Delivery|Mobile Manipulator|Wheeled|USA|RaaS",
        "release_year": 2020,
        "images": [MOXI_HERO],
        "video_queries": [
            "Diligent Robotics Moxi hospital",
            "Moxi robot nurse delivery",
        ],
        "video_needles": ["moxi", "diligent"],
        "video_reject": ["serve robotics gen", "tesla", "figure ai"],
        "description": (
            "Moxi is Diligent Robotics' hospital mobile manipulator that runs "
            "routine non-patient-facing logistics — medications, lab samples, "
            "PPE, and supplies — so clinical staff can stay with patients."
        ),
        "features": (
            "OEM diligentrobots.com/moxi + FAQ: wheeled mobile manipulator with "
            "socially expressive LED face, single arm + gripper, locking storage "
            "compartments, and autonomous dock charging (no manual plug-in). "
            "Navigates existing hospital Wi-Fi / elevators / doors without "
            "building retrofits. Staff-requested and point-to-point deliveries; "
            "meeps + heart-eye expressions for hallway awareness. Offered as "
            "robot-as-a-service (RaaS), not a one-time SKU sale. Deployed fleet: "
            "OEM cites 25+ U.S. hospitals and 1.25M+ deliveries (Moxi 2.0 launch "
            "blog, 2025-10-28). Soft: no public OEM typed L/W/H/weight/speed "
            "table — press describes human-sized / ~4 ft with rising pillar; "
            "prior DB height_mm=1650 cleared as uncited. EN features replace "
            "CJK auto-research stub. Hero: OEM Squarespace studio still."
        ),
        "purpose": "Hospital mobile manipulator for clinical logistics deliveries",
        "sources": [
            {"url": MOXI_URL, "title": "Diligent Moxi product page"},
            {"url": FAQ, "title": "Diligent FAQ — capabilities / RaaS"},
            {"url": HOME, "title": "Diligent Robotics home"},
        ],
        "clear_height": True,
    },
    {
        "id": 412,
        "name": "Diligent Moxi 2.0",
        "model_name": "Moxi 2.0",
        "action": "enrich",
        "status": "pending_review",
        "url": MOXI2_BLOG,
        "availability_status": AVAILABLE,
        "category_slugs": "service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "delivery|helping|transport",
        "industry_keys": "healthcare",
        "tags": (
            "Healthcare|Hospital|Delivery|Mobile Manipulator|Wheeled|USA|AI|NVIDIA"
        ),
        "release_year": 2025,
        "images": [MOXI2_HERO],
        "video_queries": [
            "Diligent Moxi 2.0",
            "Moxi 2.0 NVIDIA Thor Diligent",
        ],
        "video_needles": ["moxi", "diligent"],
        "video_reject": ["serve robotics gen2", "tesla", "figure ai"],
        "description": (
            "Moxi 2.0 is Diligent's next-generation hospital mobile manipulator, "
            "unveiled October 28, 2025 with redesigned hardware and ~10x onboard "
            "AI compute on NVIDIA IGX Thor for denser navigation and manipulation."
        ),
        "features": (
            "OEM launch blog diligentrobots.com/blog/moxi2-0 (2025-10-28): next-"
            "gen hardware hardened for manufacturing scale; NVIDIA IGX Thor / "
            "Blackwell edge AI (~10x compute vs Moxi 1.0); proprietary stack + "
            "robot foundation model for dense navigation and high-precision "
            "manipulation; improved physical handles / service panels from "
            "hospital feedback (larger curved drawers, bumpers — Statesman/"
            "OEM narrative). Targets denser per-site fleets (15+ units) and "
            "senior-living expansion. Soft: no public OEM typed dims/weight/"
            "speed on launch page. Product URL fixed from broken Squarespace "
            "image path to OEM blog. Hero: OEM Moxi 2.0 studio still from "
            "launch assets (distinct from gen-1 tablet-chest hero)."
        ),
        "purpose": "Next-gen AI hospital mobile manipulator for scaled clinical logistics",
        "sources": [
            {"url": MOXI2_BLOG, "title": "Diligent unveils Moxi 2.0 (OEM blog)"},
            {"url": HOME, "title": "Diligent Robotics home"},
            {"url": FAQ, "title": "Diligent FAQ"},
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
        if "moxi" not in blob and "diligent" not in blob:
            continue
        kept.append(v)
    return kept[:3]


def force_en_translations(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    """Clear zh overlay by forcing EN into zh-CN/zh-TW via translation-sync."""
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"diligent-en-force-{rid}-20260720-{loc}",
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
        "[AI Research] Diligent enrich 2026-07-20. Replaced CJK stubs with OEM EN; "
        "Moxi 2.0 URL fixed to launch blog; soft no OEM typed dims; Available RaaS."
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
        "category_slugs": spec.get("category_slugs") or "service-robots",
        "use_keys": spec.get("use_keys") or "delivery",
        "industry_keys": spec.get("industry_keys") or "healthcare",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Diligent 2026-07-20. Specs soft-absent (no OEM table); "
            "Moxi 2020 / Moxi 2.0 2025 from OEM narrative + launch blog."
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
        "dof",
    ):
        if spec.get(k) is not None:
            row[k] = spec[k]
    if spec.get("clear_height"):
        row["_clear_height"] = True
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
        "dof",
    ):
        if row.get(k) is not None:
            body[k] = row[k]
    if row.get("_clear_height"):
        body["height_mm"] = None
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
                "release_year": row.get("release_year"),
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

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
