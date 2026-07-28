"""Fix Drone Delivery Canada (company 1509) content-queue enrichment.

OEM: https://dronedeliverycanada.com
Sources: /technology/ (Sparrow, Canary), fleet brochure PDF, landing-page fleet
section (Robin XL, Condor), MDA for Condor MTOW / Robin pause, Canary articles.

Issues addressed:
- All 4 pending robots imageless
- Empty company website + null company country FK
- Press-release URLs for Condor/Robin → prefer technology / landing fleet pages
- Missing family_* / tags / stale Released availability
- purpose rewritten as OEM applications (one per line)
- Typed specs from OEM tables (payload, speed km/h, MTOW weight_kg)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
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
from tag_suggest import TagCatalog
from youtube_metadata import enrich_video_list

COMPANY_ID = 1509
COMPANY_SLUG = "drone-delivery-canada"
COMPANY_NAME = "Drone Delivery Canada"
COMPANY_WEBSITE = "https://dronedeliverycanada.com"
CA = "CA"
CA_COUNTRY_ID = 1

URL_TECH = f"{COMPANY_WEBSITE}/technology/"
URL_SPARROW = f"{URL_TECH}#sparrow"
URL_CANARY = f"{URL_TECH}#canary"
URL_CANARY_ARTICLE = (
    f"{COMPANY_WEBSITE}/technology/advanced-drone-technology-the-canary-rpa/"
)
URL_CANARY_OVER_PEOPLE = (
    f"{COMPANY_WEBSITE}/technology/"
    "breaking-barriers-ddcs-canary-drone-approved-for-flight-over-people/"
)
URL_LANDING = f"{COMPANY_WEBSITE}/landing-page/"
URL_BROCHURE = (
    f"{COMPANY_WEBSITE}/wp-content/uploads/2022/08/"
    "2022_Drone-Fleet-Brochure_NEW_Final-1.pdf"
)
URL_ROBIN_PRESS = (
    f"{COMPANY_WEBSITE}/press-releases/"
    "drone-delivery-canada-announces-update-on-successful-robin-xl-testing/"
)
URL_CONDOR_PRESS = (
    f"{COMPANY_WEBSITE}/press-releases/"
    "ddc-announces-update-on-successful-condor-testing/"
)
URL_MDA_2022 = (
    f"{COMPANY_WEBSITE}/wp-content/uploads/2023/03/FY22-Q4-MDA-FINAL.pdf"
)

# Distinct OEM product photos (md5-verified unique; visually checked).
IMG = {
    "Sparrow": f"{COMPANY_WEBSITE}/wp-content/uploads/2022/08/Sparrow.png",
    "Canary": f"{COMPANY_WEBSITE}/wp-content/uploads/2022/08/Canary.png",
    "Robin XL": f"{COMPANY_WEBSITE}/wp-content/uploads/2022/08/Robin-XL.png",
    "Condor": f"{COMPANY_WEBSITE}/wp-content/uploads/2022/08/Condor.png",
}
EXPECTED_MD5 = {
    "Sparrow": "be3d931c35856ebdb9b4b5e5a194a9f4",
    "Canary": "8520f340d314f52211cdbd390a77f356",
    "Robin XL": "bad9a0f99389bedac21937de57979e0a",
    "Condor": "f5c5c896b4baf9cd58b655ff5e34ca38",
}

YT_COMPANY = "https://www.youtube.com/watch?v=dUvDEODUln4"
YT_HOSPITAL = "https://www.youtube.com/watch?v=UIdqlST8050"
YT_CANARY_FLY = "https://www.youtube.com/watch?v=eD6_HyinsGg"
YT_CANARY_INTRO = "https://www.youtube.com/watch?v=iu3FJUxkLzw"
YT_NEXT_SPARROW = "https://www.youtube.com/watch?v=zoJwrXO4Zm0"
YT_ROBIN = "https://www.youtube.com/watch?v=2RMdutcyKnA"
YT_CONDOR = "https://www.youtube.com/watch?v=z6alNN-Uaxk"
YT_CONDOR_LAUNCH = "https://www.youtube.com/watch?v=FFGXRjcuoak"
YT_CONDOR_TEASER = "https://www.youtube.com/watch?v=TTHJu81_f0k"

TAGS_MULTI = "Drone|UAV|Delivery|Autonomous Flight|Logistics|Aerial|Quadrotor|Outdoor|Electric"
TAGS_ROBIN = "Drone|UAV|Delivery|Autonomous Flight|Logistics|Aerial|VTOL|Fixed-wing|Outdoor|Electric"
TAGS_CONDOR = "Drone|UAV|Delivery|Autonomous Flight|Logistics|Aerial|Outdoor"

PURPOSE_SPARROW = (
    "Short-range cargo delivery\n"
    "Medical supply transport\n"
    "Remote community logistics\n"
    "Depot-to-depot parcel transfer"
)
PURPOSE_CANARY = (
    "Last-mile parcel delivery\n"
    "Urban flight-over-people cargo\n"
    "Medical sample and medicine transport\n"
    "Touchless cargo drop"
)
PURPOSE_ROBIN = (
    "Mid-range cargo delivery\n"
    "Temperature-controlled freight\n"
    "Harsh-climate logistics\n"
    "Automated cargo deployment"
)
PURPOSE_CONDOR = (
    "Heavy-lift cargo delivery\n"
    "Long-range remote logistics\n"
    "Industrial parts transport\n"
    "Bulk medical and community supply"
)

_AVAIL_IDS = {
    "announced": 10,
    "available": 11,
    "released": 3,
    "discontinued": 4,
    "pre_order": 12,
}


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }


def verify_hero(name: str, url: str) -> str:
    resp = requests.get(url, timeout=60, headers=_headers())
    resp.raise_for_status()
    data = resp.content
    if data[:8] != b"\x89PNG\r\n\x1a\n" and data[:3] != b"\xff\xd8\xff":
        raise RuntimeError(f"{name}: not an image magic={data[:8]!r}")
    md5 = hashlib.md5(data).hexdigest()
    expected = EXPECTED_MD5.get(name)
    if expected and md5 != expected:
        raise RuntimeError(f"{name}: md5 mismatch got={md5} expected={expected}")
    if len(data) < 8_000:
        raise RuntimeError(f"{name}: image too small ({len(data)} bytes)")
    return md5


def _admin_base() -> str:
    api = (os.environ.get("IMPORT_SYNC_API_BASE_URL") or "").rstrip("/")
    if api.endswith("/api/v1"):
        return api[: -len("/api/v1")]
    return api.rsplit("/api/", 1)[0] if "/api/" in api else api


def _internal_secret() -> str:
    return (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    )


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = _internal_secret()
    api = _admin_base()
    if not secret:
        print("WARN: no INTERNAL_API_SECRET for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            body: dict[str, Any] = {}
            try:
                body = resp.json() if resp.content else {}
            except Exception:
                body = {}
            success = bool(body.get("success")) if "success" in body else resp.ok
            if resp.ok and success:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code} body={body}", flush=True)
        except requests.RequestException as exc:
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


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
    }
    skip = {"videos", "notes_force", "source_note", "images", "replace_media"}
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        row["research_notes"] = fix["source_note"]
    videos = fix.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    if fix.get("image"):
        row["images"] = [fix["image"]]
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "payload_kg",
        "weight_kg",
        "speed",
        "family_key",
        "family_name",
        "family_url",
        "model_name",
        "variant_code",
        "variant_label",
        "product_url_scope",
        "purpose",
        "name",
        "manufacturer_country_code",
        "url",
    ):
        if k in fix and fix[k] not in (None, ""):
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
    # M2M country list — manufacturer_country_code alone can leave manufacturer_countries=[]
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {"manufacturer_countries": [CA_COUNTRY_ID], "manufacturer_country_ref": CA_COUNTRY_ID},
        )
        ok_keys.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def patch_company(client: ResearchApiClient) -> None:
    try:
        client._patch(
            f"companies/{COMPANY_ID}/",
            {"website": COMPANY_WEBSITE, "country_id": CA_COUNTRY_ID},
        )
        print(f"company patched website={COMPANY_WEBSITE} country_id={CA_COUNTRY_ID}")
    except Exception as exc:
        print(f"company patch fail: {exc}", file=sys.stderr)


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    5103: {
        "name": "Sparrow",
        "model_name": "Sparrow",
        "variant_code": "Sparrow",
        "variant_label": "Sparrow",
        "url": URL_SPARROW,
        "family_key": f"{COMPANY_SLUG}:sparrow",
        "family_name": "Sparrow",
        "family_url": URL_SPARROW,
        "product_url_scope": "exact_variant",
        "image": IMG["Sparrow"],
        "description": (
            "Sparrow is Drone Delivery Canada's Transport Canada–compliant electric "
            "multirotor cargo drone for short-range depot-to-depot delivery. It uses "
            "GPS-based navigation with the FLYTE flight-management system and supports "
            "land or drop-ship delivery options."
        ),
        "purpose": PURPOSE_SPARROW,
        "features": (
            "Electric rotorcraft-multirotor with 8 motors; GPS-based navigation; "
            "FLYTE-managed autonomous depot-to-depot operations; land and drop-ship "
            "delivery modes; Transport Canada compliant unmanned aircraft; max range "
            "20 km; max speed 60 kph; max payload 4 kg; MTOW 24.5–25 kg (OEM brochure "
            "24.5 kg / technology page 25 kg)."
        ),
        "payload_kg": 4.0,
        "weight_kg": 24.5,
        "speed": 60.0,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "logistics|healthcare|commercial|oil-gas",
        "use_keys": "delivery|logistics|item-delivery|transport|medical-assistance",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_MULTI,
        "manufacturer_country_code": CA,
        "videos": [YT_HOSPITAL, YT_COMPANY, YT_NEXT_SPARROW],
        "information_source_urls": [URL_SPARROW, URL_TECH, URL_BROCHURE],
        "notes_force": (
            "[AI Research] OEM specs from technology/#sparrow + 2022 fleet brochure: "
            "payload 4 kg, speed 60 kph, range 20 km, MTOW 24.5 kg (brochure) / 25 kg "
            "(technology). Hero: OEM Sparrow.png runway photo (distinct md5). "
            "Renamed from 'Sparrow (Drone Delivery Canada)'."
        ),
        "source_note": f"{URL_SPARROW}; {URL_BROCHURE}",
    },
    5104: {
        "name": "Canary",
        "model_name": "Canary",
        "variant_code": "Canary",
        "variant_label": "Canary RPA",
        "url": URL_CANARY,
        "family_key": f"{COMPANY_SLUG}:canary",
        "family_name": "Canary",
        "family_url": URL_CANARY,
        "product_url_scope": "exact_variant",
        "image": IMG["Canary"],
        "description": (
            "Canary is Drone Delivery Canada's next-generation Sparrow-class electric "
            "rotorcraft RPA with parachute recovery, touchless cargo drop, and "
            "Transport Canada acceptance for flight over people. It is managed through "
            "the FLYTE system for short-range autonomous cargo missions."
        ),
        "purpose": PURPOSE_CANARY,
        "features": (
            "Next-generation Sparrow-class electric rotorcraft; 8 electric motors; "
            "GPS-based navigation; integrated parachute recovery system; touchless "
            "cargo drop; smart-battery architecture; FLYTE real-time monitoring; "
            "Transport Canada flight-over-people declaration accepted; max range "
            "20 km; max payload 4.5 kg; MTOW 25 kg; max speed cited 80 kph on fleet "
            "brochure and Canary articles (technology table lists 72 kph)."
        ),
        "payload_kg": 4.5,
        "weight_kg": 25.0,
        "speed": 80.0,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "logistics|healthcare|commercial|consumer",
        "use_keys": "delivery|logistics|item-delivery|transport|medical-assistance",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_MULTI,
        "manufacturer_country_code": CA,
        "videos": [YT_CANARY_FLY, YT_CANARY_INTRO, YT_NEXT_SPARROW, YT_COMPANY],
        "information_source_urls": [
            URL_CANARY,
            URL_CANARY_ARTICLE,
            URL_CANARY_OVER_PEOPLE,
            URL_BROCHURE,
        ],
        "notes_force": (
            "[AI Research] OEM specs from technology/#canary (payload 4.5 kg, MTOW 25 kg, "
            "range 20 km) + Canary articles/brochure for 80 kph (tech table 72 kph noted). "
            "Hero: OEM Canary.png field photo (distinct md5)."
        ),
        "source_note": f"{URL_CANARY}; {URL_CANARY_ARTICLE}; {URL_BROCHURE}",
    },
    5105: {
        "name": "Robin XL",
        "model_name": "Robin XL",
        "variant_code": "Robin XL",
        "variant_label": "Robin XL",
        "url": URL_LANDING,
        "family_key": f"{COMPANY_SLUG}:robin-xl",
        "family_name": "Robin XL",
        "family_url": URL_LANDING,
        "product_url_scope": "exact_variant",
        "image": IMG["Robin XL"],
        "description": (
            "Robin XL is Drone Delivery Canada's mid-size electric VTOL / fixed-wing "
            "cargo drone for longer routes and harsher climates. It supports temperature-"
            "controlled internal cargo, an integrated parachute system, and optional "
            "automatic cargo deployment with the DroneSpot and FLYTE stack."
        ),
        "purpose": PURPOSE_ROBIN,
        "features": (
            "Electric combination VTOL / fixed-wing airframe; GPS-based navigation; "
            "integrated parachute system; temperature-controlled internal cargo; "
            "optional automatic / touchless cargo deployment; designed for harsher "
            "climates than Sparrow; FLYTE + DroneSpot depot integration; max range "
            "60 km; max speed 105 kph (landing-page fleet); max payload 11.3 kg. "
            "OEM MDA states development was paused July 2021 in favor of Condor/Canary, "
            "with possible future resume."
        ),
        "payload_kg": 11.3,
        "speed": 105.0,
        "availability_status_key": "announced",
        "movement_type_keys": "flying|aerial|hybrid",
        "industry_keys": "logistics|healthcare|commercial|oil-gas|government",
        "use_keys": "delivery|logistics|item-delivery|transport|medical-assistance",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_ROBIN,
        "manufacturer_country_code": CA,
        "videos": [YT_ROBIN, YT_COMPANY],
        "information_source_urls": [
            URL_LANDING,
            URL_ROBIN_PRESS,
            URL_MDA_2022,
            URL_BROCHURE,
        ],
        "notes_force": (
            "[AI Research] Specs from landing-page fleet + Robin XL press + FY2022 MDA: "
            "payload 11.3 kg, range 60 km, speed 105 kph (landing). No OEM MTOW cited — "
            "weight left blank. Availability=announced (development paused Jul 2021). "
            "URL preferred landing fleet page over press-only URL. Hero: OEM Robin-XL.png."
        ),
        "source_note": f"{URL_LANDING}; {URL_ROBIN_PRESS}; {URL_MDA_2022}",
    },
    5106: {
        "name": "Condor",
        "model_name": "Condor",
        "variant_code": "Condor",
        "variant_label": "Condor",
        "url": URL_LANDING,
        "family_key": f"{COMPANY_SLUG}:condor",
        "family_name": "Condor",
        "family_url": URL_LANDING,
        "product_url_scope": "exact_variant",
        "image": IMG["Condor"],
        "description": (
            "Condor is Drone Delivery Canada's heavy-lift unmanned helicopter for "
            "long-range cargo logistics. A two-stroke gasoline powerplant and GPS-based "
            "navigation support depot-to-depot missions monitored through FLYTE, aimed at "
            "remote and industrial supply routes."
        ),
        "purpose": PURPOSE_CONDOR,
        "features": (
            "Unmanned helicopter airframe; 2-stroke gasoline powerplant; GPS-based "
            "navigation; FLYTE-managed operations; heavy-lift long-range cargo role for "
            "remote/industrial routes; max range 200 km; max speed 120 kph; max payload "
            "180 kg; MTOW 476 kg (OEM fleet brochure + FY2022 MDA)."
        ),
        "payload_kg": 180.0,
        "weight_kg": 476.0,
        "speed": 120.0,
        "availability_status_key": "announced",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "logistics|oil-gas|commercial|government|industrial",
        "use_keys": "delivery|logistics|heavy-lifting|transport|material-transport",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_CONDOR,
        "manufacturer_country_code": CA,
        "videos": [YT_CONDOR, YT_CONDOR_LAUNCH, YT_CONDOR_TEASER, YT_COMPANY],
        "information_source_urls": [
            URL_LANDING,
            URL_BROCHURE,
            URL_MDA_2022,
            URL_CONDOR_PRESS,
        ],
        "notes_force": (
            "[AI Research] Specs from 2022 fleet brochure + FY2022 MDA: payload 180 kg, "
            "range 200 km, speed 120 kph, MTOW 476 kg. Availability=announced (OEM "
            "development/integration per MDA; not listed on live technology page). "
            "URL preferred landing fleet page over press-only URL. Hero: OEM Condor.png."
        ),
        "source_note": f"{URL_LANDING}; {URL_BROCHURE}; {URL_MDA_2022}",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Drone Delivery Canada company 1509")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--skip-hero-check", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
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
        seen_hashes: dict[str, str] = {}
        for name, url in IMG.items():
            md5 = verify_hero(name, url)
            if md5 in seen_hashes:
                raise RuntimeError(f"hash collision {name} vs {seen_hashes[md5]}")
            seen_hashes[md5] = name
            print(f"  OK {name} md5={md5} bytes-checked")

    targets = []
    for rid, fix in ROBOT_FIXES.items():
        if args.only and rid not in args.only:
            continue
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        row = build_row(fix, tags=tags)
        if len(row.get("features") or "") < 40:
            print(f"ERROR {rid}: features too short", file=sys.stderr)
            return 1
        if not row.get("family_key"):
            print(f"ERROR {rid}: missing family_key", file=sys.stderr)
            return 1
        if not row.get("image"):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: payload={row.get('payload_kg')} "
            f"speed={row.get('speed')} weight={row.get('weight_kg')} "
            f"fam={row.get('family_key')} avail={row.get('availability_status_key')} "
            f"vids={len(row.get('video_urls') or [])} tags={tags}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "ddc-1509-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "payload_kg": t["row"].get("payload_kg"),
                    "speed": t["row"].get("speed"),
                    "weight_kg": t["row"].get("weight_kg"),
                    "family_key": t["row"].get("family_key"),
                    "image": (t["row"].get("image") or "")[:120],
                    "availability": t["row"].get("availability_status_key"),
                    "url": t["row"].get("url"),
                }
                for t in targets
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not targets:
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media --verify-cdn")
        return 0

    patch_company(client)

    tmp = Path(tempfile.mkdtemp(prefix="ddc-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    imported: list[int] = []
    for item in targets:
        rid = item["id"]
        row = item["row"]
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        fpath = tmp / f"{slugify_robot_name(str(item['name']))}-{rid}.json"
        fpath.write_text(json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            result = client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=False,
                replace_media=True,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            continue
        created = int(result.get("created_count") or 0)
        if created:
            print(f"IMPORT FAIL {rid}: unexpected created_count={created} {result}", file=sys.stderr)
            continue
        err = int(result.get("error_count") or 0)
        if err:
            print(f"IMPORT FAIL {rid}: {result}", file=sys.stderr)
        else:
            imported.append(rid)
            patch_typed(client, rid, item["fix"])
            notes = item["fix"].get("notes_force")
            if notes:
                try:
                    client._patch(f"robots/robots/{rid}/", {"notes": notes})
                except Exception as exc:
                    print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  imported {rid}: {result.get('results')}")

    copy_stats = None
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        copy_stats = {"ok": ok, "fail": fail, "ids": imported}
        print(f"copy-media ok={ok} fail={fail}")

    if args.verify_cdn and imported:
        rc = subprocess.call(
            [sys.executable, str(_RESEARCH_DIR / "verify_cdn_images.py"), "--company-id", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )
        if rc != 0:
            print("CDN verify FAILED", file=sys.stderr)
            return rc

    if args.mark_done and imported:
        done_path = _RESEARCH_DIR / "state" / "content_queue_done.json"
        done: dict[str, Any] = {}
        if done_path.is_file():
            done = json.loads(done_path.read_text(encoding="utf-8"))
        done[str(COMPANY_ID)] = {
            "name": COMPANY_NAME,
            "at": time.strftime("%Y-%m-%d"),
            "robots": imported,
        }
        done_path.write_text(json.dumps(done, indent=2) + "\n", encoding="utf-8")
        print(f"marked done in {done_path}")

    print("totals", totals, "copy", copy_stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
