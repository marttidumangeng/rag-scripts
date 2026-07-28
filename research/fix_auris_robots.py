"""Backfill Auris Health / J&J MedTech (company 1511) — MONARCH QUEST.

Single pending robot. Source of truth: jnjmedtech.com MONARCH Platform bronchoscopy
page + March 2025 FDA 510(k) clearance press release for MONARCH QUEST software/navigation.
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

COMPANY_ID = 1511
COMPANY_SLUG = "auris-health-johnson-johnson"
COMPANY_NAME = "Auris Health (J&J MedTech)"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

PRODUCT_URL = (
    "https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/"
)
PRESS_URL = (
    "https://www.jnjmedtech.com/en-US/news/press-releases/"
    "johnson-johnson-medtech-announces-clearance-of-monarch-quest-"
    "for-enhanced-robotic-assisted-bronchoscopy/"
)
FDA_510K = "https://www.accessdata.fda.gov/cdrh_docs/pdf24/K243219.pdf"

# Official Contentstack assets (JPEG, no webp) — filename includes QUEST.
QUEST_HERO = (
    "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
    "bltb8423cc70c8de6f9/693c6a3b1c8295672c529ddd/"
    "US_SRG_RADS_389015.1_Introducing_MONARCH%E2%84%A2_QUEST_Alt_card_1.jpg"
    "?width=1920&quality=90"
)
QUEST_UI = (
    "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
    "blt56332663aa4dd6f5/693c6a4931ed5e7752af6178/"
    "US_SRG_RADS_389015.1_Introducing_MONARCH%E2%84%A2_QUEST_Hero.jpg"
    "?width=1920&quality=90"
)
TAGS = (
    "Surgical Robot|Medical|Healthcare|Navigation|AI|"
    "Flexible Automation|Stationary"
)

# J&J MedTech / MONARCH QUEST titled demos only (reject Ion / competitor clips).
VIDEOS = [
    "https://www.youtube.com/watch?v=hqA6fhX7BB4",  # Imaging integration with MONARCH QUEST | J&J
]

ROBOT_DATA: dict[str, dict[str, Any]] = {
    "MONARCH QUEST": {
        "url": f"{PRODUCT_URL}#monarch-quest",
        "image": QUEST_HERO,
        "images": [QUEST_HERO, QUEST_UI],
        "description": (
            "MONARCH QUEST is Johnson & Johnson MedTech's next-generation AI navigation "
            "software for the MONARCH Platform robotic-assisted bronchoscopy system "
            "(Auris Health). It adds more powerful AI-powered navigation algorithms and "
            "integration with GE HealthCare OEC 3D and Siemens Cios Spin imaging to help "
            "clinicians target hard-to-reach peripheral lung nodules."
        ),
        "features": (
            "U.S. FDA 510(k) cleared (announced March 12, 2025) as the latest MONARCH "
            "navigation advancement for robotically assisted bronchoscopy. "
            "AI-powered navigation and image-processing algorithms; NVIDIA RTX–accelerated "
            "compute cited as ~260% more real-time computational power vs prior navigation. "
            "Verified imaging integration with GE HealthCare OEC 3D mobile CBCT (OEC Open) "
            "and Siemens Cios Spin for intraprocedural 3D targeting / tool-in-lesion workflows. "
            "Builds on MONARCH Platform: first flexible robotically assisted bronchoscopy "
            "system to market; scope-in-sheath design with independent articulation; continuous "
            "vision during navigation and biopsy; access to all 18 lung segments. "
            "Intended to provide bronchoscopic visualization of and access to patient airways "
            "for diagnostic and therapeutic procedures (U.S. IFU)."
        ),
        "purpose": (
            "AI-enhanced robotic bronchoscopy navigation\n"
            "Intraprocedural 3D imaging-guided lung nodule targeting"
        ),
        "family_key": "auris-health:monarch",
        "family_name": "MONARCH",
        "variant_code": "MONARCH-QUEST",
        "variant_label": "QUEST",
        "release_year": 2025,
        "videos": VIDEOS,
        "tags": TAGS,
        "source_note": (
            f"Product copy/features from {PRODUCT_URL} (MONARCH QUEST section: AI navigation, "
            "GE OEC 3D + Siemens Cios Spin). Clearance / NVIDIA 260% claim from {PRESS_URL} "
            "(12 Mar 2025). Heroes: official Contentstack QUEST Alt_card_1 clinical system still + "
            "QUEST UI hero + platform operator still. YouTube: QUEST-titled J&J demos + platform overview."
            " FDA K243219 documents the cleared MONARCH Platform underlying the QUEST update. "
            "No public system mass, dimensions, payload, reach, DOF, or price appears in the "
            "PDP, clearance release, support resources, or FDA summary."
        ),
    },
}


def verify_image(url: str) -> bool:
    try:
        resp = requests.head(url, headers=HEADERS, timeout=25, allow_redirects=True)
        if resp.status_code == 405 or "image" not in (resp.headers.get("content-type") or "").lower():
            resp = requests.get(url, headers=HEADERS, timeout=45, stream=True)
            resp.close()
        ctype = (resp.headers.get("content-type") or "").lower()
        if resp.status_code != 200:
            return False
        if "image" in ctype:
            return True
        return bool(re.search(r"\.(png|jpe?g|webp)(\?|$)", url, re.I))
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
                break
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("WARN: missing INTERNAL_API_SECRET or API base for copy-media")
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
                print(f"copy-media OK {rid}")
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.15)
    return ok, fail


def build_row(robot: dict, data: dict[str, Any]) -> dict[str, Any]:
    images, media_audit = validate_media([
        u for u in [data.get("image") or "", *(data.get("images") or [])] if u
    ])
    hero = images[0] if images else ""

    videos = enrich_video_list(data.get("videos") or [])
    return {
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
        "category_slugs": "ground",
        "sub_category_slug": "healthcare",
        "tags": data.get("tags") or TAGS,
        "availability_status": 11,
        "release_year": data["release_year"],
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": PRODUCT_URL,
        "model_name": robot["name"],
        "variant_code": data["variant_code"],
        "variant_label": data["variant_label"],
        "product_url_scope": "family",
        "sources": [
            {"url": data["url"], "type": "website", "title": "MONARCH QUEST"},
            {"url": PRESS_URL, "type": "news", "title": "MONARCH QUEST 510(k) clearance"},
            {"url": FDA_510K, "type": "documentation", "title": "FDA K243219 MONARCH Platform"},
        ],
        "information_source_urls": [data["url"], PRESS_URL, FDA_510K],
        "research_notes": data.get("source_note") or "MONARCH QUEST enrichment.",
        "_media_audit": media_audit,
    }


def patch_company_website(client: ResearchApiClient) -> None:
    try:
        co = client._get(f"companies/{COMPANY_ID}/")
    except Exception as exc:
        print(f"company fetch fail: {exc}")
        return
    website = "https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/"
    try:
        client.patch_company(COMPANY_ID, {"website": website, "country_ref": 20})
        print(f"company website -> {website}")
    except Exception as exc:
        try:
            client._patch(f"companies/{COMPANY_ID}/", {"website": website, "country_ref": 20})
            print(f"company website -> {website}")
        except Exception as exc2:
            print(f"company website patch skipped: {exc}; {exc2}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Auris / MONARCH QUEST for company 1511")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--patch-company", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    if args.patch_company or args.apply:
        patch_company_website(client)

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
            "url": row.get("url"),
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
            "family_key": row.get("family_key"),
            "availability_status": row.get("availability_status"),
            "media_audit": media_audit,
        })
        print(
            f"{robot['name']}: img={'yes' if row.get('image') else 'no'} "
            f"feat={len(row.get('features') or '')} "
            f"vids={len(row.get('video_urls') or [])} url={row.get('url')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "auris-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if any(
        not p["image"] or not p["features_len"] or not p["videos"] or not p["tags"]
        or not p["family_key"] or p["availability_status"] != 11
        for p in plan
    ):
        print("ERROR: incomplete enrichment", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="auris-fix-"))
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
                "availability_status": 11,
                "release_year": data["release_year"],
                "family_key": data["family_key"],
                "family_name": data["family_name"],
                "family_url": PRODUCT_URL,
                "model_name": row["name"],
                "variant_code": data["variant_code"],
                "variant_label": data["variant_label"],
                "product_url_scope": "family",
                "purpose": data["purpose"],
                "information_source_urls": [
                    {
                        "url": source["url"],
                        "title": source["title"],
                        "source_type": source["type"],
                    }
                    for source in row["sources"]
                ],
                "manufacturer_countries": [20],
                "manufacturer_country_ref": 20,
            },
        )
        for k in totals:
            totals[k] += result.get(k, 0) or 0
        print(f"IMPORT OK {rid} {row['name']}")

    print(json.dumps({"ok": all_ok, **totals, "imported": imported}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
