"""Backfill INTAMSYS (company 1073) FUNMAT printers: correct photos, features, specs, videos, tags.

Prior media was wrong/shared (og:image placeholder, abstract backgrounds, unrelated shots).
Hero images are official intamsys.com product renders; specs from the site comparison table;
features from each PDP; videos from YouTube search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

# Catalog tag names only (pipe-separated). Avoid auto-suggest — it maps printers to Humanoid/arms.
TAGS_BY_NAME: dict[str, str] = {
    "FUNMAT PRO 310 NEO": "Manufacturing|Industrial|3D-Printed|Prototyping|Factory|Modular|high-speed|Industrial Automation",
    "FUNMAT HT": "Manufacturing|Industrial|3D-Printed|Prototyping|Desktop Robot|Factory|Modular|Industrial Automation",
    "FUNMAT PRO 410": "Manufacturing|Industrial|3D-Printed|Prototyping|Factory|Modular|Industrial Automation|Productivity",
    "FUNMAT PRO 610HT": "Manufacturing|Industrial|3D-Printed|Factory|Modular|Industrial Automation|Productivity|high-payload",
    "FUNMAT PRO 310 APOLLO": "Manufacturing|Industrial|3D-Printed|Prototyping|Factory|Modular|high-speed|Productivity",
}

AVAILABLE = 11
FAMILY_URL = "https://www.intamsys.com/"
HELP_URLS = {
    "FUNMAT PRO 310 NEO": "https://help.intamsys.com/en/INTAMSYSPRINTERS/FUNMATPRO310NEO",
    "FUNMAT HT": "https://help.intamsys.com/en/INTAMSYSPRINTERS/FUNMATPROHT",
    "FUNMAT PRO 410": "https://help.intamsys.com/en/INTAMSYSPRINTERS/FUNMATPRO410",
    "FUNMAT PRO 610HT": "https://help.intamsys.com/en/INTAMSYSPRINTERS/FUNMATPRO610HT",
    "FUNMAT PRO 310 APOLLO": "https://help.intamsys.com/en/INTAMSYSPRINTERS/FUNMATPRO310APOLLO",
}

COMPANY_ID = 1073
COMPANY_SLUG = "intamsys-technology-co-ltd"
COMPANY_NAME = "Intamsys Technology Co., Ltd."
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Curated enrichment keyed by exact robot name in prod.
ROBOT_DATA: dict[str, dict[str, Any]] = {
    "FUNMAT PRO 310 NEO": {
        "url": "https://www.intamsys.com/funmat-pro-310-neo",
        "image": "https://www.intamsys.com/uploads/upload/images/20240914/bc7eb1f34ff95f303c9f342fd62dc074.png",
        "images": [
            "https://www.intamsys.com/uploads/upload/images/20240914/bc7eb1f34ff95f303c9f342fd62dc074.png",
            "https://www.intamsys.com/uploads/upload/images/20240911/1ac7d327313a483881e1729107684326.png",
        ],
        "description": (
            "FUNMAT PRO 310 NEO is INTAMSYS's high-speed industrial FFF 3D printer with IDEX "
            "dual-extrusion for batch and engineering production. It targets PC, PA12, TPU, and "
            "other engineering materials with an actively heated chamber up to 100°C."
        ),
        "purpose": (
            "Small-batch production of engineering-polymer parts\n"
            "Functional prototyping with dual materials and soluble supports"
        ),
        "features": (
            "IDEX dual-extrusion with mirror, duplicate, support, and dual-color modes. "
            "Actively heated chamber up to 100°C for engineering plastics including PC. "
            "High-throughput printing with 12+ high-speed material process options (about 500–1000 g/day). "
            "Build volume single nozzle 305 × 260 × 260 mm; dual nozzles 260 × 260 × 260 mm. "
            "Auto mesh leveling (100-point), IDEX auto Z calibration, modular maintenance design. "
            "Sealed dry hopper for continuous printing; HEPA/activated-carbon air filtration and door safety locks. "
            "Works with INTAMSUITE NEO slicing and remote/MES networking."
        ),
        "weight_kg": 80.0,
        "weight": "80 kg",
        "dimensions_mm": "700x655x700",
        "length_mm": 700.0,
        "width_mm": 655.0,
        "height_mm": 700.0,
        "family_key": "intamsys:funmat-pro-310",
        "family_name": "FUNMAT PRO 310",
        "variant_code": "FUNMAT-PRO-310-NEO",
        "variant_label": "NEO",
        "videos": [
            "https://www.youtube.com/watch?v=b6FPOdJ_xS0",
        ],
        "source_note": (
            "Official product render + comparison-table specs from intamsys.com/funmat-pro-310-neo; "
            "JSON-LD Product description; YouTube product videos."
        ),
    },
    "FUNMAT HT": {
        "url": "https://www.intamsys.com/funmat-ht-3d-printer",
        "image": "https://www.intamsys.com/static/cms/images/HT.png",
        "images": [
            "https://www.intamsys.com/static/cms/images/HT.png",
        ],
        "description": (
            "FUNMAT HT is INTAMSYS's affordable desktop high-temperature FFF 3D printer for "
            "PEEK and other engineering polymers. Build volume 260 × 260 × 260 mm with "
            "industrial-oriented thermal design and 50-micron class resolution."
        ),
        "purpose": (
            "R&D and functional prototyping with PEEK-class polymers\n"
            "Desktop production of high-temperature engineering parts"
        ),
        "features": (
            "Desktop PEEK-capable high-temperature FFF printer. "
            "Build volume 260 × 260 × 260 mm. "
            "Advanced thermal design for high-melt materials such as PEEK, PEEK-CF/GF, and PEKK. "
            "Auto bed leveling, reusable ceramic glass plate, filament runout warning. "
            "3.2-inch touch screen for guided operation. "
            "Open material support across high-temp and engineering filaments (PEEK family, ABS, PC, PPA, PPS, nylons, PLA)."
        ),
        "weight_kg": 63.0,
        "weight": "63 kg",
        "dimensions_mm": "543x501x645",
        "length_mm": 543.0,
        "width_mm": 501.0,
        "height_mm": 645.0,
        "release_year": 2016,
        "family_key": "intamsys:funmat-ht",
        "family_name": "FUNMAT HT",
        "variant_code": "FUNMAT-HT",
        "variant_label": "HT",
        "videos": [],
        "source_note": (
            "Official HT product render from intamsys.com; comparison-table build size/weight; "
            "PDP feature copy; YouTube reviews/overviews."
        ),
    },
    "FUNMAT PRO 410": {
        "url": "https://www.intamsys.com/funmat-pro-410-3d-printer",
        "image": "https://www.intamsys.com/static/cms/images/410.png",
        "images": [
            "https://www.intamsys.com/static/cms/images/410.png",
        ],
        "description": (
            "FUNMAT PRO 410 is INTAMSYS's industrial dual-nozzle FFF 3D printer for PEEK and "
            "high-performance engineering materials, with a 305 × 305 × 406 mm build volume and "
            "open-filament compatibility for production and complex geometries."
        ),
        "purpose": (
            "Production of PEEK-class end-use parts, jigs, and fixtures\n"
            "Dual-material printing of complex parts with removable supports"
        ),
        "features": (
            "Industrial dual-nozzle FFF platform for PEEK and engineering polymers. "
            "Build volume 305 × 305 × 406 mm with PEEK-specific ceramic glass plate. "
            "Hotends up to 500°C, chamber up to 90°C, high-temp heated bed for PEEK workflows. "
            "Multi-material printing including PEEK/PEKK/PAEK, fiber composites, PC, ABS, ASA. "
            "Open-source filament compatible (not locked to INTAM™ only). "
            "Water-soluble and breakaway support workflows via dual extruders. "
            "Auto leveling, clogging alarm, filament runout warning, self-cleaning printhead."
        ),
        "weight_kg": 230.0,
        "weight": "230 kg",
        "dimensions_mm": "728x684x1480",
        "length_mm": 728.0,
        "width_mm": 684.0,
        "height_mm": 1480.0,
        "family_key": "intamsys:funmat-pro-410",
        "family_name": "FUNMAT PRO 410",
        "variant_code": "FUNMAT-PRO-410",
        "variant_label": "410",
        "videos": [],
        "source_note": (
            "Official PRO 410 product render from intamsys.com; comparison-table specs; "
            "PDP thermal/support feature sections; YouTube overviews."
        ),
    },
    "FUNMAT PRO 610HT": {
        "url": "https://www.intamsys.com/funmat-pro-610-ht-3d-printer",
        "image": "https://www.intamsys.com/static/cms/images/pro610p2.png",
        "images": [
            "https://www.intamsys.com/static/cms/images/pro610p2.png",
        ],
        "description": (
            "FUNMAT PRO 610HT is INTAMSYS's large-format industrial FFF 3D printer for "
            "high-temperature materials including PEEK, PEKK, PEI, and PPSU. Build volume "
            "610 × 508 × 508 mm with a heated chamber up to 300°C for continuous production."
        ),
        "purpose": (
            "Large-format production of high-performance polymer parts\n"
            "Batch manufacturing of prototypes, tooling, jigs, and fixtures"
        ),
        "features": (
            "Large-format high-temperature industrial FFF printer. "
            "Build volume 610 × 508 × 508 mm for large single parts or multi-part batches. "
            "Uniformly heated chamber up to 300°C for PEEK, PEI, PEKK, PPSU and related materials. "
            "Closed-loop servo / high-precision ball-screw motion (XY precision cited at 12.5 µm class). "
            "Dual-extruder support for water-soluble and breakaway supports. "
            "24/7 production aids: auto-cleaning nozzles, filament auto-reload, jam/absence warnings. "
            "Open-filament compatible; industrial safety PLC, electromagnetic locks, redundant sensors. "
            "INTAMSUITE NEO path planning and material process packages."
        ),
        "weight_kg": 1450.0,
        "weight": "1450 kg",
        "dimensions_mm": "1710x1425x2080",
        "length_mm": 1710.0,
        "width_mm": 1425.0,
        "height_mm": 2080.0,
        "family_key": "intamsys:funmat-pro-610ht",
        "family_name": "FUNMAT PRO 610HT",
        "variant_code": "FUNMAT-PRO-610HT",
        "variant_label": "610HT",
        "videos": [],
        "source_note": (
            "Official PRO 610HT product render from intamsys.com/static/cms; comparison-table "
            "build size/weight/dimensions; PDP thermal and production feature copy; YouTube overviews."
        ),
    },
    "FUNMAT PRO 310 APOLLO": {
        "url": "https://www.intamsys.com/funmat-pro-310-apollo",
        "image": "https://www.intamsys.com/uploads/upload/images/20251118/b2ca8fd47dde62eccea69f361bc0bda6.png",
        "images": [
            "https://www.intamsys.com/uploads/upload/images/20251118/b2ca8fd47dde62eccea69f361bc0bda6.png",
            "https://www.intamsys.com/uploads/upload/images/20251118/67ccebc244df1ea8bde85cf0feae6d1f.png",
        ],
        "description": (
            "FUNMAT PRO 310 APOLLO is INTAMSYS's high-speed IDEX FFF platform engineered for "
            "PEEK/PAEK production-scale printing. Dual independent extruders, up to 200 mm/s "
            "PEEK-oriented printing, and INTAMQuality™ traceability for continuous manufacturing."
        ),
        "purpose": (
            "Continuous production of traceable PAEK parts\n"
            "High-speed manufacturing of aerospace, medical, and energy components"
        ),
        "features": (
            "Production-oriented PEEK/PAEK IDEX dual-extrusion system. "
            "Build volume single nozzle 305 × 260 × 260 mm; dual nozzles 260 × 260 × 260 mm. "
            "Print speeds up to 200 mm/s with PEEK-optimized dual-nozzle workflow. "
            "Supports full-range PAEK materials (PEEK, PEKK, PEEK-CF, PEEK-GF) plus engineering filaments. "
            "Auto-cleaning nozzles (no prime tower) to cut time and material waste. "
            "INTAMQuality™ real-time data logging and INTAMSUITE NEO adaptive path planning. "
            "Remote monitoring/control via INTAMSUITE Local Print for single printers or bureaus."
        ),
        "weight_kg": 80.0,
        "weight": "80 kg",
        "dimensions_mm": "700x655x750",
        "length_mm": 700.0,
        "width_mm": 655.0,
        "height_mm": 750.0,
        "release_year": 2025,
        "family_key": "intamsys:funmat-pro-310",
        "family_name": "FUNMAT PRO 310",
        "variant_code": "FUNMAT-PRO-310-APOLLO",
        "variant_label": "APOLLO",
        "videos": [
            "https://www.youtube.com/watch?v=U5ikVRBEWS0",
        ],
        "source_note": (
            "Official APOLLO product render from intamsys.com uploads (2025-11); comparison-table "
            "specs; PDP production/PEEK feature copy; YouTube INTAMSYS Apollo intro."
        ),
    },
}


def verify_image(url: str) -> bool:
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code == 405:
            resp = requests.get(url, headers=HEADERS, timeout=20, stream=True)
            resp.close()
        ctype = (resp.headers.get("content-type") or "").lower()
        # Some CMS assets omit content-type on HEAD; accept 200 + image extension.
        if resp.status_code != 200:
            return False
        if "image" in ctype:
            return True
        return bool(re.search(r"\.(png|jpe?g|webp)(\?|$)", url, re.I))
    except requests.RequestException:
        return False


def validate_media(urls: list[str]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Validate image magic bytes and reject duplicate content hashes."""
    valid: list[str] = []
    audit: dict[str, dict[str, Any]] = {}
    seen_hashes: set[str] = set()
    for url in dict.fromkeys(urls):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=45)
            body = resp.content
            magic_ok = body.startswith((
                b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF"
            ))
            digest = hashlib.md5(body).hexdigest()
            ok = resp.status_code == 200 and magic_ok and len(body) >= 10_000
            duplicate = digest in seen_hashes
            audit[url] = {
                "status": resp.status_code,
                "bytes": len(body),
                "md5": digest,
                "magic_ok": magic_ok,
                "duplicate": duplicate,
            }
            if ok and not duplicate:
                valid.append(url)
                seen_hashes.add(digest)
        except requests.RequestException as exc:
            audit[url] = {"error": str(exc)}
    return valid, audit


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.1)
    return ok, fail


def build_row(robot: dict, data: dict[str, Any]) -> dict[str, Any]:
    candidates = [data.get("image") or "", *(data.get("images") or [])]
    images, media_audit = validate_media([u for u in candidates if u])
    hero = images[0] if images else ""

    videos = enrich_video_list(data.get("videos") or [])
    row: dict[str, Any] = {
        "name": robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CN",
        "description": data["description"],
        "purpose": data["purpose"],
        "features": data["features"],
        "url": data["url"],
        "image": hero,
        "images": images,
        "video_urls": videos,
        "movement_type_keys": "stationary",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing",
        "weight_kg": data.get("weight_kg"),
        "weight": data.get("weight") or "",
        "dimensions_mm": data.get("dimensions_mm") or "",
        "length_mm": data.get("length_mm"),
        "width_mm": data.get("width_mm"),
        "height_mm": data.get("height_mm"),
        "release_year": data.get("release_year"),
        "availability_status": AVAILABLE,
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": FAMILY_URL,
        "model_name": robot["name"],
        "variant_code": data["variant_code"],
        "variant_label": data["variant_label"],
        "product_url_scope": "exact_variant",
        "tags": TAGS_BY_NAME.get(robot["name"]) or "Manufacturing|Industrial|3D-Printed|Factory",
        "sources": [
            {"url": data["url"], "type": "website", "title": f"{robot['name']} product page"},
            {"url": HELP_URLS[robot["name"]], "type": "documentation", "title": f"{robot['name']} documentation"},
        ],
        "information_source_urls": [data["url"], HELP_URLS[robot["name"]]],
        "research_notes": (
            f"{data.get('source_note') or 'INTAMSYS FUNMAT product enrichment.'} "
            "Build volume remains in features because the Robot schema has no typed build-volume fields. "
            "Print-head speed is mm/s and was not written to the km/h robot locomotion field."
        ),
        "_media_audit": media_audit,
    }
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix INTAMSYS FUNMAT robots for company 1073")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") != "published"
    ]
    print(f"targets: {len(robots)}")

    plan = []
    staging: dict[int, dict] = {}
    for robot in robots:
        data = ROBOT_DATA.get(robot["name"])
        if not data:
            print(f"SKIP {robot['id']} {robot['name']}: no curated data")
            continue
        row = build_row(robot, data)
        media_audit = row.pop("_media_audit")
        staging[int(robot["id"])] = row
        plan.append({
            "id": robot["id"],
            "name": robot["name"],
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "weight_kg": row.get("weight_kg"),
            "dimensions_mm": row.get("dimensions_mm"),
            "typed_dimensions": [
                row.get("length_mm"), row.get("width_mm"), row.get("height_mm")
            ],
            "family_key": row.get("family_key"),
            "availability_status": row.get("availability_status"),
            "media_audit": media_audit,
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
        })
        print(
            f"{robot['name']}: img={'yes' if row.get('image') else 'no'} "
            f"feat={len(row.get('features') or '')} weight={row.get('weight_kg')} "
            f"dims={row.get('dimensions_mm')} vids={len(row.get('video_urls') or [])} "
            f"tags={row.get('tags')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "intamsys-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if any(
        not p["image"] or not p["features_len"] or not p["tags"]
        or not p["weight_kg"] or not p["dimensions_mm"]
        or not all(p["typed_dimensions"]) or not p["family_key"]
        or p["availability_status"] != AVAILABLE
        for p in plan
    ):
        print("ERROR: incomplete enrichment", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="intamsys-fix-"))
    imported: list[int] = []
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0}
    all_ok = True
    for item in plan:
        rid = item["id"]
        row = staging[rid]
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = import_staging(
            fpath,
            patch=False,
            force_overwrite=True,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=True,
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result.get('errors')}", file=sys.stderr)
            continue
        imported.append(rid)
        data = ROBOT_DATA[row["name"]]
        video_result = client.bulk_import_robots(
            [row],
            update_existing=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_videos=True,
        )
        if video_result.get("error_count"):
            all_ok = False
            print(f"VIDEO REPLACE FAIL {rid}: {video_result}", file=sys.stderr)
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "pending_review",
                "availability_status": AVAILABLE,
                "length_mm": data["length_mm"],
                "width_mm": data["width_mm"],
                "height_mm": data["height_mm"],
                "weight_kg": data["weight_kg"],
                "release_year": data.get("release_year"),
                "family_key": data["family_key"],
                "family_name": data["family_name"],
                "family_url": FAMILY_URL,
                "model_name": row["name"],
                "variant_code": data["variant_code"],
                "variant_label": data["variant_label"],
                "product_url_scope": "exact_variant",
                "purpose": data["purpose"],
                "information_source_urls": [
                    {
                        "url": source["url"],
                        "title": source["title"],
                        "source_type": source["type"],
                    }
                    for source in row["sources"]
                ],
            },
        )
        for k in totals:
            totals[k] += result.get(k, 0) or 0

    print(json.dumps({"ok": all_ok, **totals}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
