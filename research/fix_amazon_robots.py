"""Fix Amazon Robotics (company 12) content-queue QA issues.

Priorities:
- Kiva (DU 1000) vs Kiva (DU 3000) shared identical hero → distinct images
- Wikipedia/CJK junk features → English curated copy from aboutamazon sources
- Sparrow missing image; short features on Atlas/Ernie/Scooter/Kiva Drive Unit
- Robin/Sequoia/Vulcan scraped-nav junk features

Uses force_overwrite with preserved CRM fields so blank staging keys do not wipe data.
replace_media=True + copy-media for photo changes.
"""

from __future__ import annotations

import argparse
import json
import os
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
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

COMPANY_ID = 12
COMPANY_SLUG = "amazon-robotics"
COMPANY_NAME = "Amazon Robotics"

# Distinct heroes (sha256 verified pairwise-different; not CRM duplicate 2d3485aa…)
IMG_DU1000 = "https://www.allaboutlean.com/wp-content/uploads/2019/10/Amazon-Kiva-close-1.jpg"
IMG_DU3000 = (
    "https://assets.aboutamazon.com/c9/10/1db3cf344ecd942ac75062035b77/"
    "amazon-robotics-hercules-fulfillment-center-robot.jpg"
)
IMG_KIVA_GENERIC = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/d/db/"
    "Amazon_warehouse_robot_2020.JPG/1280px-Amazon_warehouse_robot_2020.JPG"
)
IMG_SPARROW = (
    "https://assets.aboutamazon.com/de/86/c9d4054547638d179ed84123f6f7/sparrow-hero-1.jpg"
)
IMG_SCOOTER = (
    "https://assets.aboutamazon.com/a1/a3/72b6fe3b449caded039b14111cef/scooter2.jpg"
)
# Official aboutamazon assets (verified visually 2026-07-15). Prefer direct assets.* URLs
# over dims4 transforms — they recopy more reliably to S3.
IMG_VULCAN = (
    "https://assets.aboutamazon.com/06/74/164d1fb0495f9696cb7ebdff3ff1/"
    "about-amazon-hero-inline020-aa-vulcan-amazon-msb-1270984mod-copy-9504x5346.jpg"
)
IMG_SEQUOIA = (
    "https://assets.aboutamazon.com/1b/58/1a5c0e9f45dea77882f8f6f115d5/hero-sequoia-2550px.jpg"
)
# Amazon Science still of Robin arm+gripper (official Robin article). Host is
# cdn.amazon.science; robot URL remapped to aboutamazon.com for domain match.
IMG_ROBIN = (
    "https://cdn.amazon.science/dims4/default/ce2038a/2147483647/strip/true/"
    "crop/2000x1050+0+66/resize/1200x630!/quality/90/"
    "?url=https%3A%2F%2Famzn-science-production-science.s3.us-east-1.amazonaws.com"
    "%2Fscience%2Fab%2F9d%2Fe2e012c84742bca761b0aa9b99a8%2Frobin-arm-with-gripper.jpg"
)
# Official Ernie YouTube still (Amazon-branded overlay labels Ernie; FANUC arm
# lifts tote from Amazon Robotics drive-unit shelf) — only clear still found.
IMG_ERNIE = "https://i.ytimg.com/vi/RZEweNlJijE/maxresdefault.jpg"

URL_FC_ROBOTS = (
    "https://www.aboutamazon.com/news/operations/amazon-robotics-robots-fulfillment-center"
)
URL_VULCAN = "https://www.aboutamazon.com/news/operations/amazon-vulcan-robot-pick-stow-touch"
URL_SEQUOIA = "https://www.aboutamazon.com/news/operations/amazon-introduces-new-robotics-solutions"
URL_ERNIE = (
    "https://www.aboutamazon.com/news/innovation-at-amazon/"
    "new-technologies-to-improve-amazon-employee-safety"
)
URL_TITAN = "https://www.aboutamazon.com/news/operations/amazon-unveils-titan-fulfillment-center-robot"

# Public Amazon Robotics stories live on aboutamazon.com. The brand site
# amazonrobotics.com is auth-walled (OAuth), so company.website must match
# aboutamazon or every robot URL flags url_domain_mismatch.
COMPANY_WEBSITE = "https://www.aboutamazon.com"

# Per-robot curated fixes. Only listed fields are force-replaced; others preserved from CRM.
ROBOT_FIXES: dict[int, dict[str, Any]] = {
    1592: {  # Kiva (DU 1000)
        "name": "Kiva (DU 1000)",
        "model_name": "DU 1000",
        "url": "https://www.aboutamazon.com/news/operations/amazon-robotics-robots-fulfillment-center",
        "image": IMG_DU1000,
        "images": [IMG_DU1000],
        "replace_media": True,
        "features": (
            "Original Kiva Systems orange drive unit for goods-to-person fulfillment. "
            "Slides under inventory pods, lifts via rotating platform, and delivers pods "
            "to pick stations. Documented payload capacity about 1,000 lb (≈450 kg) for "
            "standard ~39 in pods."
        ),
        "weight_kg": 110.0,
        "weight": "110 kg",
        "payload_kg": 450.0,
        "movement_type_keys": "wheeled",
        "availability_status_key": "discontinued",
        "tags": "AMR|Warehouse|Warehouse Automation|Wheeled|Logistics|Autonomous|Mobile Robot",
        "notes_force": (
            "Payload ~1,000 lb / 450 kg (Wikipedia/Amazon Robotics; MWPVL Kiva review). "
            "Hero: orange Amazon Robotics drive unit under yellow pod (AllAboutLean FC photo; "
            "distinct from DU 3000 Hercules hero)."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=UtBa9yVZBJM",
        ],
        "source_note": "DU 1000 hero + features curated 2026-07-12; prior CRM shared hero with DU 3000.",
    },
    1593: {  # Kiva (DU 3000)
        "name": "Kiva (DU 3000)",
        "model_name": "DU 3000",
        "url": "https://www.aboutamazon.com/news/operations/amazon-hercules-robot",
        "image": IMG_DU3000,
        "images": [IMG_DU3000],
        "replace_media": True,
        "features": (
            "Heavy-duty Kiva-era drive unit for larger pods and pallet loads up to about "
            "3,000 lb (≈1,400 kg). Lineage continues as Amazon Robotics Hercules (H Drive), "
            "a blue drive unit that lifts up to 1,250 lb per aboutamazon.com."
        ),
        "payload_kg": 1400.0,
        "movement_type_keys": "wheeled",
        "availability_status_key": "discontinued",
        "tags": "AMR|Warehouse|Warehouse Automation|Wheeled|Logistics|Autonomous|Mobile Robot",
        "notes_force": (
            "Historical DU 3000 capacity ~3,000 lb / 1,400 kg (Wikipedia/Amazon Robotics). "
            "Hero is official aboutamazon Hercules FC photo — modern blue successor to the "
            "heavy-duty drive line (distinct from DU 1000 orange pod photo). "
            "Hercules lift capacity: 1,250 lb (aboutamazon Hercules / Titan articles)."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=8-eMzTUm79A",
        ],
        "source_note": "DU 3000 distinct Hercules hero 2026-07-12; broke shared CRM photo with DU 1000.",
    },
    98: {  # Kiva Drive Unit (generic / CN junk)
        "name": "Kiva Drive Unit",
        "model_name": "Kiva Drive Unit",
        "url": "https://www.aboutamazon.com/news/operations/amazon-robotics-robots-fulfillment-center",
        "image": IMG_KIVA_GENERIC,
        "images": [IMG_KIVA_GENERIC],
        "replace_media": True,
        "description": (
            "First-generation autonomous mobile drive unit from Kiva Systems (now Amazon Robotics). "
            "Navigates encoded warehouse floors, slides under inventory pods, lifts them, and "
            "delivers goods to human pick stations — the foundation of Amazon's goods-to-person model."
        ),
        "purpose": "Goods-to-person inventory pod transport in fulfillment centers",
        "features": (
            "Autonomous drive unit navigating on floor markers; slides under pods; "
            "rotating lift platform; fleet coordination for dense storage; "
            "delivers shelves to pick stations without associates walking the aisles."
        ),
        "source_locale": "en",
        "movement_type_keys": "wheeled",
        "tags": "AMR|Warehouse|Warehouse Automation|Wheeled|Logistics|Autonomous|Mobile Robot",
        "videos": [
            "https://www.youtube.com/watch?v=UtBa9yVZBJM",
        ],
        "source_note": "Replaced CJK features/description; Wikimedia Amazon warehouse robot hero.",
    },
    3554: {  # Sparrow — missing image
        "name": "Sparrow (Amazon Robotics)",
        "url": "https://www.aboutamazon.com/news/operations/amazon-introduces-sparrow-a-state-of-the-art-robot-that-handles-millions-of-diverse-products",
        "image": IMG_SPARROW,
        "images": [IMG_SPARROW],
        "replace_media": True,
        "features": (
            "AI computer-vision picking arm that identifies and handles millions of diverse "
            "inventory items with suction grippers, preparing products for packing in "
            "Amazon fulfillment centers."
        ),
        "movement_type_keys": "stationary",
        "tags": "Warehouse|Pick-and-Place|Industrial|Logistics|AI|Computer Vision",
        "videos": [
            "https://www.youtube.com/watch?v=GV8KdDxNr44",
        ],
        "source_note": "Official aboutamazon Sparrow launch hero.",
    },
    2678: {  # Atlas — CDN AccessDenied; no verified distinct Atlas still (Titan "Atlas" still is Kiva)
        "name": "Atlas (Amazon Robotics)",
        "url": URL_TITAN,
        "image": "",
        "images": [],
        "replace_media": True,
        "clear_image": True,
        "features": (
            "Mobile tote-transport robot deployed in 2014. Navigates fulfillment center floors "
            "on wheels and moves product totes weighing up to 750 pounds, reducing manual "
            "tote hauling before later Hercules/Titan drive generations."
        ),
        "release_year": 2014,
        "payload_kg": 340.0,  # 750 lb ≈ 340 kg
        "movement_type_keys": "wheeled",
        "tags": "AMR|Warehouse|Wheeled|Logistics|Mobile Robot|Autonomous",
        "notes_force": (
            "Payload up to 750 lb (≈340 kg) per aboutamazon Titan unveil article. "
            "Hero cleared 2026-07-15: prior CDN object AccessDenied, and the only "
            "aboutamazon still labeled Atlas (…fulfillment-center-atlast.jpg) is a "
            "Kiva/orange drive unit — do not use. No verified distinct Atlas tote-cart "
            "still found."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=UtBa9yVZBJM",
        ],
        "source_note": "URL/features on aboutamazon Titan history; photo deliberately blank.",
    },
    1599: {  # Ernie — CDN AccessDenied
        "name": "Ernie",
        "url": URL_ERNIE,
        "image": IMG_ERNIE,
        "images": [IMG_ERNIE],
        "replace_media": True,
        "features": (
            "Workstation system with a robotic arm that removes totes from a robotic shelf "
            "and presents them to associates, reducing reach-and-bend motions at pick stations."
        ),
        "movement_type_keys": "stationary",
        "tags": "Warehouse|Pick-and-Place|Industrial|Logistics|Ergonomics",
        "videos": [
            "https://www.youtube.com/watch?v=RZEweNlJijE",
        ],
        "source_note": "Hero: Amazon YouTube Ernie still (branded); URL aboutamazon safety article.",
    },
    1600: {  # Scooter
        "name": "Scooter",
        "url": URL_ERNIE,
        "image": IMG_SCOOTER,
        "images": [IMG_SCOOTER],
        "replace_media": True,
        "features": (
            "Autonomously guided cart that tows empty totes and packages through fulfillment "
            "centers, reducing manual cart pulling and associate strain."
        ),
        "movement_type_keys": "wheeled",
        "tags": "AMR|Warehouse|Wheeled|Logistics|Autonomous|Mobile Robot",
        "videos": [
            "https://www.youtube.com/watch?v=cLLfIKMvE_k",
        ],
        "source_note": "Official aboutamazon scooter2.jpg hero + safety article features.",
    },
    1589: {  # Robin — CDN AccessDenied; was amazon.science (off company domain)
        "name": "Robin",
        "url": URL_FC_ROBOTS,
        "image": IMG_ROBIN,
        "images": [IMG_ROBIN],
        "replace_media": True,
        "features": (
            "Amazon's first robotic arm for outbound package sorting: grabs packages from "
            "conveyor belts and places them onto robotic drive units before the dock."
        ),
        "movement_type_keys": "stationary",
        "tags": "Warehouse|Pick-and-Place|Industrial|Logistics|Sorting",
        "videos": [
            "https://www.youtube.com/watch?v=GV8KdDxNr44",
        ],
        "source_note": (
            "URL remapped amazon.science → aboutamazon FC robots story (Robin section). "
            "Hero: Amazon Science Robin arm+gripper still."
        ),
    },
    1596: {  # Sequoia — CDN AccessDenied
        "name": "Sequoia",
        "url": URL_SEQUOIA,
        "image": IMG_SEQUOIA,
        "images": [IMG_SEQUOIA],
        "replace_media": True,
        "features": (
            "AI, robotics, and computer-vision system that consolidates inventory and "
            "transports it to containerized storage or employee workstations, speeding "
            "stow and pick workflows. Identifies and stores inventory up to 75% faster "
            "at fulfillment centers (aboutamazon)."
        ),
        "movement_type_keys": "wheeled",
        "tags": "Warehouse|Warehouse Automation|Logistics|AI|AMR",
        "videos": [
            "https://www.youtube.com/watch?v=8-eMzTUm79A",
        ],
        "source_note": "Official aboutamazon Sequoia launch hero (hero-sequoia-2550px).",
    },
    1595: {  # Vulcan — CDN AccessDenied
        "name": "Vulcan",
        "url": URL_VULCAN,
        "image": IMG_VULCAN,
        "images": [IMG_VULCAN],
        "replace_media": True,
        "features": (
            "Amazon's first robot with a sense of touch: force-feedback sensors and "
            "specialized end-of-arm tooling pick and stow items in inventory pods, "
            "including hard-to-reach locations."
        ),
        "movement_type_keys": "stationary",
        "tags": "Warehouse|Pick-and-Place|Industrial|Logistics|AI",
        "videos": [
            "https://www.youtube.com/watch?v=GV8KdDxNr44",
        ],
        "source_note": "Official aboutamazon Vulcan launch hero (inline020).",
    },
    2677: {  # Vulcan (Amazon Robotics) — keep in sync with 1595
        "name": "Vulcan (Amazon Robotics)",
        "url": URL_VULCAN,
        "image": IMG_VULCAN,
        "images": [IMG_VULCAN],
        "replace_media": True,
        "features": (
            "Amazon's first robot with a sense of touch: force-feedback sensors and "
            "specialized end-of-arm tooling pick and stow items in inventory pods, "
            "including hard-to-reach locations."
        ),
        "movement_type_keys": "stationary",
        "tags": "Warehouse|Pick-and-Place|Industrial|Logistics|AI",
        "source_note": "Synced hero/URL with Vulcan 1595; aboutamazon Vulcan article.",
    },
}


def _tag_string(robot: dict[str, Any]) -> str:
    tags = robot.get("tags") or robot.get("tags_m2m") or []
    if isinstance(tags, str):
        return tags
    if isinstance(tags, list):
        names = []
        for t in tags:
            if isinstance(t, dict):
                names.append(str(t.get("name") or t.get("slug") or "").strip())
            else:
                names.append(str(t).strip())
        return "|".join(n for n in names if n)
    return ""


def preserve_base(robot: dict[str, Any]) -> dict[str, Any]:
    """CRM fields to keep under force_overwrite unless explicitly fixed."""
    img = (robot.get("s3_image") or robot.get("image") or "").strip()
    return {
        "name": robot.get("name") or "",
        "model_name": robot.get("model_name") or robot.get("name") or "",
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "url": robot.get("url") or "",
        "image": img,
        "description": robot.get("description") or "",
        "purpose": robot.get("purpose") or "",
        "features": robot.get("features") or "",
        "notes": robot.get("notes") or "",
        "tags": _tag_string(robot),
        "source_locale": robot.get("source_locale") or "en",
        "release_year": robot.get("release_year"),
        "weight_kg": robot.get("weight_kg"),
        "weight": robot.get("weight") or "",
        "payload_kg": robot.get("payload_kg"),
    }


def build_row(robot: dict[str, Any], fix: dict[str, Any]) -> dict[str, Any]:
    row = preserve_base(robot)
    for key, val in fix.items():
        if key in ("replace_media", "notes_force", "source_note", "videos", "images", "clear_image"):
            continue
        if val is not None and val != "":
            row[key] = val
    if fix.get("clear_image"):
        row["image"] = ""
        row["images"] = []
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        existing = (row.get("research_notes") or "").strip()
        row["research_notes"] = (
            f"{existing} | {fix['source_note']}" if existing else fix["source_note"]
        )
    videos = fix.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    if fix.get("images") is not None:
        row["images"] = list(fix["images"])
    row["company_slug"] = COMPANY_SLUG
    row["company_name"] = COMPANY_NAME
    return row


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("WARN: no INTERNAL_API_SECRET / API base for copy-media", file=sys.stderr)
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
                print(f"copy-media fail {rid}: HTTP {resp.status_code}", flush=True)
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.1)
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Amazon Robotics company 12 QA issues")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*", help="Limit to robot ids")
    args = parser.parse_args()

    client = ResearchApiClient()

    # Align company website with public story domain so url_domain_mismatch clears.
    if args.apply:
        try:
            co = client.get_company(COMPANY_ID)
            cur = (co.get("website") or "").strip()
            if cur.rstrip("/") != COMPANY_WEBSITE.rstrip("/"):
                client.patch_company(COMPANY_ID, {"website": COMPANY_WEBSITE})
                print(f"company website: {cur!r} -> {COMPANY_WEBSITE}", flush=True)
            else:
                print(f"company website already {COMPANY_WEBSITE}", flush=True)
        except Exception as exc:
            print(f"WARN: could not patch company website: {exc}", file=sys.stderr)

    all_robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    targets = []
    for rid, fix in ROBOT_FIXES.items():
        if args.only and rid not in args.only:
            continue
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        row = build_row(robot, fix)
        targets.append(
            {
                "id": rid,
                "name": robot.get("name"),
                "replace_media": bool(fix.get("replace_media")),
                "image": row.get("image") or "",
                "features_len": len(row.get("features") or ""),
                "row": row,
            }
        )
        print(
            f"  {rid} {robot.get('name')}: "
            f"img={'NEW' if fix.get('replace_media') else 'keep'} "
            f"feat={len(row.get('features') or '')} "
            f"url={(row.get('url') or '')[:60]}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "amazon-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            [{k: v for k, v in t.items() if k != "row"} for t in targets],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not targets:
        print("ERROR: no targets", file=sys.stderr)
        return 1
    # Require distinct heroes for the Kiva pair when both targeted
    ids = {t["id"] for t in targets}
    if 1592 in ids and 1593 in ids:
        u1000 = next(t["image"] for t in targets if t["id"] == 1592)
        u3000 = next(t["image"] for t in targets if t["id"] == 1593)
        if u1000 == u3000:
            print("ERROR: DU 1000 and DU 3000 still share the same image URL", file=sys.stderr)
            return 1

    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="amazon-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    imported: list[int] = []
    all_ok = True
    for item in targets:
        rid = item["id"]
        row = item["row"]
        fix = ROBOT_FIXES[rid]
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        fpath = tmp / f"{slugify_robot_name(str(item['name']))}-{rid}.json"
        fpath.write_text(json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            result = client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=False,  # force_overwrite path
                replace_media=bool(fix.get("replace_media")),
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            continue
        # force_overwrite = update_existing and not patch_existing
        # bulk_import_robots uses patch_existing flag — need force via update without patch
        # Looking at API: update_existing=True, patch_existing=False → full overwrite of mapped fields
        err = int(result.get("error_count") or 0)
        if err:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result}", file=sys.stderr)
        else:
            imported.append(rid)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  imported {rid}: {result.get('results')}")

    # Direct PATCH for notes_force / clear_image if bulk packed notes oddly
    for item in targets:
        rid = item["id"]
        fix = ROBOT_FIXES[rid]
        patch: dict[str, Any] = {}
        if fix.get("notes_force"):
            patch["notes"] = fix["notes_force"]
        if fix.get("clear_image"):
            patch["image"] = ""
            patch["s3_image"] = ""
        if not patch:
            continue
        try:
            client._patch(f"robots/robots/{rid}/", patch)
            print(f"  patched {rid}: {list(patch)}")
        except Exception as exc:
            print(f"  patch fail {rid}: {exc}", file=sys.stderr)

    copy_stats = None
    if args.copy_media:
        need = [
            t["id"] for t in targets
            if t["replace_media"] and not ROBOT_FIXES[t["id"]].get("clear_image") and t["image"]
        ]
        ok, fail = trigger_copy_media(need)
        copy_stats = {"ok": ok, "fail": fail, "ids": need}
        print(f"copy-media ok={ok} fail={fail} ids={need}")

    out = {
        "ok": all_ok,
        **totals,
        "imported": imported,
        "copy_media": copy_stats,
        "preview": str(preview),
    }
    (_RESEARCH_DIR / "staging" / "reports" / "amazon-fix-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
