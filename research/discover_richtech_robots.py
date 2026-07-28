"""Curated Richtech Robotics (131) discovery + enrich.

KEEP (create pending_review):
  Titan, Matradee Plus, Scorpion, DUST-E S, DUST-E MX, Pallet Jack

ENRICH:
  Dex (5277) — replace aggregator hero with OEM Sanity CDN
  ADAM Service Robot (162) — rename display to ADAM, OEM URL, taxonomy

SKIP (delete staging):
  Commercial/Industrial prefixed shells, Dex Stationary/Mobile as separate SKUs,
  Physical AI Robots, 818 Robot, ADAM the Robot, Richtech Robotics ADAM/Scorpion

Usage:
  python discover_richtech_robots.py
  python discover_richtech_robots.py --apply --copy-media
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

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from web_extract import WebFetcher, parse_page
from youtube_metadata import enrich_video_list

COMPANY_ID = 131
COMPANY_SLUG = "richtech-robotics"
COMPANY_NAME = "Richtech Robotics"
US_ID = 20
REPORT = _RESEARCH_DIR / "staging" / "reports" / "richtech-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# Visually / filename-mapped OEM heroes from Sanity CDN (richtechrobotics.com).
# Verified via product-page og/hero when page returns content; solutions cards otherwise.
PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "Dex",
        "id": 5277,
        "action": "enrich",
        "status": "pending_review",
        "url": "https://richtechrobotics.com/solutions/dex",
        "model_name": "Dex",
        "release_year": 2025,
        "availability_status": 11,  # available
        "category_slugs": "humanoid",
        "movement_type_keys": "wheeled",
        "use_keys": "material-handling|manipulation|other",
        "industry_keys": "manufacturing|logistics|warehousing",
        "tags": "Humanoid|Wheeled|Industrial|Autonomous|Material Handling|Dual Arm|AMR",
        "images": [
            "https://cdn.sanity.io/images/jakvqat5/production/de240542b5295357cd944c25bbf22610485641c8-1200x630.jpg",
            "https://cdn.sanity.io/images/jakvqat5/production/73dff85f4da9d679bd592aff55d3c13e3e833e2c-1580x1235.jpg",
            "https://cdn.sanity.io/images/jakvqat5/production/c54b0b56593aca88af07eefb80ab2336ee83b9fd-1350x1364.jpg",
        ],
        "videos": [],  # filled by filtered YouTube search (must include 'dex')
        "description": (
            "Dex is Richtech Robotics' wheeled industrial humanoid for manufacturing, "
            "logistics, and material-handling work. It combines an AMR-style mobile base "
            "with dual production arms and modular end-effectors, accelerated by NVIDIA Jetson Thor."
        ),
        "features": (
            "Wheeled mobile humanoid (OEM chose wheels over legs for energy, braking, and shared-space stability). "
            "Dual arms with modular end-effectors (hands, clamps, specialized tools). "
            "Four-camera vision for navigation and tasks in changing environments. "
            "About four hours battery in mobile mode; can run continuously from a static base. "
            "Simulated/trained in NVIDIA Isaac Sim and Isaac Lab (OEM CES 2026 / Dex unveil press)."
        ),
        "purpose": "Industrial material handling and light manufacturing tasks in human-shared spaces",
        "sources": [
            {"url": "https://richtechrobotics.com/solutions/dex", "title": "Dex product page"},
            {
                "url": "https://ir.richtechrobotics.com/news-releases/news-release-details/richtech-robotics-offers-first-look-dex-mobile-humanoid-robot",
                "title": "Dex first look press (2025-10-28)",
            },
        ],
    },
    {
        "name": "ADAM",
        "id": 162,
        "action": "enrich",
        "status": "published",
        "url": "https://richtechrobotics.com/solutions/adam",
        "model_name": "ADAM",
        "rename_from": "ADAM Service Robot",
        "availability_status": 11,
        "category_slugs": "service-robots",
        "movement_type_keys": "stationary",
        "use_keys": "other|manipulation",
        "industry_keys": "hospitality|retail|food-service",
        "tags": "Service Robot|Dual Arm|Hospitality|Retail|Beverage|AI|Commercial",
        "images": [
            "https://cdn.sanity.io/images/jakvqat5/production/5e492dd0d7053997efc776f2af361fe4058cdbc2-617x398.png",
        ],
        "videos": [],
        "description": (
            "ADAM is Richtech Robotics' dual-arm AI service robot for beverage preparation "
            "and customer-facing hospitality/retail. It automates mixing, shaking, and espresso "
            "workflows while interacting with guests."
        ),
        "features": (
            "Dual-arm beverage service robot for coffee, cocktails, and specialty drinks. "
            "Customer-facing commercial deployments (OEM: Walmart coffee, NVIDIA HQ cocktails, CES demos). "
            "Part of Richtech Commercial pillar alongside Scorpion and Matradee (SEC / company materials)."
        ),
        "purpose": "Automated beverage preparation and customer engagement in hospitality and retail",
        "sources": [
            {"url": "https://richtechrobotics.com/solutions/adam", "title": "ADAM product page"},
            {"url": "https://richtechrobotics.com/", "title": "Richtech Robotics"},
        ],
    },
    {
        "name": "Titan",
        "id": 5515,
        "action": "enrich",
        "status": "pending_review",
        "url": "https://richtechrobotics.com/solutions/titan",
        "model_name": "Titan",
        "availability_status": 11,
        "category_slugs": "service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "material-handling|delivery|other",
        "industry_keys": "logistics|automotive|warehousing|hospitality",
        "tags": "AMR|Logistics|Delivery|Wheeled|Service Robot|Autonomous|Material Handling",
        # Visual QA 2026-07-19: labeled TITAN OG banner (tray delivery) — NOT the DUST-E
        # solutions-card that was previously mis-mapped. titan-h on page is ADAM — banned.
        "images": [
            "https://cdn.sanity.io/images/jakvqat5/production/d88d9ef5a869c2cc6aafa282992a4c2f845f3368-1200x630.jpg",
            "https://cdn.sanity.io/images/jakvqat5/production/6e7976b65136295d2ff4424d2ef56f1745a8919a-900x909.png",
        ],
        "description": (
            "Titan is Richtech Robotics' multi-tray wheeled delivery robot for indoor "
            "logistics and facility routes, used in commercial and dealership deployments."
        ),
        "features": (
            "Multi-tray wheeled delivery robot in Richtech's Industrial pillar (OEM Titan page). "
            "OEM case: logistics delivery efficiency at Mercedes-Benz of Plano (company homepage). "
            "Tablet face interface with vertical column and open shelves for indoor payloads."
        ),
        "purpose": "Indoor logistics delivery and material movement",
        "sources": [
            {"url": "https://richtechrobotics.com/solutions/titan", "title": "Titan product page"},
        ],
    },
    {
        "name": "Matradee Plus",
        "action": "create",
        "url": "https://richtechrobotics.com/solutions/matradee-plus",
        "model_name": "Matradee Plus",
        "availability_status": 11,
        "category_slugs": "service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "delivery|other",
        "industry_keys": "hospitality|food-service|retail",
        "tags": "Service Robot|Delivery|Hospitality|Wheeled|Autonomous|Waiter|Commercial",
        "images": [
            "https://cdn.sanity.io/images/jakvqat5/production/d5b9df48528c8bd0d2f5751288fbe93de0c3c1d2-500x700.png",
        ],
        "description": (
            "Matradee Plus is Richtech's robot waiter/server assistant for restaurants and "
            "hospitality, with advertising display capability for complex floor layouts."
        ),
        "features": (
            "Food delivery and bussing server assistant (Matradee commercial line). "
            "Designed for complex restaurant layouts with advertising functionality (OEM solutions copy). "
            "Part of Commercial pillar with ADAM and Scorpion (SEC)."
        ),
        "purpose": "Restaurant food running, bussing, and guest service assistance",
        "sources": [
            {"url": "https://richtechrobotics.com/solutions/matradee-plus", "title": "Matradee Plus product page"},
        ],
    },
    {
        "name": "Scorpion",
        "action": "create",
        "url": "https://richtechrobotics.com/solutions/scorpion",
        "model_name": "Scorpion",
        "availability_status": 11,
        "category_slugs": "service-robots",
        "movement_type_keys": "stationary",
        "use_keys": "other|manipulation",
        "industry_keys": "hospitality|food-service|retail",
        "tags": "Service Robot|Beverage|Hospitality|AI|Commercial|Bartender",
        "images": [
            "https://cdn.sanity.io/images/jakvqat5/production/9aed94dbfadb5a164c47d4db91e95d79a24f83fa-337x418.png",
        ],
        "description": (
            "Scorpion is Richtech's AI-powered robot bartender for beverage service in "
            "commercial hospitality environments."
        ),
        "features": (
            "AI beverage/bartender service robot in the Commercial product pillar (SEC). "
            "OEM solutions copy: strikingly good beverage service with visual monitoring enhancements "
            "(CES 2026 Dex demo lineup)."
        ),
        "purpose": "Automated bartender and beverage service",
        "sources": [
            {"url": "https://richtechrobotics.com/solutions/scorpion", "title": "Scorpion product page"},
        ],
    },
    {
        "name": "DUST-E S",
        "action": "create",
        "url": "https://richtechrobotics.com/solutions/dust-e-s",
        "model_name": "DUST-E S",
        "availability_status": 11,
        "category_slugs": "service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "cleaning|other",
        "industry_keys": "commercial|hospitality|facilities",
        "tags": "Cleaning|Floor Cleaner|AMR|Wheeled|Autonomous|Commercial|Service Robot",
        "images": [
            "https://cdn.sanity.io/images/jakvqat5/production/17a6f17e1caf24f96a1f1cc6c27b5cb458537ed3-1200x630.jpg",
            # Visual QA: second card image was ADAM booth photo — rejected (sibling contamination).
            "https://cdn.sanity.io/images/jakvqat5/production/e20e7cadd199b0fa6f15c8fa67b91c3e96147df7-1000x958.png",
        ],
        "description": (
            "DUST-E S is Richtech's autonomous commercial floor cleaning robot for consistent "
            "indoor cleaning performance."
        ),
        "features": (
            "Autonomous floor cleaner in the DUST-E industrial/commercial cleaning line (OEM solutions page). "
            "Positioned for consistent, satisfying cleaning performance in commercial spaces (OEM copy)."
        ),
        "purpose": "Autonomous commercial floor cleaning",
        "sources": [
            {"url": "https://richtechrobotics.com/solutions/dust-e-s", "title": "DUST-E S product page"},
        ],
    },
    {
        "name": "DUST-E MX",
        "id": 5519,
        "action": "enrich",
        "status": "pending_review",
        "url": "https://richtechrobotics.com/solutions/dust-e-mx",
        "model_name": "DUST-E MX",
        "availability_status": 11,
        "category_slugs": "service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "cleaning|other",
        "industry_keys": "commercial|facilities|manufacturing",
        "tags": "Cleaning|Floor Cleaner|AMR|Wheeled|Autonomous|Industrial|Service Robot",
        # Visual QA: labeled DUST-E MX OG + distinct studio still (larger than DUST-E S brush unit).
        "images": [
            "https://cdn.sanity.io/images/jakvqat5/production/1a5dc0651733fca93e5456fd969139233437fb72-1200x630.jpg",
            "https://cdn.sanity.io/images/jakvqat5/production/2525567e2e415ad99e9bc2cd205b309811ec4482-1186x1130.jpg",
        ],
        "description": (
            "DUST-E MX is the larger/industrial sibling in Richtech's DUST-E autonomous cleaning line."
        ),
        "features": (
            "Industrial/commercial autonomous floor scrubber in the DUST-E family (OEM DUST-E MX page). "
            "Larger boxy chassis vs DUST-E S; cyan LED face panel and LiDAR mast (OEM hero). "
            "Part of Richtech Industrial pillar cleaning products (SEC)."
        ),
        "purpose": "Autonomous industrial/commercial floor cleaning",
        "sources": [
            {"url": "https://richtechrobotics.com/solutions/dust-e-mx", "title": "DUST-E MX product page"},
        ],
    },
    {
        "name": "Pallet Jack",
        "id": 5520,
        "action": "enrich",
        "status": "pending_review",
        "url": "https://richtechrobotics.com/solutions/pallet-jack",
        "model_name": "F3300",
        "availability_status": 11,
        "category_slugs": "service-robots",
        "movement_type_keys": "wheeled",
        "use_keys": "material-handling|other",
        "industry_keys": "warehousing|logistics|manufacturing",
        "tags": "Pallet Jack|F3300|AMR|Material Handling|Wheeled|Industrial|Logistics|Autonomous",
        # Visual QA via get_rendered: labeled Pallet Jack OG + F3300 render. Sibling cards banned.
        "images": [
            "https://cdn.sanity.io/images/jakvqat5/production/22664d5f5e21d1d8dc67fee586b115595d0a80ec-1200x627.jpg",
            "https://cdn.sanity.io/images/jakvqat5/production/4d275ecf9e05ce228706b89ba3027953b8cbbf3f-860x860.png",
            "https://cdn.sanity.io/images/jakvqat5/production/4e819ae2af83a1abf7bc9474f6f87457c39671bb-1563x832.jpg",
        ],
        "description": (
            "Richtech's F3300 autonomous pallet jack for industrial material handling "
            "and warehouse pallet moves."
        ),
        "features": (
            "Autonomous pallet jack (OEM model F3300 on product graphics). "
            "Forks with load wheels, LiDAR mast, HMI screen, and manual tiller override (OEM hero). "
            "Industrial pillar product alongside Titan and Dex (solutions category grouping)."
        ),
        "purpose": "Autonomous pallet transport in warehouses and facilities",
        "sources": [
            {"url": "https://richtechrobotics.com/solutions/pallet-jack", "title": "Pallet Jack product page"},
        ],
    },
]

JUNK_STAGING = [
    "commercial-adam.json",
    "commercial-dust-e-s.json",
    "commercial-matradee-plus.json",
    "commercial-scorpion.json",
    "industrial-dex.json",
    "industrial-titan.json",
    "industrial-pallet-jack.json",
    "industrial-dust-e-mx.json",
    "dex-stationary-platform.json",
    "dex-mobile-platform.json",
    "physical-ai-robots.json",
    "818-robot.json",
    "adam-the-robot.json",
    "richtech-robotics-adam.json",
    "richtech-robotics-scorpion.json",
]


def download_ok(url: str, *, min_bytes: int = 5000) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, timeout=45, headers=UA)
        data = r.content
        if r.status_code != 200 or len(data) < min_bytes:
            return False, "", len(data)
        if not (
            data[:3] == b"\xff\xd8\xff"
            or data[:8].startswith(b"\x89PNG")
            or data[:4] == b"RIFF"
        ):
            return False, "", len(data)
        return True, hashlib.md5(data).hexdigest(), len(data)
    except requests.RequestException:
        return False, "", 0


def copy_media(rid: int) -> str:
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
    for attempt in range(5):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return "ok"
            if resp.status_code not in (502, 503, 504):
                return f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            last = f"ERR {e}"
        time.sleep(2**attempt)
    return "fail"


def yt_search(query: str, limit: int = 6) -> list[str]:
    html = requests.get(
        "https://www.youtube.com/results",
        params={"search_query": query},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    ).text
    ids = list(dict.fromkeys(re.findall(r"watch\?v=([\w-]{11})", html)))[:limit]
    return [f"https://www.youtube.com/watch?v={i}" for i in ids]


def build_row(spec: dict[str, Any]) -> dict[str, Any]:
    images: list[str] = []
    seen: set[str] = set()
    for u in spec.get("images") or []:
        ok, md5, nbytes = download_ok(u)
        if not ok:
            print(f"  !! image fail {u}")
            continue
        if md5 in seen:
            continue
        seen.add(md5)
        images.append(u)
        print(f"  img ok {md5} {nbytes} {u[-50:]}")

    # Only scrape when explicitly allowed — empty images[] means fail-closed.
    banned_md5 = {
        "930f7a3938de5b46eefaac3ad13e259f",  # ADAM hero
        "b701bf2e8efda27136d17fcadc98bf12",  # ADAM booth mislabeled as cleaner
    }
    if spec.get("allow_image_scrape") and not images:
        f = WebFetcher(stealth=True)
        p = parse_page(f, spec["url"], rendered=False)
        for im in (p.images if p else []) or []:
            u = im if isinstance(im, str) else (im.get("url") or "")
            if "sanity.io" not in u and "richtech" not in u:
                continue
            if "contact.png" in u:
                continue
            ok, md5, _nbytes = download_ok(u)
            if not ok or md5 in seen or md5 in banned_md5:
                continue
            images.append(u)
            seen.add(md5)
            print(f"  scraped img {md5} {u[-60:]}")
            if len(images) >= 2:
                break

    query = f"Richtech Robotics {spec['name']}"
    vids = enrich_video_list(yt_search(query, limit=10))
    token = re.sub(r"[^a-z0-9]+", "", spec["name"].lower())
    aliases = {
        "dex": ["dex"],
        "adam": ["adam"],
        "titan": ["titan"],
        "matradeeplus": ["matradee"],
        "scorpion": ["scorpion"],
        "dustes": ["dust-e", "dust e", "duste"],
        "dustemx": ["dust-e mx", "dustemx"],
        "palletjack": ["richtech pallet"],
    }
    needles = aliases.get(token, [spec["name"].lower()])
    reject_sub = ["digit ", "mir1200", "mir ", "filics", "hexapod", "bmw", "porsche", "titan 440"]
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        if any(bad in title for bad in reject_sub):
            continue
        if token == "scorpion" and "richtech" not in title and "bartender" not in title:
            continue
        if token == "titan" and "richtech" not in title:
            continue
        if any(n in title for n in needles):
            kept.append(v)
    if token == "dex" and not kept:
        for v in enrich_video_list(yt_search("Richtech Dex robot", limit=8)):
            title = (v.get("title") or "").lower()
            if "dex" in title and "digit" not in title:
                kept.append(v)
    print(f"  videos kept={len(kept)}")
    for v in kept[:3]:
        print(f"    - {(v.get('title') or '')[:80]}")

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
        "video_urls": kept[:3],
        "movement_type_keys": spec.get("movement_type_keys") or "",
        "category_slugs": spec.get("category_slugs") or "service-robots",
        "use_keys": spec.get("use_keys") or "other",
        "industry_keys": spec.get("industry_keys") or "commercial",
        "tags": spec.get("tags") or "",
        "source_locale": "en",
        "availability_status": spec.get("availability_status") or 11,
        "research_notes": (
            f"[AI Research] Richtech discovery 2026-07-19. Curated OEM pages; "
            f"skipped Commercial/Industrial shell duplicates and Dex config SKUs."
        ),
        "sources": [
            {"url": s["url"], "type": "website", "title": s.get("title") or s["url"]}
            for s in (spec.get("sources") or [{"url": spec["url"]}])
        ],
        "information_source_urls": [s["url"] for s in (spec.get("sources") or [{"url": spec["url"]}])],
        "notes": "[AI Research] Richtech curated discovery.",
    }
    if spec.get("id"):
        row["id"] = spec["id"]
    if spec.get("release_year"):
        row["release_year"] = spec["release_year"]
    if not images:
        row["notes"] = (
            "[IMAGE TO-DO — no hero, deliberate]\n"
            f"No verified distinct OEM JPEG/PNG for {spec['name']} after stealth scrape of {spec['url']}.\n"
            "ACTION FOR TEAM: source OEM product still from Richtech press kit.\n"
            "Do NOT use sibling product renders.\n---\n"
        ) + row["notes"]
    return row


def patch_country_avail(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": row.get("availability_status") or 11,
    }
    if row.get("release_year"):
        body["release_year"] = row["release_year"]
    if row.get("model_name"):
        body["model_name"] = row["model_name"]
    if row.get("name"):
        body["name"] = row["name"]
    try:
        client._patch(f"robots/robots/{rid}/", body)
        print(f"  patched taxonomy fields {rid}")
    except Exception as e:  # noqa: BLE001
        print(f"  patch warn {rid}: {e}")


def find_by_name(client: ResearchApiClient, name: str) -> dict[str, Any] | None:
    for r in client.list_robots_for_company(COMPANY_ID) or []:
        if (r.get("name") or "") == name:
            return r
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument(
        "--only",
        default="",
        help="Comma-separated product names to process (default: all)",
    )
    args = ap.parse_args()

    only = {n.strip().lower() for n in args.only.split(",") if n.strip()}
    products = [p for p in PRODUCTS if not only or p["name"].lower() in only]
    if only and not products:
        print(f"No products matched --only={args.only!r}")
        return 1

    staging_dir = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG
    staging_dir.mkdir(parents=True, exist_ok=True)
    for junk in JUNK_STAGING:
        p = staging_dir / junk
        if p.exists():
            p.unlink()
            print(f"removed junk {junk}")

    client = ResearchApiClient()
    plan: dict[str, Any] = {"company_id": COMPANY_ID, "robots": [], "apply": bool(args.apply)}
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for spec in products:
        print(f"Building {spec['name']} ({spec['action']})…")
        row = build_row(spec)
        rows.append((spec, row))
        plan["robots"].append(
            {
                "name": spec["name"],
                "action": spec["action"],
                "id": spec.get("id"),
                "images_n": len(row.get("images") or []),
                "videos_n": len(row.get("video_urls") or []),
                "image_todo": not bool(row.get("images")),
            }
        )

    if not args.apply:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"plan": plan, "rows": [r for _, r in rows]}, indent=2), encoding="utf-8")
        print(f"Dry-run → {REPORT}")
        return 0

    for spec, row in rows:
        path = staging_dir / f"{spec['name'].lower().replace(' ', '-').replace('/', '-')}.json"
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        status = spec.get("status") or "pending_review"
        result = import_staging(
            path,
            dry_run=False,
            patch=bool(spec.get("id")),
            force_overwrite=True,
            replace_media=bool(row.get("images")),
            status=status,
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print(f"import {spec['name']}:", result)
        rid = spec.get("id")
        if not rid:
            created = find_by_name(client, spec["name"])
            rid = created["id"] if created else None
        if rid:
            patch_country_avail(client, rid, row)
            if args.copy_media and row.get("images"):
                cm = copy_media(rid)
                print(f"copy-media {rid}: {cm}")
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
