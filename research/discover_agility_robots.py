"""Discover + enrich Agility Robotics (9).

Catalog reality (OEM 2026-07-19):
  KEEP / CREATE:
    - Cassie — research biped predecessor (pending_review)
  ENRICH (published):
    - Digit (11) — Chinese narrative → English; fill uses/country/tags; OEM Digit photos
  SKIP (not separate SKUs / phantoms):
    - Digit V1, Digit v5 (generations of Digit)
    - Humanoid Robot (generic FAQ shell)
    - Arc (cloud software)

Usage:
  python discover_agility_robots.py
  python discover_agility_robots.py --apply --copy-media
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from youtube_metadata import enrich_video_list

COMPANY_ID = 9
COMPANY_SLUG = "agility-robotics"
COMPANY_NAME = "Agility Robotics"
US_COUNTRY_ID = 20
DIGIT_ID = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "agility-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

URL_SOLUTIONS = "https://www.agilityrobotics.com/solutions"
URL_COMPANY = "https://www.agilityrobotics.com/company"
URL_DIGIT_LAUNCH = (
    "https://www.agilityrobotics.com/content/"
    "agility-robotics-launches-next-generation-of-digit-worlds-first-human-centric-"
    "multi-purpose-robot-made-for-logistics-work"
)
URL_DIGIT_MEET = (
    "https://www.agilityrobotics.com/content/meet-digit-the-newest-robot-from-agility-robotics"
)
URL_CASSIE_100M = "https://www.agilityrobotics.com/videos/cassie-sets-world-record-for-100m-run"

DIGIT_HERO = (
    "https://cdn.prod.website-files.com/68d6ca150ffa11fdc25d7575/"
    "699fdc15e860d79128b81476_Agility_Digit_08.jpg"
)
DIGIT_GALLERY = [
    DIGIT_HERO,
    "https://cdn.prod.website-files.com/68d6ca150ffa11fdc25d7575/"
    "699fdc15d1e9e4e839c2963f_Agility_Digit_06.jpg",
]

DIGIT_VIDEOS = [
    "https://www.youtube.com/watch?v=AJpTpUqjgrY",  # Digit First Day at GXO
    "https://www.youtube.com/watch?v=wE_XDbkVOp0",  # Modex warehousing demo
    "https://www.youtube.com/watch?v=2zCh_6GO49c",  # ProMat 2023 TechCrunch
]
CASSIE_VIDEOS = [
    "https://www.youtube.com/watch?v=X9CUJcodFHk",  # Cassie 100M record
    "https://www.youtube.com/watch?v=gQ4UUUvypJg",  # OSU Guinness 100m
    "https://www.youtube.com/watch?v=DS18SeuMqtA",  # Cassies tour Agility
]

TAGS_DIGIT = "Humanoid|Bipedal|Logistics|Warehouse Automation|Autonomous|Material Handling|Industrial"
TAGS_CASSIE = "Bipedal|Research|Legged|Locomotion|Research Platform|Autonomous"


def download_ok(url: str, *, min_bytes: int = 8000) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, timeout=45, headers=UA)
        data = r.content
        if r.status_code != 200 or len(data) < min_bytes:
            return False, "", len(data)
        if not (
            data[:3] == b"\xff\xd8\xff"
            or data[:8].startswith(b"\x89PNG")
            or data[:4] == b"RIFF"
        ):
            return False, "", len(data)
        return True, hashlib.md5(data).hexdigest(), len(data)
    except requests.RequestException:
        return False, "", 0


def copy_media(rid: int, *, attempts: int = 5) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return "no-secret"
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    last = "ERR"
    for attempt in range(attempts):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return "ok"
            last = f"HTTP {resp.status_code}"
            if resp.status_code not in (502, 503, 504):
                return last
        except requests.RequestException as e:
            last = f"ERR {e}"
        time.sleep(2**attempt)
    return last


def build_digit_row() -> dict[str, Any]:
    seen: set[str] = set()
    images: list[str] = []
    for u in DIGIT_GALLERY:
        ok, md5, nbytes = download_ok(u)
        if not ok:
            raise RuntimeError(f"Digit image fail {u}")
        if md5 in seen:
            continue
        seen.add(md5)
        images.append(u)
        print(f"  Digit img ok md5={md5} bytes={nbytes}")
    videos = enrich_video_list(list(DIGIT_VIDEOS))
    print(f"  Digit videos kept={len(videos)}")
    for v in videos:
        print(f"    - {(v.get('title') or '')[:90]}")

    description = (
        "Digit is Agility Robotics' commercially deployed bipedal humanoid for logistics "
        "and warehouse work. It is designed to operate in spaces built for people—moving "
        "totes and handling bulk material without costly facility retrofits—and connects "
        "to warehouse systems through Agility's Arc automation platform."
    )
    features = (
        "Commercially deployed humanoid for warehouses and distribution centers. "
        "Bipedal mobility for human-scale spaces (aisles, docks, uneven floors). "
        "End effectors optimized for grabbing and moving plastic totes common in e-commerce. "
        "Works with Agility Arc cloud platform for fleet monitoring and WMS/AMR integration. "
        "Assembled at RoboFab in Salem, OR. FCC approved and NRTL certified (OEM company timeline). "
        "Height stored as 1750 mm from existing record. Spec sheet is gated on OEM site—"
        "payload/weight left blank pending OEM-citable figures (do not invent from aggregators)."
    )
    return {
        "id": DIGIT_ID,
        "name": "Digit",
        "model_name": "Digit",
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "manufacturer_country_codes": "US",
        "description": description,
        "purpose": "Warehouse and logistics tote handling and material movement in human-scale facilities",
        "features": features,
        "url": URL_SOLUTIONS,
        "image": images[0],
        "images": images,
        "video_urls": videos,
        "movement_type_keys": "bipedal",
        "availability_status_key": "available",
        "category_slugs": "humanoid",
        "sub_category_slug": "manufacturing-industrial",
        "use_keys": "material-handling|pick-and-place|other",
        "industry_keys": "logistics|manufacturing|warehousing",
        "tags": TAGS_DIGIT,
        "release_year": 2019,
        "height_mm": 1750.0,
        "height": "175 cm",
        "source_locale": "en",
        "research_notes": (
            "[AI Research] Agility discovery 2026-07-19. English rewrite of zh narrative. "
            f"Heroes from OEM solutions CDN. Sources: {URL_SOLUTIONS}; {URL_DIGIT_LAUNCH}; "
            f"{URL_DIGIT_MEET}."
        ),
        "sources": [
            {"url": URL_SOLUTIONS, "type": "website", "title": "Agility Solutions — Digit"},
            {"url": URL_DIGIT_LAUNCH, "type": "website", "title": "Next-gen Digit logistics launch (2023)"},
            {"url": URL_DIGIT_MEET, "type": "website", "title": "Meet Digit unveil (2019)"},
        ],
        "information_source_urls": [URL_SOLUTIONS, URL_DIGIT_LAUNCH, URL_DIGIT_MEET],
        "notes": (
            "[AI Research] Current commercial Digit line. Digit V1 / v5 are generations—"
            "not separate catalog SKUs. Spec sheet page gated; typed payload/weight not set."
        ),
    }


def build_cassie_row() -> dict[str, Any]:
    videos = enrich_video_list(list(CASSIE_VIDEOS))
    print(f"  Cassie videos kept={len(videos)}")
    for v in videos:
        print(f"    - {(v.get('title') or '')[:90]}")

    description = (
        "Cassie is Agility Robotics' bipedal research platform that preceded Digit. "
        "Built for dynamic walking and running research (roots in Oregon State Dynamic "
        "Robotics Laboratory work), Cassie has no arms or torso—Digit later added those "
        "for practical warehouse work."
    )
    features = (
        "Bipedal research robot for locomotion control and dynamic gait development. "
        "Sold to research labs (OEM: Michigan Robotics Institute and others cited Cassie "
        "as a high-performance biped platform). "
        "Company timeline: Cassie takes first steps (2016–2017 era). "
        "Guinness-class 100 m bipedal run: 24.73 s standing-start / standing-finish "
        "(OEM video page, Whyte Track, 2022). "
        "No public OEM height/weight datasheet found—fields left blank."
    )
    notes = (
        "[IMAGE TO-DO — no hero, deliberate]\n"
        "OEM company timeline Cassie tiles are AVIF-only; no verified JPEG/PNG Cassie "
        "product photo on agilityrobotics.com after crawl. Do not use Digit photos.\n"
        "ACTION FOR TEAM: source a licensed Cassie still from Agility press kit / OSU archive.\n"
        "Do NOT substitute a Digit render, family banner, or marketing/diagram art.\n"
        "---\n"
        "[AI Research] Cassie is a distinct research product, not a Digit generation."
    )
    return {
        "name": "Cassie",
        "model_name": "Cassie",
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "manufacturer_country_codes": "US",
        "description": description,
        "purpose": "Bipedal locomotion research platform",
        "features": features,
        "url": URL_CASSIE_100M,
        "image": "",
        "images": [],
        "video_urls": videos,
        "movement_type_keys": "bipedal",
        "availability_status_key": "discontinued",
        "category_slugs": "humanoid",
        "sub_category_slug": "research",
        "use_keys": "research|other",
        "industry_keys": "research|education",
        "tags": TAGS_CASSIE,
        "release_year": 2017,
        "source_locale": "en",
        "research_notes": (
            "[AI Research] Agility discovery 2026-07-19. Cassie kept as research biped; "
            f"skipped Digit V1/v5/Humanoid Robot phantoms. Sources: {URL_COMPANY}; {URL_CASSIE_100M}; "
            f"{URL_DIGIT_MEET}."
        ),
        "sources": [
            {"url": URL_CASSIE_100M, "type": "website", "title": "Cassie 100M run (OEM)"},
            {"url": URL_COMPANY, "type": "website", "title": "Agility company timeline"},
            {"url": URL_DIGIT_MEET, "type": "website", "title": "Digit built on Cassie design"},
        ],
        "information_source_urls": [URL_CASSIE_100M, URL_COMPANY, URL_DIGIT_MEET],
        "notes": notes,
    }


def patch_taxonomy(client: ResearchApiClient, rid: int, *, release_year: int | None = None) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_COUNTRY_ID],
        "manufacturer_country_ref": US_COUNTRY_ID,
    }
    if release_year:
        body["release_year"] = release_year
    try:
        client._patch(f"robots/robots/{rid}/", body)
        print(f"  patched country/year {rid}")
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
    args = ap.parse_args()

    client = ResearchApiClient()
    print("Building Digit enrich…")
    digit = build_digit_row()
    print("Building Cassie create…")
    cassie = build_cassie_row()

    plan: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "digit": {
            "id": DIGIT_ID,
            "action": "enrich_published",
            "images_n": len(digit["images"]),
            "videos_n": len(digit.get("video_urls") or []),
        },
        "cassie": {
            "action": "create",
            "images_n": 0,
            "videos_n": len(cassie.get("video_urls") or []),
            "image_todo": True,
        },
        "skipped": ["Digit V1", "Digit v5", "Humanoid Robot", "Arc"],
        "apply": bool(args.apply),
    }

    if not args.apply:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps({"plan": plan, "digit": digit, "cassie": cassie}, indent=2),
            encoding="utf-8",
        )
        print(f"Dry-run → {REPORT}. Re-run with --apply --copy-media")
        return 0

    staging_dir = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Clean junk auto-discover files so they are never imported by accident
    for junk in ("digit-v1.json", "digit-v5.json", "humanoid-robot.json"):
        p = staging_dir / junk
        if p.exists():
            p.unlink()
            print(f"removed junk staging {junk}")

    digit_path = staging_dir / "digit.json"
    cassie_path = staging_dir / "cassie.json"
    digit_path.write_text(json.dumps(digit, indent=2), encoding="utf-8")
    cassie_path.write_text(json.dumps(cassie, indent=2), encoding="utf-8")

    # Digit — force overwrite published (user authorized company discovery QA)
    digit_result = import_staging(
        digit_path,
        dry_run=False,
        patch=True,
        force_overwrite=True,
        replace_media=True,
        status="published",
        created_by_id=resolve_created_by_id(args.created_by_id),
        skip_company_update=True,
    )
    print("Digit import:", digit_result)
    plan["digit"]["import"] = digit_result
    patch_taxonomy(client, DIGIT_ID, release_year=2019)

    # Cassie — create pending
    existing = find_by_name(client, "Cassie")
    if existing:
        print(f"Cassie already exists id={existing['id']}")
        plan["cassie"]["action"] = "skip_exists"
        plan["cassie"]["id"] = existing["id"]
    else:
        cassie_result = import_staging(
            cassie_path,
            dry_run=False,
            force_overwrite=True,
            replace_media=False,
            status="pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print("Cassie import:", cassie_result)
        plan["cassie"]["import"] = cassie_result
        created = find_by_name(client, "Cassie")
        if created:
            plan["cassie"]["id"] = created["id"]
            patch_taxonomy(client, created["id"], release_year=2017)

    if args.copy_media:
        plan["digit"]["copy_media"] = copy_media(DIGIT_ID)
        print(f"copy-media Digit {DIGIT_ID}: {plan['digit']['copy_media']}")
        # Cassie has no image — skip copy-media

    # Company short description
    try:
        client._patch(
            f"companies/{COMPANY_ID}/",
            {
                "short_description": (
                    "Oregon-based maker of Digit, a commercially deployed bipedal humanoid "
                    "for warehouse logistics, and earlier Cassie research bipeds."
                ),
                "website": "https://www.agilityrobotics.com",
            },
        )
        print("company short_description patched")
    except Exception as e:  # noqa: BLE001
        print(f"company patch warn: {e}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
