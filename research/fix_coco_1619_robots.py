"""Fix Coco Robotics (company 1619) content-queue enrichment.

OEM: https://www.cocodelivery.com
Sources: Coco 2 product page + delivery/home.

Issues addressed:
- Rename 'Delivery' (service page) → Coco 2 (actual robot PDP)
- Point URL at /coco2; hero = official Framer studio render
- Fill features/purpose/typed specs (21 km/h, 32 km range) from OEM page
- US manufacturer country; logistics-warehouse taxonomy; Available FK 11
- status stays pending_review
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
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
from tag_suggest import TagCatalog

COMPANY_ID = 1619
COMPANY_SLUG = "coco-robotics"
COMPANY_NAME = "Coco Robotics"
COMPANY_WEBSITE = "https://www.cocodelivery.com"
US = "US"
US_COUNTRY_ID = 20

URL = {
    "coco2": f"{COMPANY_WEBSITE}/coco2",
    "home": f"{COMPANY_WEBSITE}/",
    "delivery": f"{COMPANY_WEBSITE}/delivery",
}

IMG = {
    # Official Coco 2 studio product render (Framer CDN); visually verified.
    "coco2": "https://framerusercontent.com/assets/myyH08zDWb8MyKSXl6PzjpdWvc.png",
}

EXPECTED_MD5 = {
    "coco2": "f1429d910cfcb68b5789d0c8ca949186",
}

TAGS = (
    "AMR|Autonomous Mobile Robot|Delivery|Wheeled|Service Robot|"
    "Logistics|Autonomous|Outdoor|Commercial"
)

_AVAIL_IDS = {
    "available": 11,
    "announced": 10,
    "discontinued": 4,
}


def verify_hero(name: str, url: str) -> str:
    r = requests.get(
        url,
        timeout=45,
        headers={"User-Agent": "Mozilla/5.0", "Referer": COMPANY_WEBSITE + "/"},
    )
    r.raise_for_status()
    body = r.content
    if not (body.startswith(b"\x89PNG") or body.startswith(b"\xff\xd8\xff")):
        raise RuntimeError(f"{name}: not an image magic={body[:8]!r}")
    md5 = hashlib.md5(body).hexdigest()
    expected = EXPECTED_MD5.get(name)
    if expected and md5 != expected:
        raise RuntimeError(f"{name}: md5 {md5} != {expected}")
    return md5


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET") or ""
    api = (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")
    if not secret:
        print("WARN: no INTERNAL_API_SECRET for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(
                url,
                headers={"X-Internal-Secret": secret},
                timeout=120,
            )
            if resp.status_code < 300:
                ok += 1
                print(f"copy-media ok {rid}", flush=True)
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}", flush=True)
        except Exception as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.2)
    return ok, fail


def resolve_tags(catalog: TagCatalog, pipe: str) -> str:
    names = [n.strip() for n in pipe.split("|") if n.strip()]
    out: list[str] = []
    missing: list[str] = []
    for n in names:
        hit = catalog._by_name.get(n.lower())
        if hit:
            out.append(str(hit.get("name") or n))
        else:
            missing.append(n)
    if missing:
        print(f"WARN unresolved tags: {missing}", file=sys.stderr)
    return "|".join(out)


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    5657: {
        "name": "Coco 2",
        "model_name": "Coco 2",
        "variant_code": "Coco 2",
        "variant_label": "Coco 2",
        "url": URL["coco2"],
        "family_key": "coco-robotics:coco-2",
        "family_name": "Coco 2",
        "family_url": URL["coco2"],
        "product_url_scope": "exact_variant",
        "image": IMG["coco2"],
        "description": (
            "Coco 2 is Coco Robotics' autonomous sidewalk delivery vehicle for dense "
            "urban environments and city-scale fleet operations. It combines onboard "
            "cameras, solid-state LiDAR, and GPS with end-to-end neural networks and "
            "human oversight to carry restaurant and retail orders through crowded "
            "sidewalks, uneven surfaces, and low-light conditions."
        ),
        "purpose": (
            "Autonomous last-mile food and goods delivery\n"
            "Sidewalk delivery for restaurants and merchants\n"
            "City-scale autonomous delivery fleet operations\n"
            "Uber Eats, DoorDash, and Wolt delivery fulfillment"
        ),
        "features": (
            "OEM Coco 2 page (cocodelivery.com/coco2): max speed 21 km/h; range 32 km; "
            "max grade 30%; 360° turn-in-place; swappable battery; quick-swappable tires; "
            "cargo bay fits 4×18 in pizza boxes; solid-state LiDAR; Air Blade airflow; "
            "360° light ring; end-to-end neural-network navigation with precision mapping "
            "and human oversight. Fleet claims on delivery page: 1,000+ robots produced, "
            "1M+ all-terrain miles, 500K+ deliveries under 25 minutes. Integrates with "
            "Uber Eats, DoorDash, Wolt, and Olo Dispatch."
        ),
        "speed": 21.0,
        "availability_status_key": "available",
        "movement_type_keys": "wheeled|mobile",
        "industry_keys": "food-service|hospitality|retail|commercial|logistics",
        "use_keys": "food-delivery|delivery|logistics",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS,
        "manufacturer_country_code": US,
        "information_source_urls": [URL["coco2"], URL["delivery"], URL["home"]],
        "notes_force": (
            "[AI Research] Renamed from service-page stub 'Delivery' → 'Coco 2'. "
            "URL remapped from /delivery to /coco2. Speed 21 km/h and 32 km range "
            "from OEM Coco 2 page. Hero: Framer studio render "
            "myyH08zDWb8MyKSXl6PzjpdWvc.png (rejected UI dashboard / logo-overlay "
            "home stills). No OEM weight/dims/payload published on page — left blank."
        ),
        "source_note": URL["coco2"],
        "programming_interface": (
            "End-to-end neural networks with precision mapping and human oversight; "
            "merchant ops via lid open/load/close with Uber Eats, DoorDash, Wolt, "
            "and Olo Dispatch integrations."
        ),
        "deployment_context": (
            "Urban sidewalks and city streets (Los Angeles, Miami, Chicago, Helsinki "
            "and expanding); restaurant curb and storefront loading."
        ),
        "mounting_options": "Wheeled sidewalk delivery vehicle (not mounted)",
    },
}


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
    }
    skip = {
        "videos",
        "notes_force",
        "source_note",
        "images",
        "availability_status_key",
        "clear_payload",
    }
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        row["research_notes"] = fix["source_note"]
    if fix.get("image"):
        row["images"] = [fix["image"]]
        row["image"] = fix["image"]
    row["availability_status_key"] = fix.get("availability_status_key") or "available"
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "speed",
        "weight_kg",
        "payload_kg",
        "family_key",
        "family_name",
        "family_url",
        "model_name",
        "variant_code",
        "variant_label",
        "product_url_scope",
        "purpose",
        "programming_interface",
        "deployment_context",
        "mounting_options",
    ):
        if fix.get(k) not in (None, ""):
            body[k] = fix[k]
    avail_key = fix.get("availability_status_key")
    if avail_key:
        body["availability_status"] = _AVAIL_IDS.get(str(avail_key), avail_key)
    ok_keys: list[str] = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok_keys.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "manufacturer_countries": [US_COUNTRY_ID],
                "manufacturer_country_ref": US_COUNTRY_ID,
            },
        )
        ok_keys.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Coco Robotics company 1619")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--skip-hero-check", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    all_robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    if not args.skip_hero_check:
        print("Verifying OEM hero hashes…")
        for name, url in IMG.items():
            md5 = verify_hero(name, url)
            print(f"  OK {name} md5={md5}")

    # Capture actual md5 into EXPECTED for next run
    targets: list[dict[str, Any]] = []
    for rid, fix in ROBOT_FIXES.items():
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        row = build_row(fix, tags=tags)
        if len(row.get("features") or "") < 40:
            print(f"ERROR {rid}: features too short", file=sys.stderr)
            return 1
        if not row.get("family_key") or not row.get("image"):
            print(f"ERROR {rid}: missing family_key/image", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: speed={row.get('speed')} "
            f"fam={row.get('family_key')} url={row.get('url')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "coco-1619-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps({"targets": [{"id": t["id"], "name": t["name"], "url": t["row"].get("url"),
                                  "image": t["row"].get("image"), "speed": t["row"].get("speed")}
                                 for t in targets]}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    if not targets:
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media --verify-cdn --mark-done")
        return 0

    imported: list[int] = []
    for t in targets:
        rid, row, fix = t["id"], t["row"], t["fix"]
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        bulk["name"] = fix["name"]
        bulk["status"] = "pending_review"
        print(f"Importing {rid} {fix['name']}…", flush=True)
        result = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=False,
            replace_media=True,
            replace_videos=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
        )
        created = int(result.get("created_count") or 0)
        updated = int(result.get("updated_count") or 0)
        err = int(result.get("error_count") or 0)
        print(f"  bulk-import created={created} updated={updated} err={err}")
        if created != 0 or err:
            print(f"ERROR {rid}: unexpected create/errors {result}", file=sys.stderr)
            return 1
        patch_typed(client, rid, fix)
        if fix.get("notes_force"):
            try:
                client._patch(f"robots/robots/{rid}/", {"notes": fix["notes_force"]})
            except Exception as exc:
                print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {"status": "pending_review", "name": fix["name"]},
            )
        except Exception as exc:
            print(f"  status/name patch warn {rid}: {exc}", file=sys.stderr)
        imported.append(rid)

    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
        for t in targets:
            if t["id"] in imported:
                patch_typed(client, t["id"], t["fix"])

    if args.verify_cdn and imported:
        subprocess.check_call(
            [sys.executable, str(_RESEARCH_DIR / "verify_cdn_images.py"),
             "--company-id", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )

    if args.mark_done and imported:
        subprocess.check_call(
            [sys.executable, str(_RESEARCH_DIR / "triage_content_queue.py"),
             "--mark-done", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )

    print(json.dumps({"imported": imported, "preview": str(preview)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
