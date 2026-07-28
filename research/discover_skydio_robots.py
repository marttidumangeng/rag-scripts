"""Curated Skydio (137) discovery + deep enrich.

CREATE pending_review:
  Skydio X10 — current enterprise flagship (OEM /x10 + technical-specs)
  Skydio X10D — defense/tactical twin (OEM /x10d)

ENRICH pending_review:
  Skydio X2 (170) — Chinese junk narrative; WRONG hero (Shield AI Nova-style
    indoor drone on CDN filename robot-170-skydio-r1_*); replace with OEM X2E
    datasheet product render; cite pages.skydio.com X2E datasheet

REJECT:
  Skydio R1 (344) — off live catalog (/r1 404); CDN hero is same wrong Nova-style
    asset as X2; no OEM-hosted R1 product page or verified R1 hero this pass

SKIP:
  Dock for X10 — docking station infrastructure (not an aircraft SKU)
  R10 / Paraverse / attachments — radio/software/accessories

Usage:
  python discover_skydio_robots.py
  python discover_skydio_robots.py --apply --copy-media
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

COMPANY_ID = 137
COMPANY_SLUG = "skydio"
COMPANY_NAME = "Skydio"
US_ID = 20
REPORT = _RESEARCH_DIR / "staging" / "reports" / "skydio-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# Sanity CDN — use w=1600 transforms (public, no signed params)
def sanity(asset: str, w: int = 1600) -> str:
    return (
        f"https://cdn.sanity.io/images/mgxz50fq/production-v3-red/{asset}"
        f"?w={w}&fit=max&auto=format"
    )


REJECT = [
    {
        "id": 344,
        "name": "Skydio R1",
        "reason": (
            "off_catalog: /r1 404 on live OEM; superseded by X2/X10 line; "
            "CDN hero was wrong-brand indoor Nova-style drone (not R1) — "
            "fail-closed rather than ship contaminated media"
        ),
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "Skydio X10",
        "action": "create",
        "status": "pending_review",
        "url": "https://www.skydio.com/x10",
        "model_name": "X10",
        "availability_status": 11,
        "release_year": 2023,
        "category_slugs": "aerial|drone",
        "movement_type_keys": "aerial",
        "use_keys": "inspection|monitoring|patrol|surveillance|scanning|remote",
        "industry_keys": "security|defence|construction|government",
        "tags": (
            "Autonomous|Aerial|Drone|UAV|Inspection|Public Safety|"
            "Thermal|NDAA|AI|Enterprise"
        ),
        "weight_kg": 2.11,  # Connect SL incl. battery (OEM tech specs)
        "payload_kg": 0.385,  # max attachment payload (OEM /x10)
        "height_mm": 145.0,  # unfolded 5.7 in
        "width_mm": 650.0,  # unfolded 25.6 in
        "length_mm": 790.0,  # unfolded 31.1 in
        "speed": "Max horizontal 45 mph / 20 m/s (OEM technical specs)",
        "images": [
            # Labeled X10 sensor hero (OEM /x10 banner)
            sanity("6a6fef86c5dad572083363430f9a27971cc62a1a-2400x1300.png"),
            # X10 in Dock rooftop deployment (OEM)
            sanity("f7d19072039f498ee4f69635af8f5c127d4c49b8-3575x2507.jpg"),
            # Studio / product body (OEM)
            sanity("b6f32708c15ef1b6cc2310d71f70b4825e7ae198-3454x1922.png"),
            # Substation inspection flight (OEM)
            sanity("6bc55640edeabf47e5af325d0eb78777e339f6f8-2880x1582.png"),
        ],
        "videos": [],
        "video_queries": ["Skydio X10 official", "Skydio X10 drone"],
        "video_needles": ["skydio x10", "x10"],
        "video_reject": ["x2 only", "r1", "dji", "unboxing scam", "x10d only"],
        "description": (
            "Skydio X10 is Skydio's current enterprise autonomous drone: a backpack-portable "
            "quadcopter with modular multi-sensor packages (visual + radiometric thermal), "
            "onboard NVIDIA Jetson Orin AI, true 360° obstacle avoidance, and NightSense "
            "for autonomous flight in the dark. Designed, assembled, and supported in the USA; "
            "NDAA compliant."
        ),
        "features": (
            "Enterprise autonomous sUAS with modular VT300/V100 sensor packages "
            "(OEM /x10). "
            "OEM technical specs: weight Connect SL 4.65 lb / 2.11 kg (incl. battery); "
            "max takeoff 5.49 lb / 2.49 kg; unfolded 31.1×25.6×5.7 in; folded 13.8×6.5×4.7 in; "
            "max flight time 40 min; max hover 35 min; max horizontal speed 45 mph / 20 m/s; "
            "max gust 28.6 mph; IP55; ops temp −20°C to +45°C; service ceiling 15,000 ft. "
            "NVIDIA Jetson Orin + Qualcomm Snapdragon 865; six navigation cameras for "
            "true 360° obstacle avoidance; NightSense visible/IR autonomy at night. "
            "FLIR Boson+ radiometric thermal up to 640×512 / <30 mK on VT300 packages; "
            "up to 64 MP narrow / 48 MP telephoto / 50 MP wide visual modules. "
            "Four attachment bays; max attachment payload 385 g. Connect SL up to 12 km / "
            "7.5 mi LOS; Connect 5G where cellular available. AES-256 / NDAA compliant."
        ),
        "purpose": (
            "Autonomous aerial inspection, public-safety DFR, and enterprise situational "
            "awareness"
        ),
        "sources": [
            {"url": "https://www.skydio.com/x10", "title": "Skydio X10"},
            {
                "url": "https://www.skydio.com/x10/technical-specs",
                "title": "Skydio X10 Technical Specs",
            },
            {
                "url": "https://www.skydio.com/resources/datasheets/skydio-x10",
                "title": "Skydio X10 datasheet",
            },
        ],
    },
    {
        "name": "Skydio X10D",
        "action": "create",
        "status": "pending_review",
        "url": "https://www.skydio.com/x10d",
        "model_name": "X10D",
        "availability_status": 11,
        "release_year": 2024,
        "category_slugs": "aerial|drone",
        "movement_type_keys": "aerial",
        "use_keys": "patrol|surveillance|monitoring|inspection|remote|exploration",
        "industry_keys": "defence|security|government",
        "tags": (
            "Autonomous|Aerial|Drone|UAV|Defense|Tactical|Thermal|NDAA|AI|Military"
        ),
        "weight_kg": 2.11,
        "payload_kg": 0.385,
        "speed": "Max horizontal 45 mph (OEM /x10d)",
        "images": [
            # Labeled X10D sensor banner (OEM /x10d) — distinct from X10 banner hash
            sanity("49fded83d4ba104d90abd0ea821424b94a7cd8c9-2400x1300.png"),
            sanity("99d884fbf52968d4e6b023c5a9f65b0f9376bc92-2930x1228.png"),
            sanity("c2f339973d16942e62a0530277386339dfbec411-1280x961.png"),
        ],
        "videos": [],
        "video_queries": ["Skydio X10D official", "Skydio X10D drone"],
        "video_needles": ["skydio x10d", "x10d"],
        "video_reject": ["x10 only", "x2", "dji", "unboxing scam"],
        "description": (
            "Skydio X10D is the defense/tactical twin of X10: an open modular sUAS built "
            "for EW-resilient operations with the same class-leading sensors and onboard AI, "
            "plus RAS-A / MAVLink openness for government flight apps. Same USA design and "
            "assembly lineage as X10; NDAA compliant."
        ),
        "features": (
            "Defense/tactical autonomous sUAS sharing X10's modular sensor architecture "
            "(OEM /x10d). "
            "OEM claims: max flight speed 45 mph; deploy under 40 seconds; aircraft IP55; "
            "controller IP54; open modular platform with four attachment bays; RAS-A "
            "compliance and MAVLink for third-party/government flight software. "
            "World-leading onboard autonomy and 360° obstacle avoidance for contested and "
            "complex environments; designed for distributed/dispersed rucksack-portable "
            "operations. Designed, assembled, and supported in the USA."
        ),
        "purpose": "Tactical/defense autonomous reconnaissance and situational awareness",
        "sources": [
            {"url": "https://www.skydio.com/x10d", "title": "Skydio X10D"},
            {
                "url": "https://www.skydio.com/x10/technical-specs",
                "title": "Skydio X10/X10D shared aircraft technical specs",
            },
        ],
    },
    {
        "name": "Skydio X2",
        "id": 170,
        "action": "enrich",
        "status": "pending_review",
        "url": "https://pages.skydio.com/rs/784-TUF-591/images/skydio-x2e-datasheet-x2-pg.pdf",
        "model_name": "X2",
        # Prior-gen: live /x2 PDP 404; OEM hub centers on X10 — Discontinued (id 4)
        "availability_status": 4,
        "release_year": 2020,
        "category_slugs": "aerial|drone",
        "movement_type_keys": "aerial",
        "use_keys": "inspection|monitoring|patrol|surveillance|scanning|remote",
        "industry_keys": "security|defence|construction|government",
        "tags": (
            "Autonomous|Aerial|Drone|UAV|Inspection|Public Safety|Thermal|NDAA|AI"
        ),
        "weight_kg": 1.325,  # with battery (OEM X2E datasheet)
        "height_mm": 211.0,  # 8.3 in unfolded
        "width_mm": 569.0,  # 22.4 in
        "length_mm": 663.0,  # 26.1 in
        "speed": "Max flight speed 25 mph / 40 km/h (OEM X2E Color datasheet)",
        "images": [
            # OEM X2E datasheet product render (pages.skydio.com)
            "https://pages.skydio.com/rs/784-TUF-591/images/X2E.png",
            # Border Patrol field hover with X2-class aircraft (OEM marketing CDN)
            sanity("a898c83d202a3f61db965d6278bd410b44cb4ee6-3277x1999.png"),
        ],
        "videos": [],
        "video_queries": ["Skydio X2E official", "Skydio X2 drone"],
        "video_needles": ["skydio x2", "x2e", "x2d"],
        "video_reject": ["x10", "r1", "dji", "unboxing scam"],
        "description": (
            "Skydio X2 is Skydio's prior-generation enterprise/defense autonomous drone "
            "(X2E enterprise / X2D defense). Foldable carbon-fiber airframe with 360° AI "
            "obstacle avoidance, up to 35 minutes flight time, and Color or Color/Thermal "
            "sensor options. Still documented via OEM datasheets though the live product "
            "hub now centers on X10."
        ),
        "features": (
            "Prior-gen autonomous enterprise/defense sUAS; X2E (enterprise) and X2D "
            "(defense) variants (OEM blog + X2E datasheets). "
            "OEM X2E datasheet: weight 1325 g with battery; unfolded 26.1×22.4×8.3 in "
            "(66×56×20 cm); folded 11.9×5.5×3.6 in; flight time up to 35 min; wireless "
            "range up to 3.7 mi / 6 km (commercial); max speed 25 mph; wind resistance "
            "23 mph; service ceiling up to 12,000 ft; ops temp −10°C to 43°C. "
            "Six 4K navigation cameras for 360° obstacle avoidance; dual-sensor Color/"
            "Thermal option with 12 MP color + FLIR 320×256 thermal. NDAA compliant; "
            "designed and assembled in the USA."
        ),
        "purpose": (
            "Autonomous aerial inspection, public safety, and defense situational awareness "
            "(prior-gen platform)"
        ),
        "sources": [
            {
                "url": "https://pages.skydio.com/rs/784-TUF-591/images/skydio-x2e-datasheet-x2-pg.pdf",
                "title": "Skydio X2E datasheet (OEM)",
            },
            {
                "url": "https://pages.skydio.com/rs/784-TUF-591/images/X2E.pdf",
                "title": "Skydio X2E Color/Thermal datasheet",
            },
            {
                "url": "https://www.skydio.com/blog/announces-x2-drone-shipping-and-introducing-skydio-cloud",
                "title": "Skydio X2 shipping announcement",
            },
        ],
        "notes_extra": (
            "[MEDIA FIX 2026-07-20] Replaced wrong-brand CDN hero "
            "(indoor Nova-style drone, filename robot-170-skydio-r1_*) with OEM X2E "
            "datasheet render.\n---\n"
        ),
    },
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers=UA, timeout=90)
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
                return f"ok {resp.text[:100]}"
            if resp.status_code not in (502, 503, 504):
                return f"HTTP {resp.status_code}"
        except requests.RequestException:
            pass
        time.sleep(2**attempt)
    return "fail"


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
    needles = [n.lower() for n in (spec.get("video_needles") or [spec["name"].lower()])]
    reject = [b.lower() for b in (spec.get("video_reject") or [])]
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        channel = (v.get("channel") or v.get("author_name") or "").lower()
        blob = f"{title} {channel}"
        if any(b in blob for b in reject):
            continue
        if any(n in blob for n in needles):
            # tighten X10 vs X10D
            if spec["name"] == "Skydio X10" and "x10d" in title and "x10 " not in title:
                continue
            if spec["name"] == "Skydio X10D" and "x10d" not in title and "x10 d" not in title:
                if "x10d" not in blob:
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
                "source_hash": f"skydio-en-force-{rid}-20260720-{loc}",
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
        "[AI Research] Skydio curated discover/enrich 2026-07-20. "
        "Created X10 + X10D; enriched X2; rejected R1 (off-catalog + bad media)."
    )
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
        "video_urls": kept,
        "movement_type_keys": spec.get("movement_type_keys") or "aerial",
        "category_slugs": spec.get("category_slugs") or "aerial",
        "use_keys": spec.get("use_keys") or "inspection",
        "industry_keys": spec.get("industry_keys") or "security",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or 11,
        "research_notes": (
            "[AI Research] Skydio 2026-07-20. X10/X10D from OEM PDPs + tech specs; "
            "X2 from OEM X2E datasheets; R1 rejected."
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
    ):
        if spec.get(k) is not None:
            row[k] = spec[k]
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
    ):
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
    plan: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "robots": [],
        "rejects": REJECT,
        "apply": bool(args.apply),
    }
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    used_hashes: set[str] = set()

    for spec in PRODUCTS:
        print(f"Building {spec['name']} ({spec['action']})…")
        row = build_row(spec, used_hashes)
        rows.append((spec, row))
        plan["robots"].append(
            {
                "name": spec["name"],
                "id": spec.get("id"),
                "action": spec["action"],
                "images_n": len(row.get("images") or []),
                "videos_n": len(row.get("video_urls") or []),
                "feat_len": len(row.get("features") or ""),
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
            patch=True,
            force_overwrite=True,
            replace_media=bool(row.get("images")),
            status=spec.get("status") or "pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        rid = spec.get("id")
        if not rid and isinstance(result, dict):
            for item in result.get("results") or []:
                if item.get("action") in ("created", "updated") and item.get("id"):
                    rid = item["id"]
                    spec["id"] = rid
        if rid:
            patch_fields(client, int(rid), row)
            force_en_translations(client, int(rid), row)
            if args.copy_media and row.get("images"):
                print(f"copy-media {rid}:", copy_media(int(rid)))
            for item in plan["robots"]:
                if item["name"] == spec["name"]:
                    item["id"] = rid
                    item["import"] = result

    for rej in REJECT:
        print(f"Rejecting {rej['id']} {rej['name']}…")
        out = reject_robot(client, int(rej["id"]), rej["reason"])
        print(f"  → {out}")
        rej["result"] = out

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
