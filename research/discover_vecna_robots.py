"""Curated Vecna Robotics (208) discovery + enrich.

CONTEXT (2026-07-20):
  Vecna AMR fleet: AFL forklift, ATG tugger, CPJ co-bot pallet jack.
  CaseFlow is orchestration software choosing among those platforms — not a robot.

REJECT:
  CaseFlow™ (4518) — Pivotal/CaseFlow solution orchestrating CPJ/ATG/AFL;
    no distinct hardware SKU

ENRICH pending_review:
  Vecna AFL (4519), ATG (4520), CPJ (4521)

Usage:
  python discover_vecna_robots.py
  python discover_vecna_robots.py --apply --copy-media
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

COMPANY_ID = 208
COMPANY_SLUG = "vecna-robotics"
COMPANY_NAME = "Vecna Robotics"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "vecna-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

AFL_URL = "https://www.vecnarobotics.com/afl-autonomous-forklift/"
ATG_URL = "https://www.vecnarobotics.com/atg-autonomous-tugger/"
CPJ_URL = "https://www.vecnarobotics.com/cobot-pallet-jack/"

AFL_HERO = (
    "https://www.vecnarobotics.com/wp-content/uploads/2024/08/VecnaFleet-AFL-New-@2x.png"
)
ATG_HERO = (
    "https://www.vecnarobotics.com/wp-content/uploads/2024/08/VecnaFleet-Tugger-New-@2x.png"
)
CPJ_HERO = (
    "https://www.vecnarobotics.com/wp-content/uploads/2024/10/PalletJack-2024-2.png"
)

REJECT = [
    {
        "id": 4518,
        "name": "CaseFlow™",
        "reason": (
            "not_distinct_robot_sku: CaseFlow is Vecna's Pivotal-orchestrated "
            "case-picking solution that deploys CPJ/ATG/AFL platforms — software "
            "workflow + platform choice, not a unique hardware robot model."
        ),
    },
    {
        "id": 271,
        "name": "Vecna Agile Robots",
        "reason": (
            "duplicate_umbrella_of_4520: legacy Chinese family shell "
            "('Vecna Tug, AG-X Series', homepage URL, CJK junk features). "
            "Primary photo identical content-hash to ATG fleet render; "
            "gallery mixes ATG+CPJ+RaaS. Keep ATG (4520) as canonical tugger."
        ),
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4519,
        "name": "Vecna AFL",
        "action": "enrich",
        "status": "pending_review",
        "url": AFL_URL,
        "model_name": "AFL",
        "availability_status": AVAILABLE,
        "category_slugs": "warehouse-robots|autonomous-mobile-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "material-handling|logistics|intralogistics|handling",
        "industry_keys": "logistics|retail|manufacturing",
        "tags": (
            "AMR|Forklift|Warehouse|Autonomous|Wheeled|Logistics|Pallet|"
            "Material Handling"
        ),
        "payload_kg": 1361.0,  # Tear-Sheet-AFL.pdf 3000 lb / 1361 kg
        "weight_kg": 2132.0,  # less battery
        "length_mm": 3129.0,
        "width_mm": 1102.0,
        "height_mm": 2438.0,
        "speed": 10.8,  # FloatField km/h — OEM 6.7 mph / 3.0 m/s
        "runtime_minutes": 480,
        "charging_time_minutes": 90,
        "images": [AFL_HERO],
        "videos": [],
        "video_queries": [
            "Vecna AFL autonomous forklift",
            "Vecna Robotics autonomous forklift",
        ],
        "video_needles": ["vecna", "afl", "forklift", "autonomous"],
        "video_reject": ["caseflow", "tugger", "pallet jack", "locus", "6 river"],
        "description": (
            "Vecna AFL is an autonomous forklift AMR for warehouse pick, putaway, "
            "conveyor/riser handoffs, packaging, cross-dock, and WIP transport. "
            "Route-free navigation with Pivotal orchestration; ANSI B56.5 compliant."
        ),
        "features": (
            "Autonomous forklift AMR (OEM AFL PDP + Tear-Sheet-AFL.pdf). "
            "Typed: payload 1361 kg (3000 lb); vehicle mass 2132 kg less battery; "
            "L×W×H 3129×1102×2438 mm; speed 10.8 km/h (6.7 mph / 3.0 m/s); lift to "
            "1524 mm / 60 in; right-angle stack 4.7 m; 9 ft / 2.7 m aisles at max "
            "speed; runtime up to 8+ hr; charge 1–2 hr. Ground-to-ground, conveyor, "
            "riser, stretch-wrapper, and dock workflows. LPN/barcode to WMS; "
            "opportunistic charging; ANSI/ITSDF B56.5 + RIA 15.08."
        ),
        "purpose": "Autonomous pallet forklift transport in warehouse and manufacturing",
        "sources": [{"url": AFL_URL, "title": "Vecna AFL Autonomous Forklift (OEM)"}],
    },
    {
        "id": 4520,
        "name": "Vecna ATG",
        "action": "enrich",
        "status": "pending_review",
        "url": ATG_URL,
        "model_name": "ATG",
        "availability_status": AVAILABLE,
        "category_slugs": "warehouse-robots|autonomous-mobile-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "material-handling|logistics|intralogistics|handling",
        "industry_keys": "logistics|manufacturing|healthcare",
        "tags": (
            "AMR|Tugger|Warehouse|Autonomous|Wheeled|Logistics|Manufacturing|"
            "Material Handling"
        ),
        "payload_kg": 4500.0,  # Tear-Sheet-ATG.pdf 9920 lb / 4500 kg
        "weight_kg": 736.0,  # less battery
        "length_mm": 1653.0,
        "width_mm": 1103.0,
        "height_mm": 2061.0,
        "speed": 7.2,  # FloatField km/h — tear sheet 5 mph / 2 m/s (PDP said 6.0)
        "runtime_minutes": 480,
        "charging_time_minutes": 90,
        "images": [ATG_HERO],
        "videos": [],
        "video_queries": [
            "Vecna ATG autonomous tugger",
            "Vecna Robotics autonomous tugger",
        ],
        "video_needles": ["vecna", "atg", "tugger", "autonomous"],
        "video_reject": ["caseflow", "forklift", "pallet jack", "locus"],
        "description": (
            "Vecna ATG is a driverless autonomous tugger for high-capacity cart "
            "trains in manufacturing, sortation, and lean milk-run replenishment. "
            "Fork-free material transport with flexible train configurations."
        ),
        "features": (
            "Autonomous tugger AMR (OEM ATG PDP + Tear-Sheet-ATG.pdf). Typed: tow "
            "capacity 4500 kg (9920 lb); mass 736 kg less battery; L×W×H "
            "1653×1103×2061 mm; speed 7.2 km/h (5 mph / 2 m/s tear sheet); turning "
            "radius 2.9 m with 3 quadsteer carts; 1.8 m / 6 ft aisle; runtime up to "
            "8+ hr; charge 1–2 hr. Kanban/milk-run, WIP, and cross-dock sortation. "
            "On-board or remote task assignment; ANSI/ITSDF B56.5 + RIA 15.08."
        ),
        "purpose": "Autonomous tugger/cart-train transport for manufacturing and logistics",
        "sources": [{"url": ATG_URL, "title": "Vecna ATG Autonomous Tugger (OEM)"}],
    },
    {
        "id": 4521,
        "name": "Vecna CPJ",
        "action": "enrich",
        "status": "pending_review",
        "url": CPJ_URL,
        "model_name": "CPJ",
        "availability_status": AVAILABLE,
        "category_slugs": "warehouse-robots|autonomous-mobile-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "picking|material-handling|logistics|intralogistics|handling",
        "industry_keys": "logistics|retail",
        "tags": (
            "AMR|Pallet Jack|Warehouse|Autonomous|Wheeled|Case Picking|Logistics|"
            "Cobot"
        ),
        "payload_kg": 1500.0,  # Tear-Sheet-CPJ.pdf 3300 lb / 1500 kg
        "length_mm": 1740.0,
        "width_mm": 927.0,
        "height_mm": 2273.0,
        "speed": 4.32,  # FloatField km/h — OEM 2.8 mph / 1.2 m/s
        "runtime_minutes": 240,
        "charging_time_minutes": 120,
        "images": [CPJ_HERO],
        "videos": [],
        "video_queries": [
            "Vecna CPJ cobot pallet jack",
            "Vecna CaseFlow pallet jack",
        ],
        "video_needles": ["vecna", "cpj", "pallet jack", "caseflow", "case flow"],
        "video_reject": ["forklift", "tugger", "locus", "6 river"],
        "description": (
            "Vecna CPJ is a co-bot pallet jack AMR for tight-aisle microworkflows: "
            "case picking support, replenishment, dunnage/empty pallet moves, and "
            "short point-to-point transport under 200 m. Powers Vecna CaseFlow "
            "case-picking deployments."
        ),
        "features": (
            "Co-bot pallet jack AMR (OEM CPJ PDP + Tear-Sheet-CPJ.pdf). Typed: "
            "payload 1500 kg (3300 lb); L×W×H 1740×927×2273 mm; speed 4.32 km/h "
            "(2.8 mph / 1.2 m/s); runtime ~4 hr typical; hot-swap Li-ion charge "
            "~2 hr (24 V, 60 Ah). Manual spear + autonomous nav; on-board tablet; "
            "6 ft aisle microworkflows under 200 m. ANSI/ITSDF B56.5 + RIA 15.08; "
            "Pivotal Command Center support. CaseFlow case-picking platform option."
        ),
        "purpose": (
            "Short-distance autonomous pallet/cart transport and case-picking support"
        ),
        "sources": [{"url": CPJ_URL, "title": "Vecna CPJ Co-bot Pallet Jack (OEM)"}],
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
        "[AI Research] Vecna curated discover 2026-07-20. "
        "Rejected CaseFlow solution SKU; enriched AFL/ATG/CPJ with OEM fleet renders."
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
        "category_slugs": spec.get("category_slugs") or "warehouse-robots",
        "use_keys": spec.get("use_keys") or "logistics",
        "industry_keys": spec.get("industry_keys") or "logistics",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Vecna 2026-07-20. Specs from live OEM PDPs; "
            "VecnaFleet product renders; CaseFlow rejected as orchestration solution."
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
        if not rid and isinstance(result, dict):
            for item in result.get("results") or []:
                if item.get("action") in ("created", "updated") and item.get("id"):
                    rid = item["id"]
                    spec["id"] = rid
        if rid:
            patch_fields(client, int(rid), row)
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
