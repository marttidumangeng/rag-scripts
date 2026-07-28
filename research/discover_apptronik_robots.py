"""Curated Apptronik (14) enrich — Apollo + Apollo 2.

Existing:
  Apollo (37) pending_review — Chinese 21-char features, no country; keep OEM hero
  Apptronik Apollo 2 (1634) published — features polluted with Webflow template nav junk

OEM site notes (2026-07-19):
  /apollo → 404; /apollo/apollo-2 has real copy + template leftover "Beautiful & creative websites…"
  Unveiled 2023-08-23 press still live with height/weight/payload cites.

Usage:
  python discover_apptronik_robots.py
  python discover_apptronik_robots.py --apply --copy-media
"""
from __future__ import annotations

import argparse
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

COMPANY_ID = 14
COMPANY_SLUG = "apptronik"
COMPANY_NAME = "Apptronik"
US_ID = 20
REPORT = _RESEARCH_DIR / "staging" / "reports" / "apptronik-discover.json"

PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "Apollo",
        "id": 37,
        "action": "enrich",
        "status": "pending_review",
        "url": "https://www.apptronik.com/news-collection/apptronik-unveils-apollo",
        "model_name": "Apollo",
        "release_year": 2023,
        "availability_status": 11,
        "category_slugs": "humanoid",
        "movement_type_keys": "legged",
        "use_keys": "material-handling|picking|assembly|other",
        "industry_keys": "warehousing|manufacturing|logistics",
        "tags": "Humanoid|Bipedal|Industrial|Warehouse|Modular|Collaborative|Autonomous",
        # Keep owned CDN hero (labeled Apollo / A1 chest) — do not replace with aggregator.
        "images": [],
        "keep_existing_image": True,
        "height_mm": 1727.0,
        "height": "5 ft 8 in (173 cm)",
        "weight_kg": 72.6,
        "weight": "160 lb (72.6 kg)",
        "payload_kg": 25.0,
        "description": (
            "Apollo is Apptronik's commercial general-purpose humanoid for work in "
            "human-designed spaces such as warehouses and manufacturing plants. "
            "It grew out of the team's earlier robots including NASA Valkyrie work."
        ),
        "features": (
            "Human-scale bipedal humanoid: about 5 ft 8 in (173 cm) tall, 160 lb (72.6 kg), "
            "55 lb (25 kg) payload (OEM unveil 2023-08-23). "
            "Force-control architecture for collaborative-style operation around people (OEM unveil). "
            "Modular design lineage toward mass manufacturability; swappable battery packs on the Apollo platform. "
            "Chest status display and five-fingered hands (OEM product photography)."
        ),
        "purpose": "General-purpose humanoid labor for warehouses, manufacturing, and logistics",
        "sources": [
            {
                "url": "https://www.apptronik.com/news-collection/apptronik-unveils-apollo",
                "title": "Apptronik unveils Apollo (2023-08-23)",
            },
            {"url": "https://www.apptronik.com/", "title": "Apptronik home"},
        ],
    },
    {
        "name": "Apollo 2",
        "id": 1634,
        "action": "enrich",
        "status": "published",
        "url": "https://www.apptronik.com/apollo/apollo-2",
        "model_name": "Apollo 2",
        "rename_from": "Apptronik Apollo 2",
        "availability_status": 11,
        "category_slugs": "humanoid",
        "movement_type_keys": "legged|wheeled",
        "use_keys": "material-handling|picking|inspection|other",
        "industry_keys": "warehousing|manufacturing|logistics|retail",
        "tags": "Humanoid|Apollo 2|Modular|Bipedal|Wheeled|Fleet|Industrial|AI",
        "images": [],
        "keep_existing_image": True,
        # Apollo 2 page does not restate numeric height/weight — leave blank (fail closed).
        "description": (
            "Apollo 2 is Apptronik's next-generation humanoid platform for real-world "
            "mobility, manipulation, and human interaction, with modular bipedal or wheeled bases."
        ),
        "features": (
            "Modular mobility: bipedal configuration for human spaces or wheeled base for high-throughput "
            "facilities (OEM Apollo 2 page). "
            "Human-centered UI: expressive LED mouth, lighting/speech, chest display for status/battery/tasks. "
            "Patented actuator platform aimed at high energy efficiency and mass manufacturability (OEM). "
            "Swappable batteries for high-uptime operation; opportunity charging and tethering options (OEM). "
            "Platform stack: Apollo 2 hardware + Artemis intelligence layer + Fleet Connect operations (OEM). "
            "Safety zones: impact zone pause + configurable perimeter behavior (OEM)."
        ),
        "purpose": "Next-gen commercial humanoid platform for industrial and logistics work alongside people",
        "sources": [
            {"url": "https://www.apptronik.com/apollo/apollo-2", "title": "Apollo 2 product page"},
            {"url": "https://www.apptronik.com/", "title": "Apptronik home"},
        ],
    },
]


def copy_media(rid: int) -> str:
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
    for attempt in range(5):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return "ok"
            if resp.status_code not in (502, 503, 504):
                return f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            last = f"ERR {e}"
        time.sleep(2**attempt)
    return last if "last" in dir() else "fail"


def yt_search(query: str, limit: int = 8) -> list[str]:
    html = requests.get(
        "https://www.youtube.com/results",
        params={"search_query": query},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    ).text
    ids = list(dict.fromkeys(re.findall(r"watch\?v=([\w-]{11})", html)))[:limit]
    return [f"https://www.youtube.com/watch?v={i}" for i in ids]


def pick_videos(name: str) -> list[dict[str, Any]]:
    vids = enrich_video_list(yt_search(f"Apptronik {name}", limit=10))
    token = name.lower().replace(" ", "")
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        if "apptronik" not in title and "apollo" not in title:
            continue
        if token == "apollo2" and "apollo 2" not in title and "apollo2" not in title.replace(" ", ""):
            # allow Apollo platform clips for Apollo 2 if clearly Apptronik
            if "apptronik" not in title:
                continue
        if any(bad in title for bad in ("firgelli", "unboxing toy", "roblox")):
            continue
        kept.append(v)
    return kept[:3]


def build_row(spec: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    images: list[str] = list(spec.get("images") or [])
    if spec.get("keep_existing_image") and existing:
        # Prefer external original if present on photos; else leave empty so import keeps CDN
        for p in existing.get("photos") or []:
            u = (p.get("url") or "") if isinstance(p, dict) else ""
            if u and "robotaigeek.com" not in u:
                images.append(u)
                break
        if not images and existing.get("image") and "cdn.robotaigeek.com" not in (existing.get("image") or ""):
            images.append(existing["image"])

    vids = pick_videos(spec["name"])
    print(f"  videos kept={len(vids)}")
    for v in vids:
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
        "video_urls": vids,
        "movement_type_keys": spec.get("movement_type_keys") or "",
        "category_slugs": spec.get("category_slugs") or "humanoid",
        "use_keys": spec.get("use_keys") or "other",
        "industry_keys": spec.get("industry_keys") or "manufacturing",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or 11,
        "research_notes": (
            "[AI Research] Apptronik enrich 2026-07-19. Fixed Chinese/template features; "
            "US country; unveil specs on Apollo only. /apollo PDP 404 — use unveil + Apollo 2 page."
        ),
        "sources": [
            {"url": s["url"], "type": "website", "title": s.get("title") or s["url"]}
            for s in (spec.get("sources") or [{"url": spec["url"]}])
        ],
        "information_source_urls": [s["url"] for s in (spec.get("sources") or [{"url": spec["url"]}])],
        "notes": "[AI Research] Apptronik curated enrich.",
    }
    if spec.get("id"):
        row["id"] = spec["id"]
    for key in ("release_year", "payload_kg", "weight_kg", "height_mm", "height", "weight"):
        if spec.get(key) is not None:
            row[key] = spec[key]
    return row


def patch_fields(client: ResearchApiClient, rid: int, row: dict[str, Any], *, rename: str | None = None) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": row.get("availability_status") or 11,
        "description": row["description"],
        "features": row["features"],
        "purpose": row["purpose"],
        "url": row["url"],
        "model_name": row.get("model_name"),
        "notes": row.get("notes"),
        "source_locale": "en",
    }
    if rename:
        body["name"] = rename
    elif row.get("name"):
        body["name"] = row["name"]
    for key in ("release_year", "payload_kg", "weight_kg", "height_mm", "height", "weight"):
        if row.get(key) is not None:
            body[key] = row[key]
    client._patch(f"robots/robots/{rid}/", body)
    # Overwrite stale zh translation overlays (Digit/Apollo pattern)
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"apptronik-en-force-{rid}-20260719-{loc}",
                "translated_fields": {
                    "description": row["description"],
                    "features": row["features"],
                    "purpose": row["purpose"],
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
    print(f"  patched {rid}")


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

    for spec in PRODUCTS:
        print(f"Building {spec['name']} ({spec['action']})…")
        existing = client._get(f"robots/robots/{spec['id']}/") if spec.get("id") else None
        row = build_row(spec, existing)
        rows.append((spec, row))
        plan["robots"].append(
            {
                "name": spec["name"],
                "id": spec.get("id"),
                "features_len": len(row["features"]),
                "videos_n": len(row.get("video_urls") or []),
                "images_n": len(row.get("images") or []),
            }
        )

    if not args.apply:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"plan": plan, "rows": [r for _, r in rows]}, indent=2), encoding="utf-8")
        print(f"Dry-run → {REPORT}")
        return 0

    for spec, row in rows:
        path = staging_dir / f"{spec['name'].lower().replace(' ', '-')}.json"
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        # Narrative/taxonomy via direct PATCH (keeps owned CDN when images empty)
        rename = spec["name"] if spec.get("rename_from") else None
        patch_fields(client, int(spec["id"]), row, rename=rename)
        # Optional staging import for tags/uses when we have media to replace
        if row.get("images"):
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
            if args.copy_media:
                print(f"copy-media {spec['id']}:", copy_media(int(spec["id"])))
        else:
            # Still push taxonomy keys via a light staging import without replace_media
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
            print(f"import {spec['name']} (no media replace):", result)

        for item in plan["robots"]:
            if item["name"] == spec["name"]:
                item["import"] = result

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
