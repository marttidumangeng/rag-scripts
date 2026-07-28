"""Curated Monarch Tractor (265) enrich.

CONTEXT (2026-07-20):
  Live OEM: MK-V electric driver-optional tractor (monarchtractor.com).
  Two pending records share the same hardware platform:
    3875 MK-V — general product page
    3881 MK-V Vineyard Tractor — vineyard vertical landing (same Spec Sheet)

ENRICH both (keep as distinct listing URLs / heroes; same typed dims from OEM sheet).
  Spec sheet: Monarch_MKV_SpecSheet (hubfs) — L/W/H, weight, hitch lift, runtime.

Usage:
  python discover_monarch_robots.py
  python discover_monarch_robots.py --apply --copy-media
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

COMPANY_ID = 265
COMPANY_SLUG = "monarch-tractor"
COMPANY_NAME = "Monarch Tractor"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "monarch-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

MKV_URL = "https://www.monarchtractor.com/mk-v-electric-tractor"
VINEYARD_URL = "https://www.monarchtractor.com/vineyard-tractor"
SPEC_SHEET = (
    "https://www.monarchtractor.com/hubfs/01_MK-V%20Documents/"
    "Monarch_MKV_SpecSheet_v.2024.11.pdf"
)
# Verified owned CDN heroes (distinct content hashes; visual QA 2026-07-20)
MKV_HERO = (
    "https://cdn.robotaigeek.com/robots/original/"
    "robot-3875-mk-v-an-autonomous-electric-tractor-v1783781449.jpeg"
)
VINEYARD_HERO = (
    "https://cdn.robotaigeek.com/robots/original/"
    "robot-3881-mk-v-vineyard-tractor-v1783781450.jpg"
)

# OEM Spec Sheet (in / mm): length 146.7 in (3725), height 92.1 (2340),
# min width 48.4 (1230); base weight 5750 lb (2610 kg); hitch lift 2200 lb (997 kg);
# runtime up to 14 h; charge ~5 h @ 80 A.
TYPED = {
    "length_mm": 3725,
    "height_mm": 2340,
    "width_mm": 1230,
    "weight_kg": 2610,
    "payload_kg": 997,  # 3-point hitch lift capacity
    "runtime_minutes": 840,
    "charging_time_minutes": 300,
}

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 3875,
        "name": "Monarch MK-V",
        "model_name": "MK-V",
        "action": "enrich",
        "status": "pending_review",
        "url": MKV_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "agricultural-robots|autonomous-mobile-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "agriculture|farming",
        "industry_keys": "agriculture",
        "tags": (
            "Agriculture|Electric|Autonomous|Tractor|Wheeled|USA|Specialty-crops"
        ),
        "images": [MKV_HERO],
        "videos": [],
        "video_queries": [
            "Monarch Tractor MK-V electric",
            "Monarch MK-V autonomous tractor",
        ],
        "video_needles": ["monarch", "mk-v", "mkv"],
        "video_reject": ["john deere", "new holland", "kubota", "farmwise", "carbon"],
        "description": (
            "Monarch MK-V is a 100% electric, driver-optional, data-driven compact "
            "tractor for specialty crops and general farm work. It combines "
            "electrification, WingspanAI fleet/ops software, and optional autonomy "
            "with a Cat I/II three-point hitch for existing implements."
        ),
        "features": (
            "100% electric driver-optional tractor (OEM monarchtractor.com/mk-v-"
            "electric-tractor + Hardware Spec Sheet). Peak motor power 70 HP "
            "(52 kW); rated 40 HP (30 kW); PTO 40 HP @ 540 rpm rear; 4WD push-"
            "button transmission 9F/3R. Runtime up to 14 hours (operation/"
            "implement dependent); charge ~5 hours with 80 A Level 2 (J1772 Type 1 "
            "up to 80 A) or ~10 hours with 40 A. Exportable power 110/220/12 V + "
            "USB (~5.6 kW). Cat I/II 3-point hitch lift 2,200 lb (997 kg); drawbar "
            "tow 5,500 lb. Typed dims from OEM sheet: L 3,725 mm × W min 1,230 mm "
            "× H 2,340 mm; base weight 2,610 kg. 360° roof cameras, LED work "
            "lights, smart touchscreen, collision/PTO safety in driverless modes. "
            "Configs include MK-V Standard (R1 Ag tires) and MK-V Dairy (R4 + "
            "push blade). Warranty cited: tractor 4 yr/4,000 hr; battery 8 yr/"
            "8,000 hr."
        ),
        "purpose": (
            "Electric driver-optional compact tractor for specialty and general "
            "farm operations"
        ),
        "sources": [
            {"url": MKV_URL, "title": "Monarch MK-V Electric Tractor (OEM)"},
            {"url": SPEC_SHEET, "title": "Monarch MK-V Hardware Spec Sheet (OEM PDF)"},
            {
                "url": "https://www.monarchtractor.com/mk-v-compatible-implements",
                "title": "MK-V Compatible Implements",
            },
        ],
        **TYPED,
    },
    {
        "id": 3881,
        "name": "Monarch MK-V Vineyard Tractor",
        "model_name": "MK-V Vineyard",
        "action": "enrich",
        "status": "pending_review",
        "url": VINEYARD_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "agricultural-robots|autonomous-mobile-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "agriculture|farming",
        "industry_keys": "agriculture",
        "tags": (
            "Agriculture|Electric|Autonomous|Tractor|Vineyard|Wheeled|USA"
        ),
        "images": [VINEYARD_HERO],
        "videos": [],
        "video_queries": [
            "Monarch MK-V vineyard tractor",
            "Monarch Tractor vineyard Row Follow",
        ],
        "video_needles": ["monarch", "vineyard", "mk-v", "mkv"],
        "video_reject": ["john deere", "new holland", "kubota", "farmwise", "carbon"],
        "description": (
            "Monarch MK-V Vineyard is the same MK-V electric driver-optional "
            "platform positioned for narrow-row vineyard work — mowing, undervine "
            "weeding, and harvest support — with Row Follow autosteer and "
            "WingspanAI ops visibility."
        ),
        "features": (
            "Vineyard-focused MK-V listing (OEM monarchtractor.com/vineyard-"
            "tractor). Same hardware Spec Sheet as MK-V: 40–70 HP electric, up to "
            "14 h runtime, ~6 h charge (5–95% @ 80 A on vineyard page), Cat I/II "
            "hitch 2,200 lb lift, 4WD. Emphasizes zero-emission mowing for organic/"
            "ESG reporting, Row Follow hands-free row centering, bilingual smart "
            "screen, 360° cameras, PTO proximity cut-off, and exportable power for "
            "harvest. Typed dims/weight/payload/runtime from shared OEM Spec Sheet "
            "(L 3,725 × W min 1,230 × H 2,340 mm; 2,610 kg; hitch 997 kg; 840 min "
            "runtime). Not a separate chassis SKU — vertical application of MK-V."
        ),
        "purpose": (
            "Electric driver-optional tractor configured for vineyard specialty "
            "operations"
        ),
        "sources": [
            {"url": VINEYARD_URL, "title": "Monarch MK-V Vineyard Tractor (OEM)"},
            {"url": SPEC_SHEET, "title": "Monarch MK-V Hardware Spec Sheet (OEM PDF)"},
            {"url": MKV_URL, "title": "Monarch MK-V product page"},
        ],
        **TYPED,
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
        if "monarch" not in blob:
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
        "[AI Research] Monarch Tractor curated enrich 2026-07-20. "
        "Typed dims/weight/hitch/runtime from OEM MK-V Spec Sheet; "
        "Vineyard listing shares hardware with MK-V."
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
        "category_slugs": spec.get("category_slugs") or "agricultural-robots",
        "use_keys": spec.get("use_keys") or "agriculture",
        "industry_keys": spec.get("industry_keys") or "agriculture",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Monarch 2026-07-20. Spec Sheet dims + hitch lift + "
            "runtime/charge; Available on live OEM."
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
        "runtime_minutes",
        "charging_time_minutes",
        "dof",
    ):
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
    for k in (
        "weight_kg",
        "height_mm",
        "width_mm",
        "length_mm",
        "speed",
        "release_year",
        "payload_kg",
        "runtime_minutes",
        "charging_time_minutes",
        "dof",
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
        "apply": bool(args.apply),
    }
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    used_hashes: set[str] = set()

    for spec in PRODUCTS:
        print(f"Building {spec['name']} ({spec['action']})…")
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
        # Keep existing owned CDN heroes — replace_media=False avoids wiping gallery
        # with same-URL reimport issues; heroes already HTTP 200.
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
        print(f"import {spec['name']}:", result)
        rid = spec.get("id")
        if rid:
            patch_fields(client, int(rid), row)
            if args.copy_media and row.get("images"):
                # Skip if already owned CDN path for this robot id
                img0 = (row.get("images") or [""])[0]
                if f"robot-{rid}-" in img0 or f"robot_{rid}_" in img0:
                    print(f"copy-media {rid}: skip (already owned CDN)")
                else:
                    print(f"copy-media {rid}:", copy_media(int(rid)))
            plan["robots"] = [
                {**x, "import": result} if x.get("id") == rid else x
                for x in plan["robots"]
            ]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
