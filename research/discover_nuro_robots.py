"""Curated Nuro (199) discovery + enrich.

CONTEXT (2026-07-20):
  Nuro pivoted Sep 2024 from operating custom delivery bots to licensing
  Nuro Driver™ autonomy software. Live OEM site no longer has R2/R3 PDPs.

REJECT:
  Nuro-Lucid-Uber Robotaxi (3764) — Lucid Gravity chassis + Uber network;
    Nuro contributes Driver software, not a Nuro-manufactured robot SKU;
    fake /nuro-lucid-uber-robotaxi URL; homepage scrape as features

CREATE pending_review (Discontinued):
  Nuro R2 — second-gen custom delivery AV; OEM R2 spec sheet (digitaloceanspaces)

DEFER (no verified model-only hero):
  Nuro R3 — third-gen CES 2022; fleet-lineup crops contaminated with siblings;
    create when an R3-only still is sourced

SKIP:
  Nuro Driver — software stack, not a robot
  Prius/Leaf test mules — modified OEMs, not Nuro SKUs
  Semi truck research platform — not a product SKU

Usage:
  python discover_nuro_robots.py
  python discover_nuro_robots.py --apply --copy-media
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

COMPANY_ID = 199
COMPANY_SLUG = "nuro"
COMPANY_NAME = "Nuro"
US_ID = 20
DISCONTINUED = 4
REPORT = _RESEARCH_DIR / "staging" / "reports" / "nuro-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# Hosted from OEM R2 Spec Sheet Letter.pdf page render (uploaded to our CDN)
R2_HERO = "https://cdn.robotaigeek.com/research-staging/nuro/nuro-r2-studio-from-oem-spec.jpg"
R2_SPEC_PDF = "https://nuro.sfo3.digitaloceanspaces.com/Nuro-R2-Spec-Sheet-Letter.pdf"

REJECT = [
    {
        "id": 3764,
        "name": "Nuro-Lucid-Uber Robotaxi",
        "reason": (
            "not_nuro_sku: Lucid Gravity vehicle + Uber network; Nuro provides "
            "Nuro Driver software only. Fake /nuro-lucid-uber-robotaxi URL; "
            "homepage chrome scraped into features. Not a Nuro-manufactured robot."
        ),
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "Nuro R2",
        "action": "create",
        "status": "pending_review",
        "url": R2_SPEC_PDF,
        "model_name": "R2",
        "availability_status": DISCONTINUED,
        "release_year": 2020,
        "category_slugs": "delivery-robots|autonomous-mobile-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "item-delivery|logistics|intralogistics",
        "industry_keys": "logistics|retail",
        "tags": (
            "Autonomous|Delivery|Wheeled|Electric|Last Mile|AV|Discontinued"
        ),
        "weight_kg": 1150.0,  # OEM spec sheet gross weight
        "payload_kg": 190.0,
        "height_mm": 1880.0,  # 1.88 m / 6'2" on sheet (LEIP also 1.86 m)
        "width_mm": 1100.0,
        "length_mm": 2740.0,
        "speed": "Max 25 mph (OEM R2 spec sheet)",
        "images": [R2_HERO],
        "videos": [],
        "video_queries": ["Nuro R2 autonomous delivery", "Nuro R2 robot"],
        "video_needles": ["nuro r2", "nuro delivery"],
        "video_reject": ["lucid", "uber robotaxi", "waymo", "cruise"],
        "description": (
            "Nuro R2 is Nuro's second-generation custom electric autonomous delivery "
            "vehicle (zero-occupant). Narrower than a sedan, it was designed for curbside "
            "goods delivery with 360° sensing and pedestrian-protecting front structure. "
            "Nuro later pivoted (2024) to licensing Nuro Driver software; the custom R2 "
            "vehicle line is discontinued."
        ),
        "features": (
            "Second-generation custom zero-occupant autonomous delivery vehicle "
            "(OEM R2 Spec Sheet Letter.pdf on nuro.sfo3.digitaloceanspaces.com). "
            "OEM specs: max speed 25 mph; battery 31 kWh; charge L2 6.6 kWh/hr; "
            "gross weight 1,150 kg / 2,535 lb; payload 190 kg / 419 lb; cargo volume "
            "0.634 m³ / 22.38 ft³; dimensions 2.74 m L × 1.1 m W × 1.88 m H. "
            "Narrow footprint for bike/pedestrian clearance; energy-absorbing front "
            "panel; 360° overlapping cameras + thermal + lidar + radar + ultrasonics; "
            "curbside dual cargo doors; touchscreen for customer/law-enforcement; "
            "redundant braking/control; automotive lighting; pedestrian sound generator. "
            "Vehicle program discontinued after Nuro's 2024 shift to Nuro Driver licensing."
        ),
        "purpose": "Autonomous last-mile goods delivery (historical Nuro custom vehicle)",
        "sources": [
            {"url": R2_SPEC_PDF, "title": "Nuro R2 Spec Sheet (OEM)"},
            {
                "url": "https://www.nuro.ai/blog/nuro-expands-autonomous-technology-leadership-with-a-new-business-model",
                "title": "Nuro business-model expansion / Driver licensing",
            },
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
                "availability_status": DISCONTINUED,
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
        "[AI Research] Nuro curated discover 2026-07-20. "
        "Rejected Lucid×Uber mashup; created discontinued R2/R3; skipped Driver software."
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
        "movement_type_keys": spec.get("movement_type_keys") or "wheeled",
        "category_slugs": spec.get("category_slugs") or "delivery-robots",
        "use_keys": spec.get("use_keys") or "item-delivery",
        "industry_keys": spec.get("industry_keys") or "logistics",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or DISCONTINUED,
        "research_notes": (
            "[AI Research] Nuro 2026-07-20. R2 from OEM spec PDF; R3 from CES-era claims + "
            "2024 Driver pivot; custom vehicles discontinued."
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
        "availability_status": row.get("availability_status") or DISCONTINUED,
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
