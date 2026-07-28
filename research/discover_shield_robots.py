"""Curated Shield AI (285) greenfield discovery.

CREATE pending_review:
  V-BAT — Group 3 VTOL ISR UAS (combat-proven OEM product page)
  X-BAT — AI-piloted VTOL fighter (unveiled 2025-10-22; first flight targeted 2026)

SKIP:
  Hivemind / Hivemind Enterprise / Vision Systems — software products, not robots
  Aechelon — simulation/synthetic reality acquisition (software)

Media (visual QA 2026-07-19):
  V-BAT hero = labeled OEM studio top-down `v-bat-1a-scaled.jpg`
  Reject site chrome, C2 van people shots, targeting footage, line-art schematics as heroes
  X-BAT hero = OEM jungle LRV render `X-BAT_jungle-1.png` (+ unveil still)

Usage:
  python discover_shield_robots.py
  python discover_shield_robots.py --apply --copy-media
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

COMPANY_ID = 285
COMPANY_SLUG = "shield-ai"
COMPANY_NAME = "Shield AI"
US_ID = 20
REPORT = _RESEARCH_DIR / "staging" / "reports" / "shield-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "V-BAT",
        "action": "create",
        "status": "pending_review",
        "url": "https://shield.ai/v-bat/",
        "model_name": "V-BAT",
        "availability_status": 11,
        "category_slugs": "drone|aerial",
        "movement_type_keys": "aerial",
        "use_keys": "surveillance|security|inspection|other",
        "industry_keys": "defense|security|government",
        "tags": "Drone|UAV|VTOL|Autonomous|Aerial|Defense|ISR|Surveillance|Military",
        "weight_kg": 75.0,  # max gross takeoff
        "payload_kg": 18.1,
        "height_mm": 2900.0,  # 9.6 ft
        "width_mm": 3800.0,  # wingspan 12.5 ft as width
        "images": [
            "https://shield.ai/wp-content/uploads/2025/03/v-bat-1a-scaled.jpg",
            "https://shield.ai/wp-content/uploads/2025/03/v-bat-4a-scaled.jpg",
            "https://shield.ai/wp-content/uploads/2025/03/v-bat-3a-scaled.jpg",
        ],
        "videos": [
            "https://www.youtube.com/watch?v=CdUR-PN4_6c",
            "https://www.youtube.com/watch?v=FfYEy5SuYOo",
            "https://www.youtube.com/watch?v=5HUupjXsajw",
        ],
        "video_needles": ["v-bat", "vbat", "shield ai"],
        "description": (
            "V-BAT is Shield AI's combat-proven Group 3 vertical takeoff and landing (VTOL) "
            "unmanned aircraft for expeditionary ISR and targeting. "
            "A ducted-fan tail-sitter, it deploys from small footprints including ship decks "
            "and packs for two-person field teams."
        ),
        "features": (
            "Group 3 VTOL UAS with ducted-fan / unassisted launch & land (OEM /v-bat/). "
            "Airframe: heavy-fuel (JP5) engine; wingspan 12.5 ft (3.8 m); height 9.6 ft (2.9 m); "
            "max gross takeoff weight 165 lb (75 kg) (OEM specs table). "
            "Endurance 12+ hours with EO/IR payload; max payload 40 lb (18.1 kg); "
            "landing zone 15×15 ft (4.6×4.6 m) (OEM). "
            "Radio range examples: ~81 mi (MPU5) / ~112 mi (C-Band) (OEM; env-dependent). "
            "Payload power ~600 W; modular EO/IR, SAR, SATCOM, ViDAR, EW options (OEM). "
            "Hivemind Pilot-ready for GNSS-/comms-denied autonomy (OEM block-upgrade press). "
            "Selected for U.S. Coast Guard Maritime UAS Services; Navy/MEU shipboard deployments (OEM)."
        ),
        "purpose": "Expeditionary VTOL ISR and targeting for maritime and contested environments",
        "sources": [
            {"url": "https://shield.ai/v-bat/", "title": "Shield AI — V-BAT"},
            {
                "url": "https://shield.ai/shield-ai-unveils-v-bat-block-upgrade-powered-by-hivemind-advanced-autonomy-satcom-and-heavy-fuel-engine-among-new-features/",
                "title": "V-BAT block upgrade press (2025-04-07)",
            },
        ],
    },
    {
        "name": "X-BAT",
        "action": "create",
        "status": "pending_review",
        "url": "https://shield.ai/x-bat/",
        "model_name": "X-BAT",
        "release_year": 2025,  # unveil year (not IOC)
        "availability_status": 11,
        "category_slugs": "drone|aerial",
        "movement_type_keys": "aerial",
        "use_keys": "security|surveillance|other",
        "industry_keys": "defense|government",
        "tags": "Drone|UAV|VTOL|Autonomous|Aerial|Defense|Stealth|Military|Fighter",
        "width_mm": 11887.0,  # 39 ft wingspan
        "height_mm": 7925.0,  # 26 ft fuselage height (OEM page)
        "images": [
            # OEM jungle LRV still via wsrv JPEG (source PNG is ~50MB)
            "https://wsrv.nl/?url=https%3A%2F%2Fshield.ai%2Fwp-content%2Fuploads%2F2026%2F05%2FX-BAT_jungle-1.png&output=jpg&w=1600",
            "https://shield.ai/wp-content/uploads/2025/10/Image-46.jpeg",
            "https://wsrv.nl/?url=https%3A%2F%2Fshield.ai%2Fwp-content%2Fuploads%2F2026%2F05%2FX-BAT_truck-scaled.png&output=jpg&w=1600",
        ],
        "videos": [
            "https://www.youtube.com/watch?v=OnpuNlE3UxU",
            "https://www.youtube.com/watch?v=17_P4x0k3XM",
            "https://www.youtube.com/watch?v=bGIGZMCi1nk",
        ],
        "video_needles": ["x-bat", "xbat", "shield ai"],
        "description": (
            "X-BAT is Shield AI's AI-piloted vertical takeoff and landing (VTOL) fighter "
            "aircraft concept for expeditionary and maritime operations in contested airspace. "
            "Unveiled October 22, 2025, it pairs runway-independent VTOL with theater-scale range "
            "and Hivemind autonomy; first VTOL flights are targeted for 2026 with production "
            "aimed at 2029 (OEM)."
        ),
        "features": (
            "AI-piloted VTOL fighter jet unveiled 2025-10-22 (Shield AI press + /x-bat/). "
            "OEM claimed specs: >2,000 NM max range with full mission payload; >50,000 ft ceiling; "
            ">4 g maneuver load factor; 39 ft wingspan; fuselage height 26 ft × 5 ft; "
            "storage envelope 40×14×6 ft (OEM /x-bat/ specs). "
            "Multirole: strike, counter-air, EW, ISR; internal weapons bay + external hardpoints (OEM). "
            "Launch/recovery vehicle for ships, islands, austere sites; ~3:1 expeditionary deck "
            "footprint vs legacy fighter (OEM). "
            "Powered by Hivemind for GNSS-/comms-denied collaborative teaming (OEM). "
            "Roadmap: first VTOL flight 2026; mission capability ~2028; production ~2029 (OEM)."
        ),
        "purpose": "Runway-independent AI-piloted VTOL combat aircraft for contested airpower",
        "sources": [
            {"url": "https://shield.ai/x-bat/", "title": "Shield AI — X-BAT"},
            {
                "url": "https://shield.ai/shield-ai-unveils-x-bat-an-ai-piloted-vtol-fighter-jet-for-contested-environments/",
                "title": "X-BAT unveil press (2025-10-22)",
            },
        ],
        "notes_extra": (
            "[STATUS NOTE] X-BAT is unveiled / in development — first VTOL flight targeted 2026; "
            "not yet an operational fleet aircraft.\n---\n"
        ),
    },
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=120)
    except Exception:  # noqa: BLE001
        return False, "", 0
    if r.status_code != 200 or len(r.content) < 3000:
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
        print(f"  img ok {md5[:12]} {nbytes} …{u[-50:]}")

    needles = [n.lower() for n in (spec.get("video_needles") or [spec["name"].lower()])]
    vids = enrich_video_list(list(spec.get("videos") or []))
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        if any(n in title for n in needles):
            kept.append(v)
    print(f"  videos kept={len(kept)}")
    for v in kept[:3]:
        print(f"    - {(v.get('title') or '')[:80]}")

    notes = "[AI Research] Shield AI curated discovery 2026-07-19. Skipped Hivemind software."
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
        "video_urls": kept[:3],
        "movement_type_keys": spec.get("movement_type_keys") or "aerial",
        "category_slugs": spec.get("category_slugs") or "drone",
        "use_keys": spec.get("use_keys") or "surveillance",
        "industry_keys": spec.get("industry_keys") or "defense",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or 11,
        "research_notes": (
            "[AI Research] Shield AI discovery 2026-07-19. Aircraft only (V-BAT, X-BAT); "
            "skipped Hivemind/Vision Systems software."
        ),
        "sources": [
            {"url": s["url"], "type": "website", "title": s.get("title") or s["url"]}
            for s in (spec.get("sources") or [{"url": spec["url"]}])
        ],
        "information_source_urls": [s["url"] for s in (spec.get("sources") or [{"url": spec["url"]}])],
        "notes": notes,
    }
    for k in (
        "release_year",
        "weight_kg",
        "payload_kg",
        "height_mm",
        "length_mm",
        "width_mm",
    ):
        if spec.get(k) is not None:
            row[k] = spec[k]
    if not images:
        row["notes"] = (
            "[IMAGE TO-DO — no hero, deliberate]\n"
            f"No verified OEM product still for {spec['name']}.\n"
            "ACTION FOR TEAM: source OEM press kit.\n---\n"
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
        "notes": row.get("notes") or "",
    }
    for k in (
        "release_year",
        "weight_kg",
        "payload_kg",
        "height_mm",
        "length_mm",
        "width_mm",
    ):
        if row.get(k) is not None:
            body[k] = row[k]
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
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    only = {n.strip().lower() for n in args.only.split(",") if n.strip()}
    products = [p for p in PRODUCTS if not only or p["name"].lower() in only]

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
        result = import_staging(
            path,
            dry_run=False,
            patch=False,
            force_overwrite=True,
            replace_media=bool(row.get("images")),
            status=spec.get("status") or "pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        created = find_by_name(client, spec["name"])
        rid = created["id"] if created else None
        if rid:
            patch_fields(client, rid, row)
            if args.copy_media and row.get("images"):
                print(f"copy-media {rid}:", copy_media(rid))
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
