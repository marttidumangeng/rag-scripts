"""Curated Glacier Robotics (261) enrich.

CONTEXT (2026-07-20):
  glacier.ai domain is for sale; live OEM is endwaste.io (Glacier brand).
  Two pending MRF sorting products with thin taxonomy + Released availability.

ENRICH:
  Glacier Robot (4957) — general MRF sorting cell (endwaste.io/robot/)
  Glacier Fiber QC Robot (4958) — fiber-line QC specialization (go.endwaste.io)

Media:
  Replace 4957 suction-cup hero with full GLACIER cell photo.
  Replace 4958 UI-overlay screenshot with clean fiber-line facility photo.

Usage:
  python discover_glacier_robots.py
  python discover_glacier_robots.py --apply --copy-media
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

COMPANY_ID = 261
COMPANY_SLUG = "glacier-robotics"
COMPANY_NAME = "Glacier Robotics"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "glacier-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

ROBOT_URL = "https://endwaste.io/robot/"
FIBER_URL = "https://go.endwaste.io/fiber-qc-robot-mrf"

# Full MRF cell uploaded to prod CDN (endwaste.io copy-media 500 / allowlist)
ROBOT_HERO = (
    "https://cdn.robotaigeek.com/research-staging/glacier/glacier-robot-mrf-cell.png"
)
# Clean fiber-line facility photo (no UI overlay)
FIBER_HERO = (
    "https://go.endwaste.io/hs-fs/hubfs/Glacier%202.jpg"
    "?width=1600&name=Glacier%202.jpg"
)

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4957,
        "name": "Glacier Robot",
        "action": "enrich",
        "status": "pending_review",
        "url": ROBOT_URL,
        "model_name": "Glacier Robot",
        "availability_status": AVAILABLE,
        "category_slugs": "warehouse-robots|arm",
        "movement_type_keys": "stationary",
        "use_keys": "sorting|pick-and-place|material-handling",
        "industry_keys": "logistics|manufacturing",
        "tags": (
            "Recycling|MRF|Sorting|AI|Stationary|Arm|Pick-and-place|Waste"
        ),
        "images": [ROBOT_HERO],
        "videos": [],
        "video_queries": [
            "Glacier Robotics recycling robot",
            "Glacier Robot MRF sorting endwaste",
        ],
        "video_needles": ["glacier", "recycling", "mrf", "endwaste"],
        "video_reject": ["boston dynamics", "amp robotics", "zenrobotics"],
        "description": (
            "Glacier Robot is an AI-powered stationary sorting cell for material "
            "recovery facilities (MRFs). Compact footprint, industrial pick rates, "
            "and models trained on real recycling streams — plastics, fiber, metals, "
            "glass, and specialty packaging."
        ),
        "features": (
            "AI recycling sorter for live MRF lines (OEM endwaste.io/robot/). "
            "OEM claims: 60 successful picks/min in production; ~95% uptime across "
            "customer sites; compact install without major retrofits; clog resistance "
            "for fiber lines; remote diagnostics + 24/7 support. AI trained on real "
            "recycling data identifying 70+ material categories (~90% of typical "
            "curbside stream) including PET/HDPE/film, OCC/newsprint/mixed paper, "
            "aluminum/tin, glass, cartons, and specialty SKUs. Field ROI examples "
            "cite under-1-year payback via recovery and purity gains."
        ),
        "purpose": "AI robotic sorting of recyclables on MRF conveyor lines",
        "sources": [
            {"url": ROBOT_URL, "title": "About the Glacier Robot (OEM)"},
            {"url": "https://endwaste.io/", "title": "Glacier / EndWaste home"},
        ],
    },
    {
        "id": 4958,
        "name": "Glacier Fiber QC Robot",
        "action": "enrich",
        "status": "pending_review",
        "url": FIBER_URL,
        "model_name": "Fiber QC Robot",
        "availability_status": AVAILABLE,
        "category_slugs": "warehouse-robots|arm",
        "movement_type_keys": "stationary",
        "use_keys": "sorting|pick-and-place|inspection|material-handling",
        "industry_keys": "logistics|manufacturing",
        "tags": (
            "Recycling|MRF|Fiber|Paper|Sorting|AI|Stationary|QC|Film"
        ),
        "width_mm": 914.0,  # OEM Fiber QC: robot footprint 3 ft
        "images": [FIBER_HERO],
        "videos": [],
        "video_queries": [
            "Glacier Fiber QC Robot",
            "Glacier fiber recycling robot paper line",
        ],
        "video_needles": ["glacier", "fiber", "paper", "recycling", "qc"],
        "video_reject": ["boston dynamics", "amp robotics", "zenrobotics"],
        "description": (
            "Glacier Fiber QC Robot is Glacier's fiber-line quality-control sorter "
            "for wide, high-speed paper belts plagued by plastic film contamination. "
            "Anti-clog film handling, small footprint, and MRF-proven pick rates."
        ),
        "features": (
            "Fiber QC sorting robot for MRF paper lines (OEM Fiber QC landing + "
            "specs). OEM claims: belt speed up to 240 ft/min; belt width up to "
            "80 in; uptime up to 95%+; 60 successful picks/min in real MRFs; "
            "~3 ft robot footprint (fits where a person stands); anti-clog film "
            "handling; works in high-intensity / variable lighting and extreme "
            "conditions; AI trained on recycling data; typical payback under "
            "10 months. Purpose-built to raise paper purity and cut film-driven "
            "downtime on fiber QC."
        ),
        "purpose": "AI robotic fiber/paper QC sorting and film removal on MRF lines",
        "sources": [
            {"url": FIBER_URL, "title": "Glacier Fiber QC Robot (OEM)"},
            {"url": ROBOT_URL, "title": "About the Glacier Robot (OEM)"},
        ],
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
        if "glacier" not in blob:
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
        "[AI Research] Glacier curated enrich 2026-07-20. "
        "OEM is endwaste.io (glacier.ai domain for sale). "
        "Replaced weak/overlay heroes; set Available + sorting taxonomy."
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
        "use_keys": spec.get("use_keys") or "sorting",
        "industry_keys": spec.get("industry_keys") or "recycling",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Glacier 2026-07-20. Features/specs from endwaste.io OEM "
            "pages; heroes visually QA'd and content-hash distinct."
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


def patch_company_website(client: ResearchApiClient) -> None:
    """glacier.ai is for sale; point company website at live OEM."""
    try:
        client._patch(
            f"companies/{COMPANY_ID}/",
            {"website": "https://endwaste.io"},
        )
        print("patched company website → endwaste.io")
    except Exception as e:  # noqa: BLE001
        print("company website patch warn:", e)


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

    patch_company_website(client)

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
        if rid:
            patch_fields(client, int(rid), row)
            if args.copy_media and row.get("images"):
                print(f"copy-media {rid}:", copy_media(int(rid)))
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
