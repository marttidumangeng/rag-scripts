"""Curated Anduril Industries (284) enrich + reject non-robots.

CONTEXT (2026-07-20):
  9 pending. Shared 2.7 KB placeholder heroes on most robot-160* CDN paths
  (identical md5) — replaced with OEM Sanity / press stills.
  Lattice Mesh = software mesh/SDK. Menace-X = expeditionary C4 compute, not a robot.
  Barracuda-100/250: no distinct OEM still (family page shares one factory shot) —
  reject as family dupes; keep Barracuda-500 as canonical.

ENRICH:
  1607 Fury (YFQ-44A) — Available; CCA flight still
  376 Ghost — Available; OEM silhouette still
  377 Altius — Available; OEM UK ALE field still
  1605 Barracuda-500 — Available; factory still (family canonical)
  1609 Dive-XL — Available; deploy still (Anduril-branded AUV)

REJECT:
  1606 Lattice Mesh — non_robot software
  1608 Menace-X — non_robot C4 platform
  1603 Barracuda-100 — duplicate_family of 1605 (no distinct hero)
  1604 Barracuda-250 — duplicate_family of 1605 (no distinct hero)

Usage:
  python discover_anduril_robots.py
  python discover_anduril_robots.py --apply --copy-media
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

COMPANY_ID = 284
COMPANY_SLUG = "anduril"
COMPANY_NAME = "Anduril Industries"
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH_DIR / "staging" / "reports" / "anduril-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

FURY_URL = "https://www.anduril.com/fury"
GHOST_URL = "https://www.anduril.com/ghost"
ALTIUS_URL = "https://www.anduril.com/altius"
BARRACUDA_URL = "https://www.anduril.com/barracuda"
DIVEXL_URL = "https://www.anduril.com/dive-xl"
FURY_NEWS = (
    "https://www.anduril.com/news/"
    "anduril-yfq-44a-begins-flight-testing-for-the-collaborative-combat-aircraft-program"
)

FURY_HERO = "https://cdn.robotaigeek.com/research-staging/anduril/fury-yfq44a-flight-hero.jpg"
BARRACUDA_HERO = "https://cdn.robotaigeek.com/research-staging/anduril/barracuda-factory-hero.jpg"
DIVEXL_HERO = "https://cdn.robotaigeek.com/research-staging/anduril/dive-xl-deploy-hero.jpg"
ALTIUS_HERO = "https://cdn.robotaigeek.com/research-staging/anduril/altius-field-hero.jpg"
GHOST_HERO = "https://cdn.robotaigeek.com/research-staging/anduril/ghost-silhouette-hero.jpg"

REJECT = [
    {
        "id": 1606,
        "name": "Lattice Mesh",
        "reason": (
            "non_robot_software: Lattice Mesh is Anduril's tactical data/mesh "
            "software layer + SDK (anduril.com/lattice), not a robot SKU."
        ),
    },
    {
        "id": 1608,
        "name": "Menace-X",
        "reason": (
            "non_robot_c4_platform: Menace-X is an expeditionary C4/compute "
            "node hosting Lattice at the edge (anduril.com/menace-x), not a robot."
        ),
    },
    {
        "id": 1603,
        "name": "Barracuda-100",
        "reason": (
            "duplicate_family_of_1605: Barracuda-100/250/500 share one OEM family "
            "page and one factory still; keep Barracuda-500 (1605) as canonical "
            "until distinct per-size heroes exist."
        ),
    },
    {
        "id": 1604,
        "name": "Barracuda-250",
        "reason": (
            "duplicate_family_of_1605: Barracuda-100/250/500 share one OEM family "
            "page and one factory still; keep Barracuda-500 (1605) as canonical "
            "until distinct per-size heroes exist."
        ),
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 1607,
        "name": "Anduril Fury",
        "model_name": "Fury (YFQ-44A)",
        "url": FURY_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "aerial",
        "movement_type_keys": "aerial",
        "use_keys": "patrol|monitoring|other",
        "industry_keys": "defense",
        "tags": "UAV|CCA|Autonomous|Aerial|Defense|USA|Fury",
        "release_year": 2024,
        "images": [FURY_HERO],
        "video_queries": ["Anduril Fury YFQ-44A", "Anduril Fury CCA flight"],
        "video_needles": ["anduril", "fury", "yfq"],
        "video_reject": ["lattice mesh", "ghost shark"],
        "description": (
            "Fury is Anduril's autonomous Collaborative Combat Aircraft (CCA) "
            "air vehicle (USAF designation YFQ-44A), powered by Lattice for "
            "near-fighter-speed performance and modular mission payloads."
        ),
        "features": (
            "OEM anduril.com/fury + flight-test news: autonomous air vehicle for "
            "USAF CCA / manned-unmanned teaming; Lattice software stack; modular "
            "mission payloads. Hero is OEM flight-test still of YFQ-44A (nose "
            "boom, USAF markings) from Anduril news — replaces shared 2.7 KB "
            "placeholder CDN graphic. Soft: no public OEM typed dims/weight/"
            "speed table on product page."
        ),
        "purpose": "Autonomous collaborative combat aircraft for manned-unmanned teaming",
        "sources": [
            {"url": FURY_URL, "title": "Anduril Fury product page"},
            {"url": FURY_NEWS, "title": "Anduril YFQ-44A flight testing news"},
        ],
    },
    {
        "id": 376,
        "name": "Anduril Ghost",
        "model_name": "Ghost",
        "url": GHOST_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "aerial",
        "movement_type_keys": "aerial",
        "use_keys": "monitoring|patrol|exploration",
        "industry_keys": "defense",
        "tags": "UAV|VTOL|ISR|Aerial|Defense|USA|Ghost",
        "payload_kg": 11.3,  # OEM: payloads up to 25 lbs
        "images": [GHOST_HERO],
        "video_queries": ["Anduril Ghost-X drone", "Anduril Ghost UAS"],
        "video_needles": ["anduril", "ghost"],
        "video_reject": ["ghost shark", "ghost robotics"],
        "description": (
            "Ghost is Anduril's portable VTOL ISR UAS family (Ghost-X current) "
            "for hover-and-stare reconnaissance with modular multi-mission "
            "payloads and denied-environment resilient nav/comms."
        ),
        "features": (
            "OEM anduril.com/ghost: single-rotor VTOL; 3-axis hover/stare; "
            "field-swappable payload bays / rail for multiple payloads up to "
            "25 lb (typed payload_kg 11.3); EO/LWIR/MWIR/laser marker options; "
            "packs into <8 cu ft slim tactical case; dual-battery endurance and "
            "resilient nav/comms for low-connectivity environments. EN features "
            "replace CJK stub. Hero: OEM product silhouette still (artistic "
            "dark lighting — form-factor clear). Soft: no public L/W/H/weight "
            "table."
        ),
        "purpose": "Portable VTOL ISR UAS for multi-mission reconnaissance",
        "sources": [
            {"url": GHOST_URL, "title": "Anduril Ghost product page"},
        ],
    },
    {
        "id": 377,
        "name": "Anduril Altius",
        "model_name": "Altius",
        "url": ALTIUS_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "aerial",
        "movement_type_keys": "aerial",
        "use_keys": "monitoring|patrol|exploration",
        "industry_keys": "defense",
        "tags": "UAV|Loitering|Tube-launched|Aerial|Defense|USA|Altius",
        "images": [ALTIUS_HERO],
        "video_queries": ["Anduril Altius drone", "Anduril Altius-600 ALE"],
        "video_needles": ["anduril", "altius"],
        "video_reject": ["altius insurance"],
        "description": (
            "Altius is Anduril's tube-/multi-domain-launched autonomous air "
            "vehicle family for ISR, SIGINT, EW, comms relay, and coordinated "
            "strikes with modular payloads (Altius-M kinetic variant)."
        ),
        "features": (
            "OEM anduril.com/altius: multi-domain launch (air/land/sea platforms "
            "e.g. MRZR/JLTV/UH-60 class); modular payload nose for ISR&T/"
            "SIGINT/EW/comms relay; Altius-M for collaborative teaming and "
            "coordinated strikes; one operator can control multiple assets. EN "
            "features replace CJK stub. URL set to product page (was news-only). "
            "Hero: OEM UK ALE field still with airframe on cradle. Soft: no "
            "public typed dims/weight/speed."
        ),
        "purpose": "Multi-domain launched autonomous air vehicle for ISR and effects",
        "sources": [
            {"url": ALTIUS_URL, "title": "Anduril Altius product page"},
            {
                "url": "https://www.anduril.com/news/altius-600-achieves-uk-milestone-in-ale-test-with-leonardo",
                "title": "Altius-600 UK ALE milestone (OEM news)",
            },
        ],
    },
    {
        "id": 1605,
        "name": "Anduril Barracuda",
        "model_name": "Barracuda-500",
        "url": BARRACUDA_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "aerial",
        "movement_type_keys": "aerial",
        "use_keys": "patrol|other",
        "industry_keys": "defense",
        "tags": "UAV|Cruise|Attritable|Aerial|Defense|USA|Barracuda",
        "images": [BARRACUDA_HERO],
        "video_queries": ["Anduril Barracuda autonomous air vehicle", "Anduril Barracuda-500"],
        "video_needles": ["anduril", "barracuda"],
        "video_reject": ["barracuda networks"],
        "description": (
            "Barracuda is Anduril's family of air-breathing Autonomous Air "
            "Vehicles built for hyper-scale production and mass employment from "
            "ground, air, and maritime launchers; Barracuda-500 is the "
            "canonical catalog record for the family."
        ),
        "features": (
            "OEM anduril.com/barracuda family page: air-breathing turbojet AAVs; "
            "external rails for surface/air launch (rotary/fixed-wing, ground "
            "vehicles, boats; 5th-gen fighter bays); low-cost COTS-heavy "
            "form factor (~70–78 in class cited on page); flexible kinetic/"
            "non-kinetic payloads (~35–40 lb class cited across variants — not "
            "typed per SKU without column map). Barracuda-100/250 rejected as "
            "family shells lacking distinct heroes. Hero: OEM factory still "
            "(ANDURIL markings, unit 5001) — replaces shared placeholder CDN "
            "graphic."
        ),
        "purpose": "Air-breathing attritable autonomous air vehicle for mass employment",
        "sources": [
            {"url": BARRACUDA_URL, "title": "Anduril Barracuda family page"},
        ],
    },
    {
        "id": 1609,
        "name": "Anduril Dive-XL",
        "model_name": "Dive-XL",
        "url": DIVEXL_URL,
        "availability_status": AVAILABLE,
        "category_slugs": "underwater",
        "movement_type_keys": "underwater",
        "use_keys": "exploration|monitoring|patrol",
        "industry_keys": "defense",
        "tags": "AUV|Underwater|XL-AUV|Defense|USA|Dive-XL",
        "images": [DIVEXL_HERO],
        "video_queries": ["Anduril Dive-XL AUV", "Anduril Ghost Shark XL-AUV"],
        "video_needles": ["anduril", "dive-xl", "dive xl", "ghost shark"],
        "video_reject": ["ghost robotics"],
        "description": (
            "Dive-XL is Anduril's extra-large autonomous undersea vehicle for "
            "long-range, long-duration missions with large modular payloads "
            "(baseline for Australia's Ghost Shark XL-AUV program)."
        ),
        "features": (
            "OEM anduril.com/dive-xl: XL-AUV with all-electric powertrain for "
            "long-range missions without surfacing; two-point lift for ship/"
            "pier launch-recover; carries up to three payload modules or one "
            "extra-large module (e.g. Copperhead / Seabed Sentry class); open "
            "architecture for third-party payloads. Hero: Anduril-branded AUV "
            "water deploy still (Naval News / Anduril picture) — replaces "
            "shared placeholder CDN graphic. Soft: no public typed dims/"
            "weight/speed on product page."
        ),
        "purpose": "Extra-large autonomous undersea vehicle for long-endurance missions",
        "sources": [
            {"url": DIVEXL_URL, "title": "Anduril Dive-XL product page"},
            {
                "url": "https://www.anduril.com/news/ghost-shark-xl-auv-arrives-in-the-united-states",
                "title": "Ghost Shark XL-AUV arrives in US (OEM news)",
            },
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


def force_en_translations(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"anduril-en-force-{rid}-20260720-{loc}",
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
            timeout=90,
        )
        print(f"  translation-sync {rid}: {resp.status_code} {resp.text[:100]}")
    except requests.RequestException as e:
        print(f"  translation-sync warn {rid}: {e}")


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
        if "anduril" not in blob:
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
        "[AI Research] Anduril enrich 2026-07-20. Replaced shared placeholder "
        "CDN heroes; rejected Lattice Mesh + Menace-X + Barracuda-100/250; "
        "OEM product/news copy; Available."
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
        "movement_type_keys": spec.get("movement_type_keys") or "aerial",
        "category_slugs": spec.get("category_slugs") or "aerial",
        "use_keys": spec.get("use_keys") or "patrol",
        "industry_keys": spec.get("industry_keys") or "defense",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or AVAILABLE,
        "research_notes": (
            "[AI Research] Anduril 2026-07-20. Soft specs absent on most PDPs; "
            "Ghost 25 lb payload typed."
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
    for k in ("weight_kg", "height_mm", "width_mm", "length_mm", "speed", "release_year", "payload_kg", "dof"):
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
    for k in ("weight_kg", "height_mm", "width_mm", "length_mm", "speed", "release_year", "payload_kg", "dof"):
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
        print(f"Building {spec['name']}...")
        row = build_row(spec, used_hashes)
        if not row.get("images"):
            print(f"  !! FAIL CLOSED — no images for {spec['name']}")
        rows.append((spec, row))
        plan["robots"].append(
            {
                "name": spec["name"],
                "id": spec.get("id"),
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
            status="pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        rid = spec.get("id")
        if rid:
            patch_fields(client, int(rid), row)
            force_en_translations(client, int(rid), row)
            if args.copy_media:
                print(f"copy-media {rid}:", copy_media(int(rid)))

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
