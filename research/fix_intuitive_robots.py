"""Backfill Intuitive Surgical (company 52) pending robots: photo, features, specs, videos.

Live intuitive.com pages are behind Incapsula. Content is assembled from:
- Official intuitive.com CDN images (HEAD-verified)
- Wayback Machine snapshots / Serper snippets for copy
- YouTube search for product videos
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

COMPANY_ID = 52
COMPANY_SLUG = "intuitive-surgical"
COMPANY_NAME = "Intuitive Surgical"
HEADERS = {"User-Agent": "Mozilla/5.0"}
AVAILABLE = 11
FDA_DV5 = "https://www.accessdata.fda.gov/cdrh_docs/pdf23/K232610.pdf"
FDA_ION = "https://www.accessdata.fda.gov/cdrh_docs/pdf18/K182188.pdf"
SP_BROCHURE = (
    "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Pdf/"
    "da-vinci-sp-system-brochure-1047732.pdf"
)
DV5_BROCHURE = (
    "https://info.intuitive.com/rs/901-UBE-883/images/"
    "MAT03172_da_Vinci_5_Brochure.pdf?version=0"
)
ION_BROCHURE = (
    "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Pdf/"
    "intuitive-ion-system-brochure-1051118.pdf"
)

# Curated enrichment keyed by exact robot name in prod.
ROBOT_DATA: dict[str, dict[str, Any]] = {
    "Da Vinci SP": {
        "url": "https://www.intuitive.com/en-us/products-and-services/da-vinci/sp",
        "image": "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/Davinci/sp-system-front-view.jpg",
        "images": [
            "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/Davinci/sp-system-front-view.jpg",
            "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/Davinci-Systems/davinci-sp-single-port-surgical-robot-system-patient-cart.jpg",
            "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/Da-Vinci-SP-Instruments/da-vinci-sp-instrument-cluster.jpg",
        ],
        "description": (
            "Da Vinci SP is Intuitive's single-port robotic surgical system, engineered to perform "
            "robotic-assisted surgery through a single incision or natural orifice. It is designed "
            "for precision in compact spaces, including extraperitoneal and natural-orifice approaches."
        ),
        "purpose": (
            "Single-port urologic surgery\n"
            "Transoral otolaryngology surgery through a natural orifice"
        ),
        "features": (
            "Single-port access through one incision or natural orifice. "
            "Purpose-built for surgery in compact anatomical spaces. "
            "Articulating instruments and endoscope delivered through a single port. "
            "Supports personalized surgical approaches alongside multiport da Vinci systems. "
            "Intended for robotic-assisted soft-tissue procedures where single-port access is preferred."
        ),
        "manipulation": "high",
        "videos": [
            "https://www.youtube.com/watch?v=TGjnb86HndU",
        ],
        "family_key": "intuitive:da-vinci",
        "family_name": "da Vinci",
        "variant_code": "SP1098",
        "variant_label": "SP",
        "release_year": 2018,
        "tags": "Surgical Robot|Medical|Healthcare|Stationary|Compact",
        "sources": [SP_BROCHURE],
        "source_note": (
            "Official PDP and SP system brochure. No public system mass, component dimensions, "
            "payload, reach, or total-system DOF was found; instrument carton dimensions were "
            "not misapplied to the platform."
        ),
    },
    "Da Vinci 5": {
        "url": "https://www.intuitive.com/en-us/products-and-services/da-vinci/5",
        "image": (
            "https://ml.globenewswire.com/Resource/Download/"
            "4813abf0-2ddb-48c9-bc8a-35558ed9bb9b"
        ),
        "images": [
            (
                "https://ml.globenewswire.com/Resource/Download/"
                "4813abf0-2ddb-48c9-bc8a-35558ed9bb9b"
            ),
        ],
        "description": (
            "Da Vinci 5 is Intuitive's fifth-generation multiport robotic surgical system — "
            "the company's most advanced and integrated multiport platform. It emphasizes "
            "outcomes, OR efficiency, and actionable intraoperative insights, with FDA clearance "
            "as the latest addition to the da Vinci family."
        ),
        "purpose": (
            "Adult urologic and gynecologic minimally invasive surgery\n"
            "Adult general laparoscopic and thoracoscopic surgery"
        ),
        "features": (
            "Fifth-generation multiport da Vinci platform with integrated digital insights. "
            "Force Feedback instruments with real-time Force Gauge tissue-force display. "
            "Simplified setup, guided tool change, and task automation for faster learning. "
            "Universal user interface across surgeon console, patient cart, and vision cart. "
            "Designed to support minimally invasive procedures including cardiac approaches through small incisions."
        ),
        "manipulation": "high",
        "videos": [
            "https://www.youtube.com/watch?v=MxIuOdny2cs",
        ],
        "family_key": "intuitive:da-vinci",
        "family_name": "da Vinci",
        "variant_code": "IS5000",
        "variant_label": "5",
        "release_year": 2024,
        "tags": "Surgical Robot|Medical|Healthcare|Stationary|Vision",
        "sources": [DV5_BROCHURE, FDA_DV5],
        "source_note": (
            "Official Intuitive PDP, brochure, FDA K232610, and Intuitive-issued full-system "
            "press image. No public system mass, dimensions, payload, reach, or total-system "
            "DOF was found in the PDP, brochure, or FDA summary."
        ),
    },
    "Ion robotic bronchoscopy": {
        "url": "https://www.intuitive.com/en-us/products-and-services/ion",
        "image": "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/About-the-systems/ion-system.jpeg",
        "images": [
            "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/About-the-systems/ion-system.jpeg",
            "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/Ion/ion-suite-integrated-with-cios-spin.jpg",
        ],
        "description": (
            "Ion is Intuitive's robotic-assisted bronchoscopy platform for minimally invasive "
            "peripheral lung navigation and biopsy. It helps physicians reach small, hard-to-access "
            "lung nodules with shape-sensing catheter control and integrated imaging workflows."
        ),
        "purpose": (
            "Peripheral lung nodule navigation and biopsy\n"
            "Fiducial marker placement in the pulmonary tract"
        ),
        "features": (
            "Robotic-assisted bronchoscopy for peripheral lung nodule access. "
            "Shape-sensing catheter navigation for precise airway targeting. "
            "Designed for minimally invasive lung biopsy workflows. "
            "Integrates with imaging suites for intraoperative guidance. "
            "Complements Intuitive's da Vinci soft-tissue surgery portfolio for thoracic care pathways."
        ),
        "manipulation": "high",
        "videos": [
            "https://www.youtube.com/watch?v=0ZaobUiJhCQ",
        ],
        "family_key": "intuitive:ion",
        "family_name": "Ion",
        "variant_code": "IF1000",
        "variant_label": "Ion",
        "release_year": 2019,
        "tags": "Surgical Robot|Medical|Healthcare|Navigation|Stationary|AI",
        "sources": [ION_BROCHURE, FDA_ION],
        "source_note": (
            "Official PDP, Ion system brochure, and FDA K182188. The brochure documents a "
            "3.5 mm catheter outer diameter, 2.0 mm working channel, 180° articulation, and "
            "all 18 lung segments; these have no correct Robot typed columns. No public system "
            "mass, overall dimensions, payload, reach, or total-system DOF was found."
        ),
    },
    "Da Vinci Instruments": {
        "url": "https://www.intuitive.com/en-us/products-and-services/da-vinci/instruments",
        "image": "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/Da-Vinci-SP-Instruments/da-vinci-sp-instrument-cluster.jpg",
        "images": [
            "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/Da-Vinci-SP-Instruments/da-vinci-sp-instrument-cluster.jpg",
            "https://www.intuitive.com/en-us/-/media/ISI/Intuitive/Images/Synchroseal/da-vinci-synchroseal-hero.jpg",
        ],
        "description": (
            "Da Vinci instruments are Intuitive's EndoWrist and accessory portfolio for robotic-assisted "
            "surgery — a curated set of tools that translate surgeon hand motion into precise "
            "instrument tip motion beyond the limits of the human wrist."
        ),
        "features": (
            "Wide instrument portfolio spanning clip appliers, bipolar and monopolar energy tools, "
            "needle drivers, suction/irrigation, and specialty EndoWrist instruments. "
            "Designed for wristed articulation and tremor filtration at the instrument tip. "
            "Supports multiport and single-port da Vinci platforms with system-specific instrument families. "
            "Includes energy devices such as SynchroSeal for sealing and dividing tissue. "
            "Backed by product catalogs and user manuals for OR staff and surgeons."
        ),
        "dof": 7,
        "manipulation": "high",
        "videos": [
            "https://www.youtube.com/watch?v=TGjnb86HndU",
            "https://www.youtube.com/watch?v=MxIuOdny2cs",
        ],
        "source_note": "Official CDN instrument imagery + Intuitive instruments page portfolio categories (Wayback headings).",
    },
}


def verify_image(url: str) -> bool:
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code == 405:
            resp = requests.get(url, headers=HEADERS, timeout=20, stream=True)
            resp.close()
        return resp.status_code == 200 and "image" in (resp.headers.get("content-type") or "")
    except requests.RequestException:
        return False


def validate_media(urls: list[str]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    valid: list[str] = []
    audit: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for url in dict.fromkeys(urls):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=45)
            body = resp.content
            magic_ok = body.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF"))
            digest = hashlib.md5(body).hexdigest()
            duplicate = digest in seen
            audit[url] = {
                "status": resp.status_code, "bytes": len(body), "md5": digest,
                "magic_ok": magic_ok, "duplicate": duplicate,
            }
            if resp.status_code == 200 and magic_ok and len(body) >= 10_000 and not duplicate:
                valid.append(url)
                seen.add(digest)
        except requests.RequestException as exc:
            audit[url] = {"error": str(exc)}
    return valid, audit


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.1)
    return ok, fail


def build_row(robot: dict, data: dict[str, Any]) -> dict[str, Any]:
    images, media_audit = validate_media([
        u for u in [data.get("image") or "", *(data.get("images") or [])] if u
    ])
    hero = images[0] if images else ""

    videos = enrich_video_list(data.get("videos") or [])
    row: dict[str, Any] = {
        "name": robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "description": data["description"],
        "purpose": data["purpose"],
        "features": data["features"],
        "url": data["url"],
        "image": hero,
        "images": images,
        "video_urls": videos,
        "movement_type_keys": "stationary",
        # Match published Da Vinci Xi (id 60) taxonomy on this company.
        "category_slugs": "ground",
        "sub_category_slug": "healthcare",
        "manipulation": data.get("manipulation") or "",
        "availability_status": AVAILABLE,
        "release_year": data["release_year"],
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": data["url"],
        "model_name": robot["name"],
        "variant_code": data["variant_code"],
        "variant_label": data["variant_label"],
        "product_url_scope": "exact_variant",
        "tags": data["tags"],
        "sources": [
            {"url": data["url"], "type": "website", "title": f"{robot['name']} product page"},
            *[
                {"url": url, "type": "documentation", "title": f"{robot['name']} technical source"}
                for url in data["sources"]
            ],
        ],
        "information_source_urls": [data["url"], *data["sources"]],
        "research_notes": data.get("source_note") or "Intuitive Surgical product enrichment.",
        "_media_audit": media_audit,
    }
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Intuitive Surgical robots for company 52")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") != "published"
    ]
    print(f"targets: {len(robots)}")

    plan = []
    staging: dict[int, dict] = {}
    for robot in robots:
        data = ROBOT_DATA.get(robot["name"])
        if not data:
            print(f"SKIP {robot['id']} {robot['name']}: no curated data")
            continue
        row = build_row(robot, data)
        media_audit = row.pop("_media_audit")
        staging[int(robot["id"])] = row
        plan.append({
            "id": robot["id"],
            "name": robot["name"],
            "image": bool(row.get("image")),
            "features_len": len(row.get("features") or ""),
            "family_key": row.get("family_key"),
            "availability_status": row.get("availability_status"),
            "media_audit": media_audit,
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
        })
        print(
            f"{robot['name']}: img={'yes' if row.get('image') else 'no'} "
            f"feat={len(row.get('features') or '')} family={row.get('family_key')} "
            f"vids={len(row.get('video_urls') or [])} tags={bool(row.get('tags'))}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "intuitive-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if any(
        not p["image"] or not p["features_len"] or not p["videos"]
        or not p["family_key"] or p["availability_status"] != AVAILABLE
        for p in plan
    ):
        print("ERROR: incomplete enrichment", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="intuitive-fix-"))
    imported: list[int] = []
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0}
    all_ok = True
    for item in plan:
        rid = item["id"]
        row = staging[rid]
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = import_staging(
            fpath,
            patch=False,
            force_overwrite=True,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=True,
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result.get('errors')}", file=sys.stderr)
            continue
        imported.append(rid)
        data = ROBOT_DATA[row["name"]]
        video_result = client.bulk_import_robots(
            [row],
            update_existing=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_videos=True,
        )
        if video_result.get("error_count"):
            all_ok = False
            print(f"VIDEO REPLACE FAIL {rid}: {video_result}", file=sys.stderr)
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "pending_review",
                "dof": None,
                "availability_status": AVAILABLE,
                "release_year": data["release_year"],
                "family_key": data["family_key"],
                "family_name": data["family_name"],
                "family_url": data["url"],
                "model_name": row["name"],
                "variant_code": data["variant_code"],
                "variant_label": data["variant_label"],
                "product_url_scope": "exact_variant",
                "purpose": data["purpose"],
                "information_source_urls": [
                    {
                        "url": source["url"],
                        "title": source["title"],
                        "source_type": source["type"],
                    }
                    for source in row["sources"]
                ],
            },
        )
        client._patch(f"robots/robots/{rid}/", {"tags": []})
        client._patch(
            f"robots/robots/{rid}/",
            {"tags": [tag for tag in data["tags"].split("|") if tag]},
        )
        for k in totals:
            totals[k] += result.get(k, 0) or 0

    print(json.dumps({"ok": all_ok, **totals}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
