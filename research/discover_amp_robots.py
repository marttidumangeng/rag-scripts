"""Curated AMP Robotics (259) enrich — Delta + Delta Compact; reject non-robots.

CONTEXT (2026-07-20):
  10 pending_review with junk homepage features, empty country/family, Released
  avail, mostly no typed specs. Only real robot SKUs are Delta + Delta Compact
  (Cortex-C rename). Software / vision / pneumatic jets / AMP ONE / Cortex dup
  are rejected.

ENRICH:
  1472 AMP Delta — Available; US; family amp:delta; OEM Delta Datasheet 2024
  1474 AMP Delta Compact — rename from Cortex-C; same family; Compact Datasheet 2024

REJECT:
  1475 Clarity, 1469 Vision, 1468 SmartTons, 1467 Insight (software/data)
  1471 MicroJet, 1470 Jet (pneumatic air-jet, not arm robots)
  1473 Cortex (duplicate/superseded by Delta)
  1466 AMP ONE (facility-scale MRF, not a single robot)

Media (research-staging/amp/):
  amp-delta-studio-hero.jpg          (Prismic delta-new-hero)
  amp-delta-compact-facility-hero.jpg (facility effector still)

Usage:
  python _amp_prep_heroes.py
  python discover_amp_robots.py
  python discover_amp_robots.py --apply --copy-media
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

COMPANY_ID = 259
COMPANY_SLUG = "amp-robotics"
COMPANY_NAME = "AMP Robotics"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "amp-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

DELTA_URL = "https://ampsortation.com/technologies/delta"
COMPACT_URL = "https://www.amprobotics.com/compact-robotic-sorting"
FAMILY_KEY = "amp:delta"
FAMILY_NAME = "AMP Delta"
FAMILY_URL = DELTA_URL

DELTA_HERO = (
    "https://cdn.robotaigeek.com/research-staging/amp/amp-delta-studio-hero.jpg"
)
COMPACT_HERO = (
    "https://cdn.robotaigeek.com/research-staging/amp/"
    "amp-delta-compact-facility-hero.jpg"
)

# OEM Delta Datasheet 2024 (ampsortation.com) — installed height 2743 mm,
# footprint 2134×2134 mm, weight 1180 kg, max pick object 4.5 kg, ≤80 ppm.
# Conveyor max 1.5 m/s is belt speed — do NOT map to robot speed km/h.
# OEM Delta Compact Datasheet 2024 — height 1347 mm above belt, belt length
# 1651 mm, system weight 135–227 kg (range → leave weight blank), payload 1 kg.

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 1472,
        "name": "AMP Delta",
        "model_name": "Delta",
        "variant_code": "Delta",
        "variant_label": "Standard",
        "url": DELTA_URL,
        "image": DELTA_HERO,
        "release_year": 2024,
        "weight_kg": 1180,
        "height_mm": 2743,
        "width_mm": 2134,
        "length_mm": 2134,
        "payload_kg": 4.5,
        "description": (
            "AMP Delta is a high-speed AI robotic arm sortation system that "
            "replaces manual sorters on material recovery lines, recovering "
            "recyclables with consistent 24/7 pick rates."
        ),
        "purpose": "AI robotic sortation of recyclables on MRF conveyor lines",
        "features": (
            "OEM AMP Delta Datasheet 2024 (ampsortation.com/technologies/delta): "
            "delta-arm sortation cell for MRFs; pick rate up to 80 ppm (OEM: ~2× "
            "manual sortation); max pick object weight 4.5 kg (110 lb); up to 4 "
            "discrete drop locations; installed height 2743 mm (S-model 2286 mm); "
            "installed footprint 2134×2134 mm; system weight 1180 kg (2600 lb); "
            "max belt angle 10°; conveyor speed up to 1.5 m/s (300 fpm); conveyor "
            "width 457–1066 mm (S-model max 762 mm); control cabinet "
            "1010×530×1980 mm; 300+ deployments claimed; optional dual-gripper; "
            "pairs with AMP Clarity data platform. Soft: no public MSRP; conveyor "
            "belt speed is not typed as robot speed."
        ),
        "video_queries": [
            "AMP Robotics Delta sorting robot",
            "AMP Delta robotic sortation MRF",
            "AMP Robotics recycling robot arm",
        ],
        "video_needles": ["amp", "delta", "sort", "recycl"],
        "video_reject": [
            "boston dynamics",
            "figure ai",
            "omron",
            "abb ",
            "fanuc",
            "kuka",
            "clarity app only",
        ],
    },
    {
        "id": 1474,
        "name": "AMP Delta Compact",
        "model_name": "Delta Compact",
        "variant_code": "Compact",
        "variant_label": "Compact",
        "url": COMPACT_URL,
        "image": COMPACT_HERO,
        "release_year": 2024,
        "height_mm": 1347,
        "length_mm": 1651,
        "payload_kg": 1.0,
        # weight 135–227 kg range — leave blank; cite in features
        "description": (
            "AMP Delta Compact is the belt-mounted, space-efficient sibling of "
            "AMP Delta — the same AI identification and robotic pick technology "
            "in a smaller over-belt package for tight MRF installs."
        ),
        "purpose": "Belt-mounted AI robotic sortation on space-constrained MRF lines",
        "features": (
            "OEM AMP Delta Compact Datasheet 2024 + amprobotics.com/"
            "compact-robotic-sorting: belt-mounted delta-arm sorter; pick rate "
            "up to 65 ppm (~1.5× human); max pick object 1 kg (2.2 lb); up to 2 "
            "drop locations; installed height 1347 mm above belt; installed belt "
            "length 1651 mm; system weight 135–227 kg (300–500 lb — range, not "
            "typed); max belt angle 20°; conveyor speed up to 0.75 m/s (150 fpm); "
            "max conveyor width 914 mm; over-belt mount with optional floor "
            "structure; control cabinet 1010×530×1980 mm; formerly marketed as "
            "Cortex-C. Soft: no public MSRP; weight left blank due to OEM range."
        ),
        "video_queries": [
            "AMP Robotics Compact sorting robot",
            "AMP Delta Compact robotic sorting",
            "AMP Cortex Compact robot",
        ],
        "video_needles": ["amp", "compact", "cortex", "sort", "recycl"],
        "video_reject": ["boston dynamics", "figure ai"],
    },
]

REJECTS: list[tuple[int, str]] = [
    (
        1475,
        "non_robot: AMP Clarity is a software/data platform, not a robot SKU",
    ),
    (
        1469,
        "non_robot: AMP Vision is a vision/computing platform, not a robot SKU",
    ),
    (
        1468,
        "non_robot: AMP SmartTons is software, not a robot SKU",
    ),
    (
        1467,
        "non_robot: AMP Insight is analytics software, not a robot SKU",
    ),
    (
        1471,
        "non_robot: AMP MicroJet is a pneumatic air-jet sorter, not an arm robot",
    ),
    (
        1470,
        "non_robot: AMP Jet is a pneumatic air-jet sorter, not an arm robot",
    ),
    (
        1473,
        "duplicate: AMP Cortex superseded by AMP Delta (keep 1472; same product line)",
    ),
    (
        1466,
        "non_robot: AMP ONE is a facility-scale MRF system, not a single robot SKU",
    ),
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=120)
        data = r.content or b""
        if r.status_code != 200 or len(data) < 2000:
            return False, "", len(data)
        is_jpeg = data[:3] == b"\xff\xd8\xff"
        is_png = data[:8] == b"\x89PNG\r\n\x1a\n"
        is_webp = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        if not (is_jpeg or is_png or is_webp):
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
    urls: list[str] = []
    for q in spec.get("video_queries") or []:
        urls.extend(yt_search(q, limit=6))
    seen: set[str] = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
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
        kept.append(v)
    return kept[:3]


def force_en_translations(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"amp-en-force-{rid}-20260720-{loc}",
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


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "notes": f"[REJECTED 2026-07-20] {reason}\n---\n",
                "rejection_reason": reason[:500],
            },
        )
        return "patched-rejected"
    except Exception as e:  # noqa: BLE001
        return f"fail {e}"


def build_row(spec: dict[str, Any], used_hashes: set[str]) -> dict[str, Any]:
    images: list[str] = []
    ok, md5, nbytes = download_ok(spec["image"])
    if not ok:
        print(f"  !! image fail {spec['image']}")
    elif md5 in used_hashes:
        print(f"  !! hash collision {md5[:12]}")
    else:
        used_hashes.add(md5)
        images.append(spec["image"])
        print(f"  img ok {md5[:12]} {nbytes}")

    kept = filter_videos(spec)
    print(f"  videos kept={len(kept)}")
    for v in kept:
        print(f"    - {(v.get('title') or '')[:80]}")

    notes = (
        f"[AI Research] AMP enrich 2026-07-20. US; Available; family {FAMILY_KEY}; "
        f"typed specs from OEM {spec['name']} Datasheet 2024; rename/keep as listed."
    )
    row: dict[str, Any] = {
        "id": spec["id"],
        "name": spec["name"],
        "model_name": spec["model_name"],
        "variant_code": spec["variant_code"],
        "variant_label": spec["variant_label"],
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
        "movement_type_keys": "stationary",
        "category_slugs": "warehouse-robots|arm",
        "use_keys": "sorting|pick-and-place|material-handling",
        "industry_keys": "logistics|manufacturing",
        "tags": "Recycling|MRF|Sorting|AI|Stationary|Arm|Pick-and-place|Delta|USA",
        "source_locale": "en",
        "availability_status": AVAILABLE,
        "family_key": FAMILY_KEY,
        "family_name": FAMILY_NAME,
        "family_url": FAMILY_URL,
        "product_url_scope": "exact_variant",
        "release_year": spec["release_year"],
        "research_notes": notes,
        "sources": [
            {"url": DELTA_URL, "type": "website", "title": "AMP Delta product"},
            {"url": COMPACT_URL, "type": "website", "title": "AMP Compact sorting"},
            {
                "url": "https://ampsortation.com/",
                "type": "website",
                "title": "AMP Sortation home",
            },
        ],
        "information_source_urls": [DELTA_URL, COMPACT_URL, "https://ampsortation.com/"],
        "notes": notes,
    }
    for k in ("weight_kg", "height_mm", "width_mm", "length_mm", "payload_kg"):
        if spec.get(k) is not None:
            row[k] = spec[k]
    return row


def patch_fields(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": AVAILABLE,
        "name": row["name"],
        "model_name": row["model_name"],
        "variant_code": row["variant_code"],
        "variant_label": row["variant_label"],
        "description": row["description"],
        "features": row["features"],
        "purpose": row["purpose"],
        "url": row["url"],
        "source_locale": "en",
        "notes": row["notes"],
        "family_key": FAMILY_KEY,
        "family_name": FAMILY_NAME,
        "family_url": FAMILY_URL,
        "product_url_scope": "exact_variant",
        "release_year": row["release_year"],
        "tags": row["tags"].split("|") if isinstance(row["tags"], str) else row["tags"],
        "s3_image": None,
    }
    for k in ("weight_kg", "height_mm", "width_mm", "length_mm", "payload_kg"):
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


def re_patch_specs(client: ResearchApiClient, row: dict[str, Any]) -> None:
    rid = row["id"]
    body: dict[str, Any] = {
        "availability_status": AVAILABLE,
        "release_year": row["release_year"],
        "family_key": FAMILY_KEY,
        "family_name": FAMILY_NAME,
        "family_url": FAMILY_URL,
        "s3_image": None,
    }
    for k in ("weight_kg", "height_mm", "width_mm", "length_mm", "payload_kg"):
        if row.get(k) is not None:
            body[k] = row[k]
    client._patch(f"robots/robots/{rid}/", body)
    print(f"  re-PATCH specs/avail/family {rid}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--skip-reject", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    used: set[str] = set()
    rows: list[dict[str, Any]] = []
    for spec in PRODUCTS:
        print(f"Building {spec['id']} {spec['name']}...")
        rows.append(build_row(spec, used))

    plan = {
        "company_id": COMPANY_ID,
        "apply": bool(args.apply),
        "enrich": [
            {
                "id": r["id"],
                "name": r["name"],
                "images_n": len(r.get("images") or []),
                "videos_n": len(r.get("video_urls") or []),
                "feat_len": len(r.get("features") or ""),
                "weight_kg": r.get("weight_kg"),
                "payload_kg": r.get("payload_kg"),
                "release_year": r.get("release_year"),
            }
            for r in rows
        ],
        "reject": [{"id": rid, "reason": reason} for rid, reason in REJECTS],
    }

    if not args.apply:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps({"plan": plan, "rows": rows}, indent=2), encoding="utf-8"
        )
        print(f"Dry-run -> {REPORT}")
        return 0

    staging = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    for row in rows:
        if not row.get("images"):
            print(f"FAIL CLOSED — no image for {row['id']}")
            return 1
        slug = re.sub(r"[^a-z0-9]+", "-", row["name"].lower()).strip("-")
        path = staging / f"{slug}.json"
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
        print(f"import {row['id']}:", result)
        patch_fields(client, row["id"], row)
        force_en_translations(client, row["id"], row)
        if args.copy_media:
            print(f"copy-media {row['id']}:", copy_media(row["id"]))
        re_patch_specs(client, row)

    reject_results = []
    if not args.skip_reject:
        for rid, reason in REJECTS:
            status = reject_robot(client, rid, reason)
            print(f"reject {rid}: {status}")
            reject_results.append({"id": rid, "status": status, "reason": reason})

    plan["reject_results"] = reject_results
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
