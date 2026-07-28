"""Curated Flexiv (315) enrich — Rizon 4/10 (+F/T) + Moonlight; reject Grav EOAT.

CONTEXT (2026-07-20):
  7 pending_review. OEM flexiv.com product pages.
  RIZON 4 (2863) had Franka-like wrong CDN hero (reliable.png lab) — replaced with
  verified Flexiv ProductParameter studio stills (cyan joint rings).
  Grav / Grav Enhanced are 2-finger grippers (EOAT), not robots → reject.

ENRICH:
  2863 RIZON 4 — Available; white studio hero
  3644 Rizon 4 + F/T Sensor — Available; silver studio hero
  3645 RIZON 10 — Available; dark studio hero
  4587 Rizon 10 + F/T Sensor — Available; OEM application still
  5165 MOONLIGHT — Available; parallel robot studio hero

REJECT:
  4588 GRAV — end_effector gripper
  4589 GRAV ENHANCED — end_effector gripper

Specs from embedded OEM parameter JSON on flexiv.com/product/rizon|moonlight.
Rizon launch: Hannover Messe 2019 (flexiv.com news). Manufacturer country China.

Usage:
  python discover_flexiv_robots.py
  python discover_flexiv_robots.py --apply --copy-media
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

COMPANY_ID = 315
COMPANY_SLUG = "flexiv"
COMPANY_NAME = "Flexiv"
CN_ID = 3
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "flexiv-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

RIZON_URL = "https://www.flexiv.com/product/rizon"
MOONLIGHT_URL = "https://www.flexiv.com/product/moonlight"
LAUNCH_URL = "https://www.flexiv.com/news/new_product_launch_adaptive_robot_arm"
DATASHEET = (
    "https://flexiv.com/uploaded/en/resource/file/2024/09/20/5upqi2xywow.pdf"
)

RIZON4_HERO = (
    "https://cdn.robotaigeek.com/research-staging/flexiv/rizon4-white-hero.jpg"
)
RIZON4FT_HERO = (
    "https://cdn.robotaigeek.com/research-staging/flexiv/rizon4-silver-hero.jpg"
)
RIZON10_HERO = (
    "https://cdn.robotaigeek.com/research-staging/flexiv/rizon10-dark-hero.jpg"
)
RIZON10FT_HERO = (
    "https://cdn.robotaigeek.com/research-staging/flexiv/rizon10ft-app-hero.jpg"
)
MOONLIGHT_HERO = (
    "https://cdn.robotaigeek.com/research-staging/flexiv/moonlight-hero.jpg"
)

REJECT = [
    {
        "id": 4588,
        "name": "GRAV",
        "reason": (
            "non_robot_end_effector: Flexiv Grav is a 2-finger adaptive gripper "
            "(EOAT accessory on flexiv.com/product/grav), not a robot SKU."
        ),
    },
    {
        "id": 4589,
        "name": "GRAV ENHANCED",
        "reason": (
            "non_robot_end_effector: Flexiv Grav Enhanced is a heavier EOAT "
            "gripper variant, not a robot SKU."
        ),
    },
]

COMMON_RIZON_SOURCES = [
    {"url": RIZON_URL, "title": "Flexiv Rizon product page (OEM)"},
    {"url": LAUNCH_URL, "title": "Flexiv Rizon launch — Hannover Messe 2019"},
    {"url": DATASHEET, "title": "Flexiv Rizon datasheet PDF"},
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 2863,
        "name": "Flexiv RIZON 4",
        "model_name": "RIZON 4",
        "action": "enrich",
        "status": "pending_review",
        "url": RIZON_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "industrial-robots",
        "movement_type_keys": "stationary",
        "use_keys": "assembly|pick-and-place|inspection",
        "industry_keys": "others",
        "tags": "Cobot|Force Control|Adaptive|IP65|7-DOF|Assembly|Industrial",
        "dof": 7,
        "payload_kg": 4.0,
        "weight_kg": 20.0,
        "reach_mm": 876,
        "release_year": 2019,
        "images": [RIZON4_HERO],
        "video_queries": ["Flexiv Rizon 4 robot", "Flexiv Rizon adaptive robot"],
        "video_needles": ["flexiv", "rizon"],
        "video_reject": ["franka", "universal robots", "abb"],
        "description": (
            "Flexiv RIZON 4 is a 7-DOF adaptive collaborative robot arm with "
            "integrated force sensing, 4 kg payload, and IP65 protection for "
            "precision assembly and contact-rich tasks."
        ),
        "features": (
            "OEM flexiv.com/product/rizon parameter table: 7 DOF; payload 4 kg; "
            "weight 20 kg; reach 876 mm; protection IP65; pose repeatability "
            "+/-0.05 mm; force sensing accuracy 0.1 N; max TCP force 200 N; "
            "typical TCP linear speed 1.0 m/s; mounting flange ISO "
            "9409-1-50-4-M6; install in any orientation. Adaptive force control "
            "for contact-rich assembly/polishing/inspection. Launched Hannover "
            "Messe 2019 (OEM news). Hero replaced: prior CDN primary matched "
            "Franka-like lab still (reliable.png) — now verified Flexiv white "
            "studio ProductParameter cover with cyan joint rings."
        ),
        "purpose": "Adaptive 7-DOF cobot for force-controlled assembly and inspection",
        "sources": COMMON_RIZON_SOURCES,
    },
    {
        "id": 3644,
        "name": "Flexiv Rizon 4 + F/T Sensor",
        "model_name": "Rizon 4 + F/T Sensor",
        "action": "enrich",
        "status": "pending_review",
        "url": RIZON_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "industrial-robots",
        "movement_type_keys": "stationary",
        "use_keys": "assembly|pick-and-place|inspection",
        "industry_keys": "others",
        "tags": "Cobot|Force Control|Adaptive|IP65|7-DOF|F/T Sensor|Industrial",
        "dof": 7,
        "payload_kg": 4.0,
        "weight_kg": 21.0,
        "reach_mm": 919,
        "release_year": 2019,
        "images": [RIZON4FT_HERO],
        "video_queries": ["Flexiv Rizon 4 force torque sensor"],
        "video_needles": ["flexiv", "rizon"],
        "video_reject": ["franka", "universal robots", "abb"],
        "description": (
            "Flexiv Rizon 4 + F/T Sensor adds a wrist force/torque sensor package "
            "to the Rizon 4 adaptive arm for higher-accuracy contact tasks "
            "(4 kg payload, 919 mm reach)."
        ),
        "features": (
            "OEM flexiv.com/product/rizon column 'Rizon 4 + F/T Sensor': 7 DOF; "
            "payload 4 kg; weight 21 kg; reach 919 mm; IP65; pose repeatability "
            "+/-0.05 mm; force sensing accuracy 0.03 N; max TCP force 150 N; "
            "typical TCP linear speed 1.0 m/s; ISO 9409-1-50-4-M6 flange. "
            "F/T package vs base Rizon 4: longer reach, +1 kg arm mass, finer "
            "force sensing. Family launched 2019. Hero: silver Flexiv studio "
            "still (cyan joint rings) — distinct from white Rizon 4 / dark "
            "Rizon 10 heroes."
        ),
        "purpose": "Rizon 4 adaptive arm with wrist F/T sensor for precision contact work",
        "sources": COMMON_RIZON_SOURCES,
    },
    {
        "id": 3645,
        "name": "Flexiv RIZON 10",
        "model_name": "RIZON 10",
        "action": "enrich",
        "status": "pending_review",
        "url": RIZON_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "industrial-robots",
        "movement_type_keys": "stationary",
        "use_keys": "assembly|pick-and-place|inspection",
        "industry_keys": "others",
        "tags": "Cobot|Force Control|Adaptive|IP65|7-DOF|Assembly|Industrial",
        "dof": 7,
        "payload_kg": 10.0,
        "weight_kg": 38.0,
        "reach_mm": 941,
        "release_year": 2019,
        "images": [RIZON10_HERO],
        "video_queries": ["Flexiv Rizon 10 robot", "Flexiv Rizon 10 adaptive"],
        "video_needles": ["flexiv", "rizon"],
        "video_reject": ["franka", "universal robots", "abb"],
        "description": (
            "Flexiv RIZON 10 is the higher-payload 7-DOF adaptive cobot in the "
            "Rizon family (10 kg payload, 941 mm reach, IP65) for heavier "
            "force-controlled industrial tasks."
        ),
        "features": (
            "OEM flexiv.com/product/rizon 'RIZON 10': 7 DOF; payload 10 kg; "
            "weight 38 kg; reach 941 mm; IP65; pose repeatability +/-0.05 mm; "
            "force sensing accuracy 0.2 N; max TCP force 350 N; typical TCP "
            "linear speed 1.0 m/s; ISO 9409-1-50-4-M6 flange. Adaptive force "
            "control platform shared with Rizon 4. Family launched Hannover "
            "Messe 2019. Hero: dark charcoal Flexiv ProductParameter studio "
            "still with cyan joint rings."
        ),
        "purpose": "Higher-payload adaptive 7-DOF cobot for industrial contact tasks",
        "sources": COMMON_RIZON_SOURCES,
    },
    {
        "id": 4587,
        "name": "Flexiv Rizon 10 + F/T Sensor",
        "model_name": "Rizon 10 + F/T Sensor",
        "action": "enrich",
        "status": "pending_review",
        "url": RIZON_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "industrial-robots",
        "movement_type_keys": "stationary",
        "use_keys": "assembly|pick-and-place|inspection",
        "industry_keys": "others",
        "tags": "Cobot|Force Control|Adaptive|IP65|7-DOF|F/T Sensor|Industrial",
        "dof": 7,
        "payload_kg": 10.0,
        "weight_kg": 39.0,
        "reach_mm": 984,
        "release_year": 2019,
        "images": [RIZON10FT_HERO],
        "video_queries": ["Flexiv Rizon 10 force torque"],
        "video_needles": ["flexiv", "rizon"],
        "video_reject": ["franka", "universal robots", "abb"],
        "description": (
            "Flexiv Rizon 10 + F/T Sensor pairs the Rizon 10 adaptive arm with "
            "a wrist force/torque sensor for long-reach, high-payload contact "
            "applications (10 kg, 984 mm)."
        ),
        "features": (
            "OEM flexiv.com/product/rizon 'Rizon 10 + F/T Sensor': 7 DOF; "
            "payload 10 kg; weight 39 kg; reach 984 mm; IP65; pose "
            "repeatability +/-0.05 mm; force sensing accuracy 0.2 N; max TCP "
            "force 350 N; typical TCP linear speed 1.0 m/s; ISO "
            "9409-1-50-4-M6 flange. Longest reach in the Rizon table. Hero: "
            "OEM news application still showing Flexiv Rizon (cyan joint "
            "rings) in use — distinct hash from studio SKUs."
        ),
        "purpose": "Rizon 10 with wrist F/T sensor for long-reach force-controlled work",
        "sources": COMMON_RIZON_SOURCES,
    },
    {
        "id": 5165,
        "name": "Flexiv Moonlight",
        "model_name": "MOONLIGHT",
        "action": "enrich",
        "status": "pending_review",
        "url": MOONLIGHT_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "industrial-robots",
        "movement_type_keys": "stationary",
        "use_keys": "pick-and-place|assembly|inspection",
        "industry_keys": "others",
        "tags": "Parallel Robot|Delta|Force Control|IP65|Pick and Place|Industrial",
        "dof": 3,
        "weight_kg": 38.0,
        "height_mm": 400,
        "width_mm": 1200,
        "length_mm": 1200,
        "images": [MOONLIGHT_HERO],
        "video_queries": ["Flexiv Moonlight robot", "Flexiv Moonlight parallel"],
        "video_needles": ["flexiv", "moonlight"],
        "video_reject": ["franka", "abb", "fanuc"],
        "description": (
            "Flexiv Moonlight is a force-controlled parallel (delta-style) "
            "robot with 3 DOF, 1200 mm working diameter, and 400 mm max "
            "working height for high-speed precision tasks."
        ),
        "features": (
            "OEM flexiv.com/product/moonlight parameter table: 3 DOF; weight "
            "38 kg; max working height 400 mm; max working diameter 1200 mm; "
            "protection IP65; pose repeatability +/-0.05 mm; robot base "
            "diameter 206 mm; mounting flange ISO 9409-1-50-4-M6; max speed "
            "1.5 m/s / accel 15 m/s^2; install in any orientation. Marketed "
            "as the world's first force-controlled parallel robot (OEM). "
            "Typed height_mm=400 and width/length_mm=1200 map OEM max working "
            "height/diameter. Hero: OEM ProductParameter studio still of "
            "ceiling-mount parallel hardware."
        ),
        "purpose": "Force-controlled parallel robot for high-speed precision pick/place",
        "sources": [
            {"url": MOONLIGHT_URL, "title": "Flexiv Moonlight product page (OEM)"},
            {"url": "https://www.flexiv.com/", "title": "Flexiv home"},
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
        if "flexiv" not in blob:
            continue
        # Moonlight: require model token (Rizon videos also say Flexiv)
        if "moonlight" in needles and "moonlight" not in blob:
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
        "[AI Research] Flexiv enrich 2026-07-20. Replaced Franka-like Rizon heroes "
        "with OEM ProductParameter / news stills; Grav EOAT rejected; specs from "
        "flexiv.com embedded parameter JSON; Available."
    )
    row: dict[str, Any] = {
        "name": spec["name"],
        "model_name": spec.get("model_name") or spec["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CN",
        "manufacturer_country_codes": "CN",
        "description": spec["description"],
        "purpose": spec["purpose"],
        "features": spec["features"],
        "url": spec["url"],
        "image": images[0] if images else "",
        "images": images,
        "video_urls": kept,
        "movement_type_keys": spec.get("movement_type_keys") or "stationary",
        "category_slugs": spec.get("category_slugs") or "industrial-robots",
        "use_keys": spec.get("use_keys") or "assembly",
        "industry_keys": spec.get("industry_keys") or "others",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Flexiv 2026-07-20. Specs from OEM PDP parameter JSON; "
            "Rizon release_year 2019 from launch news; CN manufacturer country."
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
        "reach_mm",
        "runtime_minutes",
        "dof",
    ):
        if spec.get(k) is not None:
            row[k] = spec[k]
    return row


def patch_fields(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [CN_ID],
        "manufacturer_country_ref": CN_ID,
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
        "reach_mm",
        "runtime_minutes",
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
        "rejects": REJECT,
        "apply": bool(args.apply),
    }
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    used_hashes: set[str] = set()

    for spec in PRODUCTS:
        print(f"Building {spec['name']} ({spec['action']})...")
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
                "payload_kg": row.get("payload_kg"),
                "reach_mm": row.get("reach_mm"),
                "dof": row.get("dof"),
            }
        )

    if not args.apply:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps({"plan": plan, "rows": [r for _, r in rows]}, indent=2),
            encoding="utf-8",
        )
        print(f"Dry-run -> {REPORT}")
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
        if rid:
            patch_fields(client, int(rid), row)
            if args.copy_media and row.get("images"):
                print(f"copy-media {rid}:", copy_media(int(rid)))
            for item in plan["robots"]:
                if item["name"] == spec["name"]:
                    item["id"] = rid
                    item["import"] = result

    for rej in REJECT:
        print(f"Rejecting {rej['id']} {rej['name']}...")
        out = reject_robot(client, int(rej["id"]), rej["reason"])
        print(f"  -> {out}")
        rej["result"] = out

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
