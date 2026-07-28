"""Curated Berkshire Grey (256) discovery + enrich.

CONTEXT (2026-07-20):
  SoftBank-backed US warehouse automation OEM. Live PDPs for Core / Scoop /
  Stride / Dispatch. Queue had thin features, wrong/CAD heroes, and a
  Dispatch duplicate.

REJECT:
  Dispatch Parcel Sorter (4044) — duplicate of Dispatch™ Small Parcel Sorter
    (2694); CDN hero was logo/black bar junk (hash matched BerkshireGrey-Black)

ENRICH pending_review:
  Core Robotic Picking System (4043) — OEM Core PDP + product sheet; CORE.webp
  Scoop Trailer Unloader (4045) — OEM Scoop PDP + trailer action still
  Stride Shuttle Sorter (4046) — OEM Stride PDP + sheet crop (PDP embeds sibling
    Core chrome — fail-closed on those; use sheet photo)
  Dispatch™ Small Parcel Sorter (2694) — OEM Dispatch PDP hero

Usage:
  python discover_berkshiregrey_robots.py
  python discover_berkshiregrey_robots.py --apply --copy-media
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

COMPANY_ID = 256
COMPANY_SLUG = "berkshire-grey"
COMPANY_NAME = "Berkshire Grey"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "berkshiregrey-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

CORE_URL = "https://www.berkshiregrey.com/solutions/core-robotic-picking-system/"
SCOOP_URL = "https://www.berkshiregrey.com/solutions/scoop-trailer-unloader/"
STRIDE_URL = "https://www.berkshiregrey.com/solutions/stride-shuttle-sorter/"
DISPATCH_URL = "https://www.berkshiregrey.com/solutions/dispatch-parcel-sorter/"
CORE_SHEET = "https://www.berkshiregrey.com/wp-content/uploads/2026/04/BG-Core-product-sheet.pdf"
SCOOP_SHEET = "https://www.berkshiregrey.com/wp-content/uploads/2026/04/BG-Scoop-product-sheet.pdf"
STRIDE_SHEET = "https://www.berkshiregrey.com/wp-content/uploads/2026/04/BG-Stride-product-sheet.pdf"

CORE_HERO = "https://www.berkshiregrey.com/wp-content/uploads/2026/04/CORE.webp"
SCOOP_HERO = (
    "https://www.berkshiregrey.com/wp-content/uploads/2026/03/"
    "Screenshot-2026-03-30-at-10.26.04-AM.png"
)
DISPATCH_HERO = (
    "https://www.berkshiregrey.com/wp-content/uploads/2026/04/Hero-Package-Sortation.webp"
)
# Cropped from OEM BG-Stride-product-sheet.pdf (PDP only embeds Core cross-sell chrome)
STRIDE_HERO = (
    "https://cdn.robotaigeek.com/research-staging/berkshiregrey/"
    "stride-shuttle-from-oem-sheet.jpg"
)
STRIDE_GALLERY = (
    "https://www.berkshiregrey.com/wp-content/uploads/2024/12/BG-RSPS_OS_wide_2.webp"
)

REJECT = [
    {
        "id": 4044,
        "name": "Dispatch Parcel Sorter",
        "reason": (
            "duplicate_of_2694: same OEM Dispatch™ Small Parcel Sorter PDP; "
            "4044 had empty features and logo/black-bar CDN hero "
            "(BerkshireGrey-Black hash). Keep 2694 as the canonical Dispatch record."
        ),
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4043,
        "name": "Core™ Robotic Picking System",
        "action": "enrich",
        "status": "pending_review",
        "url": CORE_URL,
        "model_name": "Core",
        "availability_status": AVAILABLE,
        "category_slugs": "warehouse-robots|arm",
        "movement_type_keys": "stationary",
        "use_keys": "picking|material-handling|logistics|intralogistics|handling",
        "industry_keys": "logistics|retail",
        "tags": (
            "Warehouse|Picking|Arm|AI|Stationary|Intralogistics|Logistics|"
            "SpectrumGripper|Piece Picking"
        ),
        "payload_kg": 6.0,  # OEM FAQ: heavy items up to 6 kg
        "images": [CORE_HERO],
        "videos": [],
        "video_queries": [
            "Berkshire Grey Core robotic picking",
            "Berkshire Grey Core piece picking",
        ],
        "video_needles": ["berkshire grey", "core", "piece pick", "picking"],
        "video_reject": ["scoop", "stride", "dispatch", "trailer unload"],
        "description": (
            "Core™ is Berkshire Grey's AI-powered robotic piece-picking platform "
            "for complex fulfillment. Perception, motion planning, and "
            "SpectrumGripper® adaptive gripping work as one pick cell that "
            "configures for tote AMR, goods-to-person, sorter induction, put wall, "
            "autobagger, and custom workflows."
        ),
        "features": (
            "AI + 3D vision pick cell for high-SKU-variability warehouse fulfillment "
            "(OEM Core Robotic Picking System PDP). Claims >99% pick accuracy and "
            ">99% uptime; up to ~2× human pick-and-release throughput. Patented "
            "SpectrumGripper® adapts to porous, irregular, heavy, transparent, "
            "chilled/frozen, and glass-packaged goods; quick-change suction cups; "
            "secure grip detection without a perfect vacuum seal. Handles previously "
            "unseen SKUs without prior SKU data; FAQ cites item payload up to 6 kg. "
            "Integrates with AutoStore/ASRS, shuttles, conveyors, AMRs, put walls, "
            "and autobaggers without full facility redesign. Configurable for tote "
            "picking, AMR induction, goods-to-person, sorter induction, put wall/"
            "Gaylord, pack-to-box/bag, and custom setups."
        ),
        "purpose": (
            "Autonomous warehouse piece picking and pick-and-place for "
            "eCommerce, retail, grocery, 3PL, and parcel fulfillment"
        ),
        "sources": [
            {"url": CORE_URL, "title": "Core™ Robotic Picking System (OEM)"},
            {"url": CORE_SHEET, "title": "BG Core product sheet (OEM PDF)"},
        ],
    },
    {
        "id": 4045,
        "name": "Scoop™ Trailer Unloader",
        "action": "enrich",
        "status": "pending_review",
        "url": SCOOP_URL,
        "model_name": "Scoop",
        "availability_status": AVAILABLE,
        "category_slugs": "warehouse-robots|arm",
        "movement_type_keys": "stationary",
        "use_keys": "material-handling|logistics|intralogistics|handling",
        "industry_keys": "logistics|retail",
        "tags": (
            "Warehouse|Trailer Unloading|Arm|Dock|Logistics|Parcel|AI|Stationary"
        ),
        "images": [SCOOP_HERO],
        "videos": [],
        "video_queries": [
            "Berkshire Grey Scoop trailer unloader",
            "Berkshire Grey Scoop robotic unloading",
        ],
        "video_needles": ["berkshire grey", "scoop", "trailer", "unload"],
        "video_reject": [
            "core picking",
            "stride",
            "dispatch",
            "boston dynamics",
            "stretch",
            "agility",
            "amazon robotics",
        ],
        "description": (
            "Scoop™ is Berkshire Grey's autonomous trailer/container unloader for "
            "floor-loaded and unstructured inbound freight. Dual-mode bulk induction "
            "plus robotic picking empties mixed parcel walls at the dock without "
            "pre-sort conditioning."
        ),
        "features": (
            "Autonomous trailer and container unloading for unstructured and "
            "structured inbound loads (OEM Scoop Trailer Unloader PDP + product "
            "sheet). Dual-mode selective picking/pulling with conveyor floor "
            "induction for dense walls, loose parcels, padded mailers, heavy and "
            "irregular items. OEM claims throughput at or above manual processing, "
            ">99% uptime, and up to ~1:5 operator-to-system ratio. Integrates with "
            "existing dock doors and conveyors; supports highly autonomous dock "
            "execution plus manual mode for non-conveyable exceptions. Built for "
            "parcel hubs, eCommerce fulfillment, and 3PL mixed operations."
        ),
        "purpose": (
            "Automated inbound trailer/container unloading for parcel hubs, "
            "eCommerce networks, and 3PL docks"
        ),
        "sources": [
            {"url": SCOOP_URL, "title": "Scoop™ Trailer Unloader (OEM)"},
            {"url": SCOOP_SHEET, "title": "BG Scoop product sheet (OEM PDF)"},
        ],
    },
    {
        "id": 4046,
        "name": "Stride™ Shuttle Sorter",
        "action": "enrich",
        "status": "pending_review",
        "url": STRIDE_URL,
        "model_name": "Stride",
        "availability_status": AVAILABLE,
        "category_slugs": "warehouse-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "sorting|logistics|intralogistics|material-handling",
        "industry_keys": "logistics|retail",
        "tags": (
            "Warehouse|Sortation|Shuttle|Logistics|Retail|AI|Wheeled|"
            "Intralogistics"
        ),
        "images": [STRIDE_HERO, STRIDE_GALLERY],
        "videos": [],
        "video_queries": [
            "Berkshire Grey Stride shuttle sorter",
            "Berkshire Grey Stride sortation",
        ],
        "video_needles": ["berkshire grey", "stride", "shuttle", "sort"],
        "video_reject": [
            "scoop",
            "trailer",
            "dispatch parcel",
            "tilt tray",
            "tilt-tray",
            "beumer",
            "honeywell",
        ],
        "description": (
            "Stride™ is Berkshire Grey's high-speed robotic shuttle sortation "
            "system for retail and omnichannel fulfillment. Independent shuttles "
            "move point-to-point in parallel, sorting into totes or boxes at high "
            "density inside a compact footprint."
        ),
        "features": (
            "Robotic shuttle unit-sortation for high-throughput fulfillment "
            "(OEM Stride Shuttle Sorter PDP + product sheet). Parallel shuttle "
            "architecture eliminates single-path conveyor bottlenecks; configurable "
            "beam lengths (8 m / 10 m / 14 m) with middle or end induction; "
            "sort-to-tote or sort-to-box. OEM claims ~6.5× human baseline per labor "
            "hour, ~50% footprint reduction vs traditional sorters, and >99% "
            "accuracy; SKU scale cited from ~4k to 60k+. Manual or Core™ robotic "
            "induction; controlled short release into outbound containers; optional "
            "dynamic staging and automatic takeaway. Suited to store replenishment, "
            "omnichannel, wholesale/B2B, and brownfield space-constrained sites."
        ),
        "purpose": (
            "High-density robotic shuttle sortation for retail store replenishment "
            "and omnichannel/wholesale fulfillment"
        ),
        "sources": [
            {"url": STRIDE_URL, "title": "Stride™ Shuttle Sorter (OEM)"},
            {"url": STRIDE_SHEET, "title": "BG Stride product sheet (OEM PDF)"},
        ],
    },
    {
        "id": 2694,
        "name": "Dispatch™ Small Parcel Sorter",
        "action": "enrich",
        "status": "pending_review",
        "url": DISPATCH_URL,
        "model_name": "Dispatch",
        "availability_status": AVAILABLE,
        "category_slugs": "warehouse-robots|arm",
        "movement_type_keys": "stationary",
        "use_keys": "sorting|logistics|intralogistics|material-handling",
        "industry_keys": "logistics|retail",
        "tags": (
            "Warehouse|Parcel|Sortation|Arm|Hyperscanner|Logistics|AI|Stationary"
        ),
        "images": [DISPATCH_HERO],
        "videos": [],
        "video_queries": [
            "Berkshire Grey Dispatch parcel sorter",
            "Berkshire Grey Hyperscanner sortation",
        ],
        "video_needles": ["berkshire grey", "dispatch", "parcel", "hyperscanner"],
        "video_reject": ["scoop", "stride shuttle", "core picking"],
        "description": (
            "Dispatch™ is Berkshire Grey's compact small-parcel sorter for hubs "
            "and eCommerce fulfillment. Patented Hyperscanner™ identification plus "
            "adaptive manual/automated induction routes polybags, mailers, cartons, "
            "and irregular packages without expanding the building footprint."
        ),
        "features": (
            "Compact small-parcel sortation with dynamic routing (OEM Dispatch "
            "Parcel Sorter PDP). Patented Hyperscanner™ package identification for "
            "sizes/shapes/materials traditional scanners struggle with. Supports "
            "manual and automated induction across polybags, mailers, cartons, and "
            "irregular parcels. Designed to raise sort capacity inside existing "
            "footprints for parcel hub/carrier destination sort and eCommerce "
            "fulfillment demand spikes without new buildings."
        ),
        "purpose": (
            "Compact automated small-parcel sortation for carrier hubs and "
            "eCommerce fulfillment"
        ),
        "sources": [
            {"url": DISPATCH_URL, "title": "Dispatch™ Parcel Sorter (OEM)"},
        ],
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
        "[AI Research] Berkshire Grey curated discover 2026-07-20. "
        "Rejected Dispatch dupe 4044; replaced CAD/logo heroes; OEM PDP + sheets."
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
        "movement_type_keys": spec.get("movement_type_keys") or "stationary",
        "category_slugs": spec.get("category_slugs") or "warehouse-robots",
        "use_keys": spec.get("use_keys") or "logistics",
        "industry_keys": spec.get("industry_keys") or "logistics",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Berkshire Grey 2026-07-20. Features from live OEM PDPs + "
            "product sheets; heroes visually QA'd; Stride hero cropped from OEM sheet "
            "because PDP embeds Core sibling chrome."
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
