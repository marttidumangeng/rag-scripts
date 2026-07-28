"""Discover + enrich Sanctuary AI (92) — Phoenix only.

Auto-discover staged junk (Hydraulic Hands component, 'General Purpose Robots'
phantom). This script creates the one real product: Phoenix (current Gen 8).

OEM sources (2026-07-19):
- Gen 6 unveil specs: https://sanctuary.ai/news/sanctuary-ai-unveils-phoenix-...
- Gen 8 announcement: https://sanctuary.ai/news/sanctuary-ai-releases-new-generation-...
- Technology: https://www.sanctuary.ai/technology

Usage:
  python discover_sanctuary_phoenix.py
  python discover_sanctuary_phoenix.py --apply --copy-media
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

COMPANY_ID = 92
COMPANY_SLUG = "sanctuary-ai"
COMPANY_NAME = "Sanctuary AI"
REPORT = _RESEARCH_DIR / "staging" / "reports" / "sanctuary-phoenix-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# Visually verified Gen 8 product photos (labeled PHOENIX™ GEN 8 on OEM assets).
HERO = "https://sanctuary.ai/wp-content/uploads/2024/12/08_sanctuary_ai_phoenix_gen_7_full_body_not_a_render-scaled.webp"
GALLERY = [
    HERO,
    "https://sanctuary.ai/wp-content/uploads/2024/12/09_sanctuary_ai_phoenix_gen_7_front_angled_not_a_render-scaled.webp",
    "https://sanctuary.ai/wp-content/uploads/2024/12/03_sanctuary_ai_phoenix_gen_7_back_not_a_render.webp",
]

URL_UNVEIL = (
    "https://sanctuary.ai/news/"
    "sanctuary-ai-unveils-phoenix-a-humanoid-general-purpose-robot-designed-for-work/"
)
URL_GEN8 = (
    "https://sanctuary.ai/news/"
    "sanctuary-ai-releases-new-generation-of-ai-robots-for-high-quality-data-capture/"
)
URL_TECH = "https://www.sanctuary.ai/technology"

VIDEOS = [
    "https://www.youtube.com/watch?v=FH3zbUSMAAU",  # Phoenix at Human-Equivalent Speed
    "https://www.youtube.com/watch?v=E4RqGYbxaWM",  # tactile sensors on Phoenix
    "https://www.youtube.com/watch?v=NQWTRsWqHIA",  # Robot Phoenix by Sanctuary AI
]

# TagCatalog-style names used on other humanoids in this repo.
TAGS = "Humanoid|Autonomous|Wheeled|Service|Research|AI|Manipulation|General-Purpose"


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, timeout=45, headers=UA)
        data = r.content
        if r.status_code != 200 or len(data) < 5000:
            return False, "", len(data)
        if not (
            data[:4] == b"RIFF"
            or data[:8].startswith(b"\x89PNG")
            or data[:3] == b"\xff\xd8\xff"
        ):
            return False, "", len(data)
        return True, hashlib.md5(data).hexdigest(), len(data)
    except requests.RequestException:
        return False, "", 0


def build_row() -> dict[str, Any]:
    seen: set[str] = set()
    images: list[str] = []
    hero_md5 = ""
    for u in GALLERY:
        ok, md5, nbytes = download_ok(u)
        if not ok:
            raise RuntimeError(f"image fail {u}")
        if md5 in seen:
            continue
        seen.add(md5)
        images.append(u)
        if u == HERO:
            hero_md5 = md5
            print(f"  hero ok md5={md5} bytes={nbytes}")
    if not hero_md5:
        raise RuntimeError("hero hash missing")

    videos = enrich_video_list(list(VIDEOS))
    print(f"  videos kept: {len(videos)}")
    for v in videos:
        print(f"    - {(v.get('title') or '')[:90]}")

    # Gen-6 unveil OEM figures (press, May 2023). Gen 8 keeps the product line
    # name Phoenix; wheeled base is Gen 8 design (no new public height/weight).
    features = (
        "General-purpose humanoid for industrial work, controlled by Sanctuary Carbon AI. "
        "Current Gen 8 uses a wheeled base (OEM: bipedal legs too frail for strong torso work) "
        "with improved depth/vision cameras, telemetry, and sensor suite for high-quality data capture. "
        "Dexterous hydraulic hands with tactile sensing (20 DoF hands cited at Gen 6 unveil). "
        "Gen 6 unveil specs (OEM; production may vary): height 170 cm / 5 ft 7 in; "
        "weight 70 kg / 155 lbs; max payload 25 kg / 55 lbs; max speed 5 kph / 3 mph."
    )
    description = (
        "Phoenix is Sanctuary AI's general-purpose humanoid robot platform, "
        "powered by the Carbon AI control system for industrial and workplace tasks. "
        "The current Gen 8 generation emphasizes wheeled mobility and high-fidelity sensing for data capture."
    )

    return {
        "name": "Phoenix",
        "model_name": "Phoenix Gen 8",
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CA",
        "manufacturer_country_codes": "CA",
        "description": description,
        "purpose": "General-purpose humanoid robot for industrial and workplace labor tasks",
        "features": features,
        "url": URL_GEN8,
        "image": HERO,
        "images": images,
        "video_urls": videos,
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "humanoid",
        "sub_category_slug": "manufacturing-industrial",
        "use_keys": "manipulation|other",
        "industry_keys": "manufacturing|research",
        "tags": TAGS,
        "release_year": 2023,
        "weight_kg": 70.0,
        "weight": "70 kg",
        "height_mm": 1700.0,
        "height": "170 cm",
        "payload_kg": 25.0,
        "speed_ms": 1.39,
        "speed": "5 kph / 3 mph",
        "source_locale": "en",
        "research_notes": (
            "[AI Research] Sanctuary discovery 2026-07-19. "
            f"Hero/gallery = Gen 8 labeled OEM photos. Specs from Gen 6 unveil {URL_UNVEIL}. "
            f"Gen 8 wheeled-base notes from {URL_GEN8}. "
            "Skipped: Hydraulic Hands (component), 'General Purpose Robots' (phantom category), "
            "Carbon (AI software)."
        ),
        "sources": [
            {"url": URL_GEN8, "type": "website", "title": "Sanctuary AI Phoenix Gen 8 announcement"},
            {"url": URL_UNVEIL, "type": "website", "title": "Sanctuary AI Phoenix unveil (Gen 6 specs)"},
            {"url": URL_TECH, "type": "website", "title": "Sanctuary AI Technology"},
        ],
        "information_source_urls": [URL_GEN8, URL_UNVEIL, URL_TECH],
        "notes": (
            "[AI Research] Phoenix Gen 8 (current). "
            "Gen 6 unveil specs cited for height/weight/payload/speed; Gen 8 press does not restate them. "
            "Do not invent Gen 8-only dimensions."
        ),
        "_hero_md5": hero_md5,
    }


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


def find_phoenix(client: ResearchApiClient) -> dict[str, Any] | None:
    for r in client.list_robots_for_company(COMPANY_ID) or []:
        if (r.get("name") or "") == "Phoenix":
            return r
    return None


def patch_typed(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    # Canada country id=1 from company record
    body: dict[str, Any] = {
        "manufacturer_countries": [1],
        "manufacturer_country_ref": 1,
    }
    for key in ("payload_kg", "weight_kg", "height_mm", "speed_ms", "release_year"):
        if row.get(key) is not None:
            body[key] = row[key]
    try:
        client._patch(f"robots/robots/{rid}/", body)
        print(f"  patched typed fields {rid}")
    except Exception as e:  # noqa: BLE001
        print(f"  typed patch warn {rid}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    existing = find_phoenix(client)
    if existing:
        print(f"Phoenix already exists id={existing['id']} status={existing.get('status')}")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps({"action": "skip_exists", "robot": existing}, indent=2),
            encoding="utf-8",
        )
        return 0

    print("Building Phoenix row…")
    row = build_row()
    md5 = row.pop("_hero_md5")
    plan = {
        "company_id": COMPANY_ID,
        "action": "create",
        "name": row["name"],
        "url": row["url"],
        "images_n": len(row["images"]),
        "hero": row["image"],
        "hero_md5": md5,
        "videos_n": len(row.get("video_urls") or []),
        "apply": bool(args.apply),
    }
    print(
        f"READY Phoenix: imgs={len(row['images'])} videos={len(row.get('video_urls') or [])} "
        f"payload={row.get('payload_kg')}kg height={row.get('height_mm')}mm"
    )

    if not args.apply:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"plan": plan, "row_preview": row}, indent=2), encoding="utf-8")
        print(f"Dry-run report → {REPORT}. Re-run with --apply --copy-media")
        return 0

    staging_dir = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path = staging_dir / "phoenix.json"
    staging_path.write_text(json.dumps(row, indent=2), encoding="utf-8")

    result = import_staging(
        staging_path,
        dry_run=False,
        force_overwrite=True,
        replace_media=True,
        status="pending_review",
        created_by_id=resolve_created_by_id(args.created_by_id),
        skip_company_update=True,
    )
    print("import:", result)

    created = find_phoenix(client)
    if not created:
        print("ERROR: Phoenix not found after import")
        plan["error"] = "not_found_after_import"
        REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return 1

    rid = created["id"]
    plan["robot_id"] = rid
    patch_typed(client, rid, row)

    if args.copy_media:
        cm = copy_media(rid)
        plan["copy_media"] = cm
        print(f"copy-media {rid}: {cm}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
