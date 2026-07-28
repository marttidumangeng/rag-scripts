#!/usr/bin/env python3
"""Discover + enrich Realman (882) missing *named* variants that OEM evidence supports.

Original gap list had 6 names. OEM PDP evidence supports creating **3**:

  CREATE:
    - ECO63 Standard
    - ECO63 Six-Axis Force
    - RX71 Standard

  DO NOT CREATE (not separate SKUs / no distinct media):
    - ECO62 Six-Axis Force — Force column is "—" on eco62.html; only 标准版 assets
    - RX71 Six-Axis Force — force is built-in (spec labels), not a second SKU
    - RX75 Six-Axis Force — page: Standard + Vision only; "Integrated Six-Axis Force" is a feature

Usage:
  python discover_realman_missing_variants.py
  python discover_realman_missing_variants.py --apply --copy-media
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
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

COMPANY_ID = 882
COMPANY_SLUG = "realman-beijing-intelligent-technology-co-ltd"
COMPANY_NAME = "Realman (Beijing) Intelligent Technology Co., Ltd."
_PROP = "https://www.realman-robotics.com/prop/products-images"
REPORT = _RESEARCH_DIR / "staging" / "reports" / "realman-missing-variants-create.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

YT_ECO63_POLISH = "https://www.youtube.com/watch?v=YFEaiHXNi5Y"
YT_ECO_RM_SERIES = "https://www.youtube.com/watch?v=2ecQGCLOY3Q"
YT_RX_LIGHT = "https://www.youtube.com/watch?v=CM9b4EGjb_E"
YT_CES_ARMS = "https://www.youtube.com/watch?v=LF96dkzeNrY"

TAGS_ECO = "6-Axis|Collaborative Robot|Lightweight|Industrial Arm|Pick-and-Place|Education"
TAGS_FORCE = "Force Sensing|6-Axis|Collaborative Robot|Industrial Arm|Precision|Manufacturing|Lightweight"
TAGS_RX7 = "7-DoF|Collaborative Robot|Humanoid|Lightweight|Industrial Arm|Manipulation"

# Curated from live OEM PDPs (2026-07-19).
# RX71 Standard is handled as rename of published 5230 (single OEM render — no duplicate create).
NEW_VARIANTS: list[dict[str, Any]] = [
    {
        "name": "ECO63 Standard",
        "model_name": "ECO63 Standard",
        "url": "https://www.realman-robotics.com/en/products/eco63.html",
        "image": f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-标准版/前视图-标准版.png",
        "images": [
            f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-标准版/前视图-标准版.png",
            f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-标准版/角度1-标准版.png",
            f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-标准版/角度3-标准版.png",
            f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-标准版/角度4-标准版.png",
        ],
        "description": (
            "RealMan ECO63 Standard is a long-reach 6-DoF collaborative arm "
            "with 900 mm working radius for wide-area pick-and-place and service tasks."
        ),
        "features": (
            "Variant: Standard (no integrated F/T tip). "
            "6 DoF; 3 kg payload; 900 mm working radius; 9.5 kg net weight; "
            "±0.05 mm repeatability; TCP ≤2.8 m/s; typical power ≤150 W. "
            "Full mechanical brakes; longest reach in the ECO series."
        ),
        "dof": 6,
        "payload_kg": 3.0,
        "reach_mm": 900.0,
        "weight_kg": 9.5,
        "weight": "9.5 kg",
        "repeatability_mm": 0.05,
        "tags": TAGS_ECO,
        "videos": [YT_ECO63_POLISH, YT_ECO_RM_SERIES],
        "use_keys": "assembly|pick-and-place",
        "industry_keys": "manufacturing|retail",
        "source_note": (
            "eco63.html Technical Specifications column ECO63 Standard "
            "(900 mm · 3 kg · 9.5 kg). Heroes: OEM ECO63-标准版 folder."
        ),
    },
    {
        "name": "ECO63 Six-Axis Force",
        "model_name": "ECO63 Six-Axis Force",
        "url": "https://www.realman-robotics.com/en/products/eco63.html",
        "image": f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-六维力版/前视图-6维力版.png",
        "images": [
            f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-六维力版/前视图-6维力版.png",
            f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-六维力版/角度1-6维力版.png",
            f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-六维力版/角度3-6维力版.png",
            f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-六维力版/角度4-6维力版.png",
        ],
        "description": (
            "RealMan ECO63 Six-Axis Force adds an integrated six-axis force/torque tip "
            "to the long-reach ECO63 collaborative platform (917 mm working radius)."
        ),
        "features": (
            "Variant: Six-Axis Force (integrated F/T tip, 200 N / 7 N·m class, ±0.5%FS per OEM). "
            "6 DoF; 3 kg payload; 917 mm working radius; 9.6 kg net weight; "
            "±0.05 mm repeatability; TCP ≤2.8 m/s; typical power ≤150 W. "
            "For precision contact tasks at extended ECO-series reach."
        ),
        "dof": 6,
        "payload_kg": 3.0,
        "reach_mm": 917.0,
        "weight_kg": 9.6,
        "weight": "9.6 kg",
        "repeatability_mm": 0.05,
        "tags": TAGS_FORCE,
        "videos": [YT_ECO63_POLISH, YT_ECO_RM_SERIES],
        "use_keys": "assembly|pick-and-place",
        "industry_keys": "manufacturing|retail",
        "source_note": (
            "eco63.html Technical Specifications column ECO63 Six-Axis Force "
            "(917 mm · 3 kg · 9.6 kg). Heroes: OEM ECO63-六维力版 folder."
        ),
    },
]

RENAME_PUBLISHED = [
    {
        "id": 5230,
        "from_name": "RX71",
        "to_name": "RX71 Standard",
        "why": (
            "Only OEM asset is RX71-标准版; creating a second row would duplicate "
            "primary hash 75f5b93ab9b5. Force is built-in — not a separate SKU."
        ),
        "features": (
            "Single OEM configuration (force sensing is built-in, not a separate Force SKU). "
            "7 DoF humanoid wrist; 1 kg payload; 474 mm working radius (incl. force sensor); "
            "~3.8 kg net weight (excl. controller). "
            "Designed for dual-arm collaborative / humanoid-style mounting."
        ),
    },
]

SKIPPED = [
    {
        "name": "ECO62 Six-Axis Force",
        "why": 'eco62.html Force column is "—"; only ECO62-标准版 assets exist (no 六维力版 folder).',
    },
    {
        "name": "RX71 Six-Axis Force",
        "why": "Not a SKU — force is built into the single RX71 (spec labels Force Range / radius incl. sensor).",
    },
    {
        "name": "RX75 Six-Axis Force",
        "why": "Not a SKU — page sells Standard + Vision only; Integrated Six-Axis Force is a feature heading.",
    },
]


def encode_url(url: str) -> str:
    p = urlsplit(url)
    segs = [quote(unquote(seg), safe="") for seg in p.path.split("/")]
    return urlunsplit((p.scheme, p.netloc, "/".join(segs), p.query, p.fragment))


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(encode_url(url), headers=UA, timeout=60)
        if not r.ok:
            return False, "", 0
        body = r.content
        if not body.startswith((b"\x89PNG", b"\xff\xd8", b"GIF8", b"RIFF")):
            return False, "", len(body)
        return True, hashlib.md5(body).hexdigest(), len(body)
    except requests.RequestException:
        return False, "", 0


def build_row(data: dict[str, Any]) -> dict[str, Any]:
    hero = data["image"]
    ok, md5, nbytes = download_ok(hero)
    if not ok:
        raise RuntimeError(f"hero fail {data['name']}: {hero}")
    gallery = []
    seen = {md5}
    for u in data.get("images") or [hero]:
        ok2, h2, _ = download_ok(u)
        if not ok2:
            continue
        if h2 in seen:
            continue
        seen.add(h2)
        gallery.append(u)
    images = [hero] + gallery
    videos = enrich_video_list(list(data.get("videos") or []))
    row: dict[str, Any] = {
        "name": data["name"],
        "model_name": data.get("model_name") or data["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CN",
        "manufacturer_country_codes": "CN",
        "description": data["description"],
        "purpose": data["description"],
        "features": data["features"],
        "url": data["url"],
        "image": hero,
        "images": images,
        "video_urls": videos,
        "movement_type_keys": "stationary",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "use_keys": data.get("use_keys") or "assembly|pick-and-place",
        "industry_keys": data.get("industry_keys") or "manufacturing",
        "tags": data.get("tags") or "",
        "research_notes": data.get("source_note") or "",
        "source_locale": "en",
        "sources": [
            {
                "url": data["url"],
                "type": "website",
                "title": f"RealMan {data['name']} product page",
            },
            {
                "url": "https://www.realman-robotics.com/",
                "type": "website",
                "title": "RealMan Robotics",
            },
        ],
        "_hero_md5": md5,
        "_hero_bytes": nbytes,
    }
    for key in ("dof", "payload_kg", "reach_mm", "weight_kg", "weight", "repeatability_mm"):
        if data.get(key) is not None and data.get(key) != "":
            row[key] = data[key]
    return row


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
        time.sleep(2 ** attempt)
    return last


def find_created(client: ResearchApiClient, name: str) -> dict[str, Any] | None:
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": COMPANY_ID,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
                "search": name,
            },
        )
        for r in data.get("results") or []:
            if (r.get("name") or "") == name:
                return r
        if not data.get("next"):
            break
        page += 1
    # fallback: list all pending
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": COMPANY_ID,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        for r in data.get("results") or []:
            if (r.get("name") or "") == name:
                return r
        if not data.get("next") or not (data.get("results") or []):
            break
        page += 1
    return None


def patch_typed_specs(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body = {
        k: row[k]
        for k in ("dof", "payload_kg", "reach_mm", "weight_kg", "repeatability_mm")
        if row.get(k) is not None
    }
    body["manufacturer_countries"] = [3]
    body["manufacturer_country_ref"] = 3
    if not body:
        return
    try:
        client._patch(f"robots/robots/{rid}/", body)
        print(f"  patched typed specs {rid}")
    except Exception as e:  # noqa: BLE001
        print(f"  typed specs patch warn {rid}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    # Skip if already pending/published with same name
    existing_names: set[str] = set()
    for status in ("pending_review", "published", "approved"):
        page = 1
        while True:
            data = client._get(
                "robots/robots/",
                params={
                    "company_ref": COMPANY_ID,
                    "status": status,
                    "page": page,
                    "page_size": 50,
                },
            )
            for r in data.get("results") or []:
                existing_names.add(r.get("name") or "")
            if not data.get("next") or not (data.get("results") or []):
                break
            page += 1

    plan: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    hero_hashes: dict[str, str] = {}
    for data in NEW_VARIANTS:
        name = data["name"]
        if name in existing_names:
            print(f"SKIP exists: {name}")
            plan.append({"name": name, "action": "skip_exists"})
            continue
        row = build_row(data)
        md5 = row.pop("_hero_md5")
        row.pop("_hero_bytes", None)
        if md5 in hero_hashes.values():
            raise RuntimeError(f"hero hash collision for {name}")
        hero_hashes[name] = md5
        rows.append(row)
        plan.append(
            {
                "name": name,
                "action": "create",
                "image": row["image"],
                "images_n": len(row["images"]),
                "hero_md5": md5,
                "payload_kg": row.get("payload_kg"),
                "reach_mm": row.get("reach_mm"),
                "weight_kg": row.get("weight_kg"),
                "videos": len(row.get("video_urls") or []),
            }
        )
        print(
            f"READY {name}: imgs={len(row['images'])} "
            f"payload={row.get('payload_kg')} reach={row.get('reach_mm')} "
            f"md5={md5[:12]}"
        )

    report = {
        "company_id": COMPANY_ID,
        "create": plan,
        "renames": [],
        "skipped_not_skus": SKIPPED,
        "created_ids": [],
    }

    # Renames (published): name-only to avoid hash-duplicate create
    for ren in RENAME_PUBLISHED:
        rid = int(ren["id"])
        try:
            cur = client._get(f"robots/robots/{rid}/")
        except Exception as e:  # noqa: BLE001
            print(f"RENAME skip {rid}: {e}")
            continue
        cur_name = cur.get("name") or ""
        entry = {
            "id": rid,
            "from": ren["from_name"],
            "to": ren["to_name"],
            "current": cur_name,
            "why": ren["why"],
            "action": "rename",
        }
        if cur_name == ren["to_name"]:
            entry["action"] = "already_named"
            print(f"RENAME already {rid} {cur_name}")
        elif cur_name != ren["from_name"] and cur_name != ren["to_name"]:
            entry["action"] = "unexpected_name"
            print(f"RENAME unexpected {rid} is {cur_name!r}")
        else:
            print(f"RENAME plan {rid}: {cur_name!r} -> {ren['to_name']!r}")
        report["renames"].append(entry)

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not rows and not any(r.get("action") == "rename" for r in report["renames"]):
        print("nothing to create/rename")
        print("wrote", REPORT)
        return 0
    if not args.apply:
        print(
            f"dry-run: {len(rows)} create, "
            f"{sum(1 for r in report['renames'] if r.get('action')=='rename')} rename. "
            "Pass --apply --copy-media"
        )
        print("wrote", REPORT)
        return 0

    # Apply renames first
    for ren in RENAME_PUBLISHED:
        rid = int(ren["id"])
        matching = next((x for x in report["renames"] if x["id"] == rid), None)
        if not matching or matching.get("action") != "rename":
            continue
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "name": ren["to_name"],
                    "model_name": ren["to_name"],
                    "features": ren["features"],
                },
            )
            print(f"renamed {rid} -> {ren['to_name']}")
            matching["action"] = "renamed"
        except Exception as e:  # noqa: BLE001
            print(f"RENAME FAIL {rid}: {e}")
            matching["action"] = "rename_failed"

    created_ids: list[int] = []
    for row in rows:
        bulk = staging_dict_to_bulk_import_row(row)
        # Ensure create path (no id)
        bulk.pop("id", None)
        try:
            result = client.bulk_import_robots(
                [bulk],
                update_existing=False,
                patch_existing=False,
                replace_media=True,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as e:  # noqa: BLE001
            print(f"CREATE FAIL {row['name']}: {e}")
            continue
        print(f"import {row['name']}: {result}")
        time.sleep(0.5)
        found = find_created(client, row["name"])
        if not found:
            print(f"WARN could not locate created {row['name']}")
            continue
        rid = int(found["id"])
        created_ids.append(rid)
        print(f"created id={rid} {row['name']}")
        patch_typed_specs(client, rid, row)
        if args.copy_media:
            cm = copy_media(rid)
            print(f"  copy-media {rid}: {cm}")
            time.sleep(0.4)

    report["created_ids"] = created_ids
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("DONE created", created_ids, "wrote", REPORT)
    return 0 if len(created_ids) == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
