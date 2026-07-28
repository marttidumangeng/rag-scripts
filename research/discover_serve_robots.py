"""Curated Serve Robotics (252) discovery + enrich.

Existing:
  Serve (286) published — Chinese narrative; features <40; homepage URL; Gen3-looking CDN hero

CREATE pending_review:
  Serve Gen2 — prior-gen sidewalk delivery robot (investor Gen2 column)

ENRICH published:
  Serve Gen3 (rename from Serve / 286) — current Magna-built platform

SKIP:
  Moxi — stays under Diligent Robotics (company 29); Serve acquired Diligent Jan 2026
  Named fleet units (Jamie/Bowen/Sergio/Joel) — unit names, not SKUs

OEM notes (2026-07-19):
  Product page: https://www.serverobotics.com/robot
  Gen3 unveil press 2024-10-16 + investor Gen2/Gen3 table
  Gen3 heroes: GlobeNewswire press stills (labeled third-generation)
  Gen2 hero: crop of labeled Futurride Gen2|Gen3 studio comparison (Sergio) — no Gen2-only OEM still found

Usage:
  python discover_serve_robots.py
  python discover_serve_robots.py --apply --copy-media
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

COMPANY_ID = 252
COMPANY_SLUG = "serve-robotics"
COMPANY_NAME = "Serve Robotics"
US_ID = 20
REPORT = _RESEARCH_DIR / "staging" / "reports" / "serve-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

GEN3_PRESS_A = (
    "https://ml.globenewswire.com/media/071c90f0-2c0d-4d86-afd6-57642231e57a/"
    "small_or_original_size/serve-robotics-third-generation-robot.jpg"
)
GEN3_PRESS_B = (
    "https://ml.globenewswire.com/media/b06e9439-2317-4759-b919-8d1bfb5f12f6/"
    "small_or_original_size/serve-robotics-third-generation-robot.jpg"
)
GEN3_STREET = (
    "https://cdn.sanity.io/images/dh33lj7y/production/"
    "c4edde8256c9e2d9a0822e899c27cf9e5ac3d5c3-8192x5464.jpg"
)
GEN3_STREET2 = (
    "https://cdn.sanity.io/images/dh33lj7y/production/"
    "2f3f598551e073d3e193f22e6ac4fae77772c6f6-8192x5464.jpg"
)

FUTURRIDE_BOTH = (
    "https://futurride.com/wp-content/uploads/2024/10/Serve-Gen-2-left-and-Gen-3-robots.jpg"
)

# Shared curated videos (title-verified Serve Robotics delivery)
VIDEOS = [
    "https://www.youtube.com/watch?v=2Bs9Xuf38Yk",  # Real Robots of Beverly Hills — Serve x Uber Eats
    "https://www.youtube.com/watch?v=n9MJorTjpxU",  # Serve Robotics x Uber Eats delivery experience
    "https://www.youtube.com/watch?v=AYwb3CV-UV4",  # Chicago neighborhoods Uber Eats
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "Serve Gen3",
        "id": 286,
        "action": "enrich",
        "status": "published",
        "rename_from": "Serve",
        "url": "https://www.serverobotics.com/robot",
        "model_name": "Serve Gen3",
        "release_year": 2024,
        "availability_status": 11,
        "category_slugs": "mobile-robot|service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "delivery",
        "industry_keys": "logistics|food-service|commercial",
        "tags": "Autonomous|Delivery|Wheeled|Mobile Robot|Last Mile|Logistics|Service Robot",
        "speed": "11 mph (4.9 m/s)",
        "images": [GEN3_PRESS_A, GEN3_PRESS_B, GEN3_STREET, GEN3_STREET2],
        "videos": VIDEOS,
        "description": (
            "Serve Gen3 is Serve Robotics' third-generation autonomous sidewalk delivery robot, "
            "built for fleet-scale last-mile food and goods delivery on pedestrian paths. "
            "Mass manufacturing with Magna began in late 2024 for Uber Eats deployments across U.S. cities."
        ),
        "features": (
            "Third-generation sidewalk delivery platform unveiled 2024-10-16 (Serve IR press). "
            "Top speed 11 mph (4.9 m/s); operating range about 48 miles / ~14 hours; cargo about 15 gal "
            "(holds 4×16\" pizzas) — Serve investor Gen2/Gen3 table. "
            "Weather envelope about −4–113°F / heavy rain (same investor table). "
            "NVIDIA Jetson Orin onboard compute (~5× prior) + Ouster REV7 digital LiDAR and upgraded "
            "sensor suite (Serve Gen3 press). "
            "Suspension drivetrain, expanded insulated cargo bin, fail-safe mechanical braking and "
            "emergency braking ~40% faster than prior gen (Serve Gen3 press). "
            "Level-4-capable sidewalk autonomy with remote teleop backup for fleet ops (company positioning)."
        ),
        "purpose": "Autonomous last-mile sidewalk delivery of food and small goods",
        "sources": [
            {
                "url": "https://investors.serverobotics.com/news-releases/news-release-details/serve-robotics-rolls-out-third-generation-autonomous-delivery",
                "title": "Serve Gen3 unveil (2024-10-16)",
            },
            {
                "url": "https://ir.serverobotics.com/static-files/d621ad04-0056-40a1-9ea1-c89f5fd8078d",
                "title": "Serve investor presentation (Gen2/Gen3 table)",
            },
            {"url": "https://www.serverobotics.com/robot", "title": "Serve Robotics — Our Robot"},
        ],
    },
    {
        "name": "Serve Gen2",
        "action": "create",
        "status": "pending_review",
        "url": "https://www.serverobotics.com/robot",
        "model_name": "Serve Gen2",
        "availability_status": 11,
        "category_slugs": "mobile-robot|service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "delivery",
        "industry_keys": "logistics|food-service|commercial",
        "tags": "Autonomous|Delivery|Wheeled|Mobile Robot|Last Mile|Logistics|Service Robot",
        "speed": "7 mph (2.5 m/s)",
        # images filled at runtime via litterbox (Gen2 crop) — see ensure_gen2_hero()
        "images": [],
        "need_gen2_temp_hero": True,
        "videos": VIDEOS,
        "description": (
            "Serve Gen2 is Serve Robotics' prior-generation autonomous sidewalk delivery robot, "
            "widely deployed for Uber Eats and merchant partners before Gen3 mass production. "
            "It remains the baseline referenced in Serve's Gen2 vs Gen3 investor comparisons."
        ),
        "features": (
            "Second-generation sidewalk delivery robot (Serve investor Gen2 column). "
            "Top speed 7 mph (2.5 m/s); range about 23 miles / ~10 hours; cargo about 13 gal "
            "(holds 4×14\" pizzas). "
            "Weather envelope about 32–104°F / light rain. "
            "Four-wheel sidewalk chassis with top-loading lockable cargo, rear LiDAR mast, and "
            "expressive LED 'eyes' (OEM/fleet photography). "
            "Level-4-capable sidewalk autonomy with remote teleop backup for fleet ops."
        ),
        "purpose": "Autonomous last-mile sidewalk delivery of food and small goods",
        "sources": [
            {
                "url": "https://ir.serverobotics.com/static-files/d621ad04-0056-40a1-9ea1-c89f5fd8078d",
                "title": "Serve investor presentation (Gen2/Gen3 table)",
            },
            {
                "url": "https://investors.serverobotics.com/news-releases/news-release-details/serve-robotics-rolls-out-third-generation-autonomous-delivery",
                "title": "Serve Gen3 unveil (references prior-gen cargo/performance)",
            },
            {"url": "https://www.serverobotics.com/robot", "title": "Serve Robotics — Our Robot"},
            {
                "url": FUTURRIDE_BOTH,
                "title": "Labeled Gen2 (left) vs Gen3 (right) studio comparison",
            },
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
    if r.content[:1] == b"<" or b"<!DOCTYPE" in r.content[:200]:
        return False, "", 0
    return True, hashlib.md5(r.content).hexdigest(), len(r.content)


def litterbox_upload(data: bytes, filename: str) -> str:
    r = requests.post(
        "https://litterbox.catbox.moe/resources/internals/api.php",
        data={"reqtype": "fileupload", "time": "72h"},
        files={"fileToUpload": (filename, data, "image/jpeg")},
        timeout=120,
        headers={"User-Agent": UA["User-Agent"]},
    )
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise RuntimeError(f"litterbox failed: {url[:200]}")
    return url


def ensure_gen2_hero() -> str:
    """Crop Gen2 (Sergio) from labeled Futurride Gen2|Gen3 still; host for copy-media."""
    cache = _RESEARCH_DIR / "staging" / "tmp" / "serve-heroes" / "gen2_crop_sergio.jpg"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists() or cache.stat().st_size < 5000:
        r = requests.get(FUTURRIDE_BOTH, headers=UA, timeout=90)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        w, h = im.size
        # Left unit = Gen2 (Sergio); keep tight to avoid Gen3 Jamie edge
        crop = im.crop((0, 0, int(w * 0.42), h))
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=92)
        cache.write_bytes(buf.getvalue())
    data = cache.read_bytes()
    url = litterbox_upload(data, "serve-gen2-sergio.jpg")
    print(f"  Gen2 temp hero → {url}")
    return url


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
                return f"HTTP {resp.status_code} {resp.text[:80]}"
        except requests.RequestException as e:
            last = f"ERR {e}"
        time.sleep(2**attempt)
    return "fail"


def force_translation_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    """Clear zh overlay by forcing EN into zh-CN/zh-TW via translation-sync."""
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"serve-en-force-{rid}-20260719-{loc}",
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
        print(f"  translation-sync {rid}: {resp.status_code} {resp.text[:120]}")
    except requests.RequestException as e:
        print(f"  translation-sync warn {rid}: {e}")


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
        print(f"  img ok {md5[:12]} {nbytes} …{u[-55:]}")

    if spec.get("need_gen2_temp_hero") and not images:
        try:
            temp = ensure_gen2_hero()
            ok, md5, nbytes = download_ok(temp)
            if ok and md5 not in seen:
                images.append(temp)
                seen.add(md5)
                print(f"  img ok temp {md5[:12]} {nbytes}")
        except Exception as e:  # noqa: BLE001
            print(f"  !! Gen2 temp hero failed: {e}")

    vids = enrich_video_list(list(spec.get("videos") or []))
    print(f"  videos kept={len(vids)}")
    for v in vids[:3]:
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
        "video_urls": vids[:3],
        "movement_type_keys": spec.get("movement_type_keys") or "wheeled",
        "category_slugs": spec.get("category_slugs") or "mobile-robot",
        "use_keys": spec.get("use_keys") or "delivery",
        "industry_keys": spec.get("industry_keys") or "logistics",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or 11,
        "research_notes": (
            "[AI Research] Serve Robotics discovery 2026-07-19. "
            "Gen3 from IR press + investor table; Gen2 from investor Gen2 column. "
            "Skipped Moxi (Diligent co.29). Skipped named fleet units as SKUs."
        ),
        "sources": [
            {"url": s["url"], "type": "website", "title": s.get("title") or s["url"]}
            for s in (spec.get("sources") or [{"url": spec["url"]}])
        ],
        "information_source_urls": [s["url"] for s in (spec.get("sources") or [{"url": spec["url"]}])],
        "notes": "[AI Research] Serve curated discovery.",
    }
    if spec.get("id"):
        row["id"] = spec["id"]
    if spec.get("release_year"):
        row["release_year"] = spec["release_year"]
    if spec.get("speed"):
        row["speed"] = spec["speed"]
    if not images:
        row["notes"] = (
            "[IMAGE TO-DO — no hero, deliberate]\n"
            f"No verified distinct product still for {spec['name']}.\n"
            "ACTION FOR TEAM: source OEM Gen2-only press kit still.\n"
            "Do NOT use Gen3 press stills or dual-gen comparison as Gen2 hero without crop.\n---\n"
        ) + row["notes"]
    elif spec.get("need_gen2_temp_hero"):
        row["notes"] = (
            "[MEDIA NOTE] Gen2 hero is a crop of the labeled Futurride Gen2|Gen3 studio still "
            "(Sergio / left = Gen2). Prefer replacing with OEM Gen2-only press asset when available.\n---\n"
        ) + row["notes"]
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
    if row.get("release_year"):
        body["release_year"] = row["release_year"]
    if row.get("speed"):
        body["speed"] = row["speed"]
    # Clear uncited height from prior Chinese record
    body["height_mm"] = None
    try:
        client._patch(f"robots/robots/{rid}/", body)
        print(f"  patched fields {rid}")
    except Exception as e:  # noqa: BLE001
        print(f"  patch warn {rid}: {e}")


def find_by_name(client: ResearchApiClient, name: str) -> dict[str, Any] | None:
    for r in client.list_robots_for_company(COMPANY_ID) or []:
        if (r.get("name") or "") == name:
            return r
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--only", default="", help="Comma-separated product names")
    args = ap.parse_args()

    only = {n.strip().lower() for n in args.only.split(",") if n.strip()}
    products = [p for p in PRODUCTS if not only or p["name"].lower() in only]
    if only and not products:
        print(f"No products matched --only={args.only!r}")
        return 1

    staging_dir = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG
    staging_dir.mkdir(parents=True, exist_ok=True)

    client = ResearchApiClient()
    plan: dict[str, Any] = {"company_id": COMPANY_ID, "robots": [], "apply": bool(args.apply)}
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for spec in products:
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
                "image_todo": not bool(row.get("images")),
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
        status = spec.get("status") or "pending_review"
        result = import_staging(
            path,
            dry_run=False,
            patch=bool(spec.get("id")),
            force_overwrite=True,
            replace_media=bool(row.get("images")),
            status=status,
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        rid = spec.get("id")
        if not rid:
            created = find_by_name(client, spec["name"])
            rid = created["id"] if created else None
        if rid:
            patch_fields(client, rid, row)
            force_translation_en(client, rid, row)
            if args.copy_media and row.get("images"):
                cm = copy_media(rid)
                print(f"copy-media {rid}: {cm}")
            for item in plan["robots"]:
                if item["name"] == spec["name"]:
                    item["id"] = rid
                    item["import"] = result

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
