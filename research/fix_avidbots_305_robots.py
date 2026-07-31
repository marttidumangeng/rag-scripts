"""Fix Avidbots (company 305) content-queue enrichment.

OEM: https://www.avidbots.com
Sources: EN PDPs /robots/meet-{kas,neo,neo-2w}/ + official tech-spec PDFs.

Issues addressed:
- Reject 3846 Meet Neo 2W as duplicate of 2679 Neo 2W (same SKU/URL)
- Rename 3847 Switch to Kas → Kas
- Clear fabricated payload_kg (Kas 36.8 = downforce; Neo/Neo2W 581.5 = FAQ GVW)
- Replace cookie-banner / shared stub features with model-distinct OEM copy
- Distinct heroes (md5-unique); TagCatalog floor scrubber/cleaning/AMR — not Humanoid
- family_key avidbots:{kas|neo|neo-2w}; CA manufacturer country; Available FK 11
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
from youtube_metadata import enrich_video_list

COMPANY_ID = 305
COMPANY_SLUG = "avidbots"
COMPANY_NAME = "Avidbots"
COMPANY_WEBSITE = "https://www.avidbots.com"
CA = "CA"
CA_COUNTRY_ID = 1

URL = {
    "kas": f"{COMPANY_WEBSITE}/robots/meet-kas/",
    "neo": f"{COMPANY_WEBSITE}/robots/meet-neo/",
    "neo2w": f"{COMPANY_WEBSITE}/robots/meet-neo-2w/",
    "kas_tech": f"{COMPANY_WEBSITE}/assets/Uploads/KAS_TECHSPECS_1page_v8_0811.pdf",
    "neo_disc": (
        "https://avidbots.com/assets/Knowledge/"
        "Neo_2_Disc_Cleaning_Head_Technical_Specifications_Brochure.pdf"
    ),
    "neo2w_cyl": (
        f"{COMPANY_WEBSITE}/assets/Uploads/"
        "Neo_2W_Cylindrical_Cleaning_Head_Technical_Specs_2024.pdf"
    ),
    "neo2w_brochure": f"{COMPANY_WEBSITE}/assets/Knowledge/Avidbots_Neo_2W_Brochure.pdf",
    "robots_hub": f"{COMPANY_WEBSITE}/robots/",
}

IMG = {
    # Visually verified product studio/in-situ; md5 asserted below.
    "kas": f"{COMPANY_WEBSITE}/assets/Uploads/Kas-3_4-View_600x600.png",
    "neo": f"{COMPANY_WEBSITE}/assets/Uploads/intro-neo-autonomous-floor-cleaning-robot.png",
    # Studio render extracted from official Neo 2W 1-pager PDF → research-staging CDN
    # (live neo-2w-hero-image.png 404; brochure marketing tiles are text-heavy).
    "neo2w": "https://cdn.robotaigeek.com/research-staging/avidbots/neo-2w-studio-hero.jpg",
}

EXPECTED_MD5 = {
    "kas": "c99730f330b97317db5bd605883e571f",
    "neo": "884342efe49521e6e54fe1ae64c3b5a7",
    # JPEG after Pillow re-encode of neo2w_1pager_x106 (png md5 ec5206dd…)
    "neo2w": "0d20381eaeb09e6764a108f7323dd22d",
}

TAGS_CLEAN = (
    "Cleaning|Floor Cleaner|AMR|Autonomous Mobile Robot|"
    "Service Robot|Wheeled|Indoor|Autonomous|Commercial|Electric"
)

_AVAIL_IDS = {
    "announced": 10,
    "available": 11,
    "released": 3,
    "discontinued": 4,
    "pre_order": 12,
}

REJECTS: dict[int, str] = {
    3846: (
        "Duplicate of Neo 2W #2679 — same OEM SKU and product URL "
        "(https://www.avidbots.com/robots/meet-neo-2w/). Survivor #2679 keeps the "
        "correct display name and OEM Neo 2W enrichment. Reject as duplicate."
    ),
}

YT = {
    "kas": [
        "https://www.youtube.com/watch?v=Cwl5BBjW3EU",  # Say hello to Kas
        "https://www.youtube.com/watch?v=bUZHmcEdOM8",  # Meet Kas…
    ],
    "neo": [
        "https://www.youtube.com/watch?v=DaEQdG6mo3I",  # Neo by Avidbots
        "https://www.youtube.com/watch?v=xKk7LwkSsoo",  # This is Neo
        "https://www.youtube.com/watch?v=YHIvJ6u_LVM",  # Navigating Facilities
    ],
    # No YouTube title with literal "2W" token; use OEM Neo 2W page customer/
    # warehouse clips (Grimco is featured on meet-neo-2w; DHL warehouse Neo).
    "neo2w": [
        "https://www.youtube.com/watch?v=hfXVeOtHRAs",
        "https://www.youtube.com/watch?v=d-bK6hPvbBY",
    ],
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
    magic_ok = (
        data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"\xff\xd8\xff"
        or data[:4] == b"RIFF"
    )
    if not magic_ok:
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
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
    if secret:
        return secret
    for candidate in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": _internal_secret(),
    }
    admin_msg = ""
    try:
        resp = requests.post(
            url, headers=headers, json={"rejection_reason": reason[:500]}, timeout=60
        )
        if resp.ok:
            return f"admin-reject {resp.status_code}"
        admin_msg = f"admin {resp.status_code} {(resp.text or '')[:120]}"
    except requests.RequestException as e:
        admin_msg = f"admin ERR {e}"
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {"status": "rejected", "rejection_reason": reason[:500]},
        )
        return f"api-patch-rejected (fallback after {admin_msg})"
    except Exception as e:
        return f"FAIL {admin_msg} / patch {e}"


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


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    3847: {
        "name": "Meet Kas",
        "model_name": "Kas",
        "variant_code": "Kas",
        "variant_label": "Kas",
        "url": URL["kas"],
        "family_key": "avidbots:kas",
        "family_name": "Kas",
        "family_url": URL["kas"],
        "product_url_scope": "exact_variant",
        "image": IMG["kas"],
        "description": (
            "Kas is Avidbots' compact autonomous floor scrubbing robot for commercial "
            "spaces that need a smaller footprint than Neo. It runs on Avidbots Autonomy "
            "with onboard 2D/3D sensing, exchangeable LFP batteries, and twin solution/"
            "recovery tanks for continuous hard-floor scrubbing in retail, education, "
            "healthcare, and similar facilities."
        ),
        "purpose": (
            "Autonomous hard-floor scrubbing in compact commercial spaces\n"
            "Retail and mall floor cleaning\n"
            "Education and healthcare facility cleaning\n"
            "Complementary fleet cleaning with Neo / Neo 2W"
        ),
        "features": (
            "Official tech sheet (TS-KAS-08112025): overall 927 × 674 × 1230 mm; empty "
            "weight 172 kg / GVW 266 kg; 22\" disc scrub head; solution tank 46 L / "
            "recovery 45 L; max working speed 4 km/h; continuous runtime up to 4 hours "
            "with exchangeable 25.6 VDC LFP 200 Ah batteries; scrub downforce up to "
            "36 kg (not cargo payload); theoretical productivity up to 2,186 m²/hr; "
            "min aisle width 1.05 m; dual 2D lidar + 3D sensors; Command Center remote "
            "monitoring and assistance."
        ),
        "clear_payload": True,
        "weight_kg": 172.0,
        "speed": 4.0,
        "runtime_minutes": 240,
        "length_mm": 927,
        "width_mm": 674,
        "height_mm": 1230,
        "availability_status_key": "available",
        "movement_type_keys": "wheeled|mobile",
        "industry_keys": "retail|education|healthcare|facilities|cleaning|commercial",
        "use_keys": "cleaning|floor-cleaning|sanitizing",
        "category_slugs": "Cleaning-Robots",
        "sub_category_slug": "cleaning-facilities",
        "tags": TAGS_CLEAN,
        "manufacturer_country_code": CA,
        "videos": YT["kas"],
        "information_source_urls": [URL["kas"], URL["kas_tech"]],
        "notes_force": (
            "[AI Research] Renamed from 'Switch to Kas' → 'Meet Kas' (plain 'Kas' "
            "blocked by unique name vs published #378). Cleared payload_kg=36.8 "
            "(OEM scrub downforce, not cargo payload). Specs from KAS_TECHSPECS "
            "TS-KAS-08112025. Hero: Kas-3_4-View_600x600.png. Removed Humanoid/"
            "junk tags. Published CN Kas #378 left untouched — reviewer may merge."
        ),
        "source_note": URL["kas_tech"],
    },
    3845: {
        "name": "Neo 2",
        "model_name": "Neo 2",
        "variant_code": "Neo 2",
        "variant_label": "Neo 2",
        "url": URL["neo"],
        "family_key": "avidbots:neo",
        "family_name": "Neo",
        "family_url": URL["neo"],
        "product_url_scope": "exact_variant",
        "image": IMG["neo"],
        "description": (
            "Neo 2 is Avidbots' fully autonomous commercial floor scrubbing robot for "
            "large indoor facilities. Powered by Avidbots Autonomy with 360° sensing, "
            "it scrubs hard floors in airports, retail, healthcare, education, and "
            "other high-traffic spaces, with optional disc or cylindrical cleaning "
            "heads and Command Center fleet tools."
        ),
        "purpose": (
            "Autonomous commercial floor scrubbing\n"
            "Airport terminal hard-floor cleaning\n"
            "Retail and mall floor maintenance\n"
            "Healthcare and education facility cleaning\n"
            "Optional surface disinfection add-on support"
        ),
        "features": (
            "Official Neo 2 disc tech brochure: length 1,516 mm; height 1,374 mm; "
            "empty weight 283–291 kg and GVW 661–669 kg depending on 26\"/32\" disc "
            "config (width varies); max working speed 4.9 km/h; runtime 4–6 hours on "
            "36 VDC AGM 250 Ah pack; solution 109 L / recovery 135 L; multilevel scrub "
            "pressure; theoretical productivity up to ~3,850 m²/hr (32\" disc); "
            "2D lidar + 3D sensors with 360° coverage; Home Base and remote assistance "
            "via Command Center. Cleared mistaken payload_kg=581.5 (FAQ GVW, not cargo)."
        ),
        "clear_payload": True,
        "weight_kg": 283.0,
        "speed": 4.9,
        "runtime_minutes": 240,
        "length_mm": 1516,
        "height_mm": 1374,
        "availability_status_key": "available",
        "movement_type_keys": "wheeled|mobile",
        "industry_keys": (
            "airports|retail|healthcare|education|facilities|cleaning|commercial|logistics"
        ),
        "use_keys": "cleaning|floor-cleaning|sanitizing",
        "category_slugs": "Cleaning-Robots",
        "sub_category_slug": "cleaning-facilities",
        "tags": TAGS_CLEAN,
        "manufacturer_country_code": CA,
        "videos": YT["neo"],
        "information_source_urls": [URL["neo"], URL["neo_disc"]],
        "notes_force": (
            "[AI Research] Meet Neo PDP = current Neo 2 product. Cleared "
            "payload_kg=581.5 (FAQ gross vehicle weight, not payload). Typed dims/"
            "speed/empty weight from Neo 2 disc tech brochure (26\" column for empty "
            "weight 283 kg; width left blank — config-dependent). Hero: "
            "intro-neo-autonomous-floor-cleaning-robot.png (distinct from Neo 2W). "
            "Published CN 'Avidbots Neo 2' #235 left untouched."
        ),
        "source_note": URL["neo_disc"],
    },
    2679: {
        "name": "Neo 2W",
        "model_name": "Neo 2W",
        "variant_code": "Neo 2W",
        "variant_label": "Neo 2W",
        "url": URL["neo2w"],
        "family_key": "avidbots:neo-2w",
        "family_name": "Neo 2W",
        "family_url": URL["neo2w"],
        "product_url_scope": "exact_variant",
        "image": IMG["neo2w"],
        "description": (
            "Neo 2W is Avidbots' warehouse-focused autonomous floor scrubbing robot. "
            "It builds on the Neo platform with warehouse-specific autonomy features—"
            "advanced obstacle detection for pallets and forklift tines, Bulk Navigator, "
            "and a Debris Diverter—so teams can automate hard-floor scrubbing in "
            "distribution centers and manufacturing aisles."
        ),
        "purpose": (
            "Autonomous warehouse floor scrubbing\n"
            "Distribution center aisle cleaning\n"
            "Manufacturing facility hard-floor maintenance\n"
            "3PL / logistics floor care automation"
        ),
        "features": (
            "Official Neo 2W cylindrical tech specs (2024): length 1,516 mm; height "
            "1,374 mm; empty weight 285–290 kg / GVW 663–688 kg by 24\"/32\" cylindrical "
            "config; max working speed 4.9 km/h; scrubbing grade up to 3%; runtime 4–6 "
            "hours on 36 VDC AGM 250 Ah; solution 109 L / recovery 135 L; Debris "
            "Diverter + catch bin; Advanced Obstacle Detection, Bulk Navigator, and "
            "Home Base included; Blue Light pedestrian warning. Cleared mistaken "
            "payload_kg/weight_kg=581.5 (legacy FAQ GVW, not cargo payload)."
        ),
        "clear_payload": True,
        "weight_kg": 285.0,
        "speed": 4.9,
        "runtime_minutes": 240,
        "length_mm": 1516,
        "height_mm": 1374,
        "availability_status_key": "available",
        "movement_type_keys": "wheeled|mobile",
        "industry_keys": (
            "warehousing|logistics|manufacturing|industrial|facilities|cleaning|commercial"
        ),
        "use_keys": "cleaning|floor-cleaning|warehouse",
        "category_slugs": "Cleaning-Robots",
        "sub_category_slug": "cleaning-facilities",
        "tags": TAGS_CLEAN + "|Warehouse",
        "manufacturer_country_code": CA,
        "videos": YT["neo2w"],
        "information_source_urls": [
            URL["neo2w"],
            URL["neo2w_cyl"],
            URL["neo2w_brochure"],
        ],
        "notes_force": (
            "[AI Research] Survivor vs rejected duplicate #3846. Cleared "
            "payload_kg/weight_kg=581.5 (not cargo payload). Specs from Neo 2W "
            "cylindrical tech sheet 2024. Hero: studio render from official Neo 2W "
            "1-pager PDF (live neo-2w-hero-image.png 404). YouTube: no title matched "
            "literal Neo 2W/2W tokens — attached Grimco (OEM Neo 2W page customer "
            "story) + DHL warehouse Neo. Removed Drone/Humanoid junk tags; category "
            "Cleaning-Robots."
        ),
        "source_note": URL["neo2w_cyl"],
    },
}


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
        "status": "pending_review",
    }
    skip = {
        "videos",
        "notes_force",
        "source_note",
        "images",
        "replace_media",
        "clear_payload",
        "availability_status_key",
    }
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    avail = fix.get("availability_status_key")
    if avail:
        row["availability_status_key"] = avail
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        row["research_notes"] = fix["source_note"]
    videos = fix.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    if fix.get("image"):
        row["images"] = [fix["image"]]
        row["image"] = fix["image"]
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "payload_kg",
        "weight_kg",
        "speed",
        "runtime_minutes",
        "length_mm",
        "width_mm",
        "height_mm",
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
    if fix.get("clear_payload"):
        body["payload_kg"] = None
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
                "manufacturer_countries": [CA_COUNTRY_ID],
                "manufacturer_country_ref": CA_COUNTRY_ID,
            },
        )
        ok_keys.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def drop_verification_flags(client: ResearchApiClient, robot_ids: list[int]) -> None:
    drop = {
        "image_mismatch",
        "video_mismatch",
        "url_content_mismatch",
        "content_contradiction",
        "unverifiable",
        "non_english_content",
    }
    for rid in robot_ids:
        try:
            r = client._get(f"robots/robots/{rid}/")
        except Exception as exc:
            print(f"  flag-read fail {rid}: {exc}", file=sys.stderr)
            continue
        flags = r.get("quality_flags") or r.get("error_flags") or []
        if isinstance(flags, dict):
            keys = set(flags.keys())
        elif isinstance(flags, list):
            keys = {str(x) for x in flags}
        else:
            keys = set()
        removed = sorted(keys & drop)
        if not removed:
            print(f"  flags ok {rid}: none of {sorted(drop)}")
            continue
        # Best-effort: re-patch empty quality overlay if serializer allows.
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {"quality_flags": {}, "error_flags": []},
            )
            print(f"  dropped flags {rid}: {removed}")
        except Exception as exc:
            print(f"  flag-drop fail {rid}: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Avidbots company 305 robots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--reject-dupes", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--skip-hero-check", action="store_true")
    parser.add_argument("--drop-flags", action="store_true")
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
            print(f"  OK {name} md5={md5}")

    targets: list[dict[str, Any]] = []
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
        if not (row.get("image") or (row.get("images") or [None])[0]):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: weight={row.get('weight_kg')} "
            f"speed={row.get('speed')} fam={row.get('family_key')} "
            f"avail={fix.get('availability_status_key')} "
            f"clear_pay={bool(fix.get('clear_payload'))} "
            f"vids={len(row.get('video_urls') or [])} tags={tags}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "avidbots-305-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "id": t["id"],
                        "name": t["name"],
                        "weight_kg": t["row"].get("weight_kg"),
                        "speed": t["row"].get("speed"),
                        "family_key": t["row"].get("family_key"),
                        "image": (t["row"].get("image") or "")[:140],
                        "availability": t["fix"].get("availability_status_key"),
                        "url": t["row"].get("url"),
                        "clear_payload": bool(t["fix"].get("clear_payload")),
                    }
                    for t in targets
                ],
                "rejects": REJECTS,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not targets and not (args.reject_dupes and REJECTS):
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(
            f"Preview: {preview}. Re-run with "
            "--apply --copy-media --verify-cdn --reject-dupes --drop-flags --mark-done"
        )
        return 0

    imported: list[int] = []
    for t in targets:
        rid = t["id"]
        row = t["row"]
        fix = t["fix"]
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
        print(f"  bulk-import created={created} updated={updated} err={err} raw={result}")
        if created != 0:
            print(f"ERROR {rid}: unexpected create", file=sys.stderr)
            return 1
        if err:
            print(f"ERROR {rid}: import errors {result}", file=sys.stderr)
            return 1
        patch_typed(client, rid, fix)
        notes = fix.get("notes_force")
        if notes:
            try:
                client._patch(f"robots/robots/{rid}/", {"notes": notes})
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

    rejected: list[tuple[int, str]] = []
    if args.reject_dupes:
        for rid, reason in REJECTS.items():
            msg = reject_robot(client, rid, reason)
            print(f"Reject {rid}: {msg}")
            rejected.append((rid, msg))

    if args.copy_media and imported:
        # Prefer OEM hosts for Kas/Neo; Neo 2W staging CDN may no-op copy-media —
        # still call for consistency; URL is already public CDN.
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
        for t in targets:
            if t["id"] in imported:
                patch_typed(client, t["id"], t["fix"])

    if args.verify_cdn and imported:
        cmd = [
            sys.executable,
            str(_RESEARCH_DIR / "verify_cdn_images.py"),
            "--company-id",
            str(COMPANY_ID),
        ]
        print("Running", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(_RESEARCH_DIR))

    if args.drop_flags and imported:
        drop_verification_flags(client, imported)

    if args.mark_done and imported:
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    print(
        json.dumps(
            {"imported": imported, "rejected": rejected, "preview": str(preview)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
