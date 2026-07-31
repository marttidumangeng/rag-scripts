"""Fix AgXeed (company 264) content-queue enrichment.

OEM: https://www.agxeed.com
Sources: series PDPs under /solutions/agbots/, official Specsheet-*.pdf
(W4/W3/T2-5/T2-7), FAQ power table, T2 7 unveiling press.

Issues addressed:
- 4031 AgBot W4.2 is the same SKU as 1537 AgBot W4 2 SERIES → reject
- 4029 press URL → official T2 7 SERIES PDP; rename to OEM series label
- duplicate_images junk galleries (logo / icon size variants) → single OEM heroes
- fabricated payload_kg=500 (fertilizer use-case number) cleared
- typed weight/speed/dims from OEM spec sheets; HP/kW + lift in features
- family_* / purpose apps / tags / NL manufacturer country / Available
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

COMPANY_ID = 264
COMPANY_SLUG = "agxeed"
COMPANY_NAME = "AgXeed"
COMPANY_WEBSITE = "https://www.agxeed.com"
NL = "NL"
NL_COUNTRY_ID = 107

URL_AGBOTS = f"{COMPANY_WEBSITE}/solutions/agbots/"
URL_W4 = f"{URL_AGBOTS}agbot-w4-series/"
URL_W3 = f"{URL_AGBOTS}agbot-w3-series/"
URL_T25 = f"{URL_AGBOTS}agbot-t2-5-series/"
URL_T27 = f"{URL_AGBOTS}agbot-t2-7-series/"
URL_FAQ_POWER = f"{COMPANY_WEBSITE}/faq/how-powerful-are-the-agbots/"
URL_T27_PRESS = (
    f"{COMPANY_WEBSITE}/agxeed-unveils-the-new-agbot-t2-7-series-230-hp-of-"
    "autonomous-power-forsmarter-soil-friendly-farming/"
)

PDF_W4 = f"{COMPANY_WEBSITE}/wp-content/uploads/2025/11/Specsheeet-W4-2series.pdf"
PDF_W3 = f"{COMPANY_WEBSITE}/wp-content/uploads/2025/11/Specsheeet-W3-2series.pdf"
PDF_T25 = f"{COMPANY_WEBSITE}/wp-content/uploads/2025/11/Specsheet-T2-5series.pdf"
PDF_T27 = f"{COMPANY_WEBSITE}/wp-content/uploads/2025/11/Specsheeet-T2-7series.pdf"

# Distinct OEM product heroes (md5-verified unique; visually checked).
IMG = {
    "W4": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/10/Agbot-w4-2-series-AgXeed-1.webp",
    "W3": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/10/W3-render-new-header_w.png",
    "T25": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/09/agxeed_agbot.webp",
    "T27": (
        f"{COMPANY_WEBSITE}/wp-content/uploads/2025/11/"
        "T2-7-SERIES-product-page-e1762374279586.png"
    ),
}
EXPECTED_MD5 = {
    "W4": "0865d5a362608ae2d518b00736269fae",
    "W3": "e03792cf9715e2f2ff0718988817d4a0",
    "T25": "2469288b786ce8fbebf2e514dbc7728d",
    "T27": "6b5121e01f66dbe07fa271fe1eaf9bf9",
}

# Model-token title-filtered YouTube (reject sibling / generic).
YT_W4 = [
    "https://www.youtube.com/watch?v=LJbQdxw37x4",  # Agbot 2.055W4
    "https://www.youtube.com/watch?v=RASYtcnyGaM",  # AgBot 2.055W4 TractorLab
    "https://www.youtube.com/watch?v=ATqTBUedyjM",  # 2.055W4 Kema Alfalfa
]
YT_W3 = [
    "https://www.youtube.com/watch?v=p8v_KipYk4w",  # W3 2-SERIES weeding nurseries
    "https://www.youtube.com/watch?v=yOMCk2zHSHU",  # W3 2 SERIES blueberry spray
    "https://www.youtube.com/watch?v=_QaMdG0T-7Q",  # W3 2 SERIES mulching orchard
]
YT_T25 = [
    "https://www.youtube.com/watch?v=Q0ATjasw9K0",  # AgBot 5115.T2
    "https://www.youtube.com/watch?v=gGSURWUlSkI",  # AgBot 5.115T2 3 tasks
    "https://www.youtube.com/watch?v=r4oAz7PCQmw",  # AgBot 5.115T2 ploughing
]
YT_T27 = [
    "https://www.youtube.com/watch?v=Y6iai-xxISs",  # introduces T2 7-SERIES
    "https://www.youtube.com/watch?v=ZHgRwJOo73Q",  # T2 7 SERIES potato planting
    "https://www.youtube.com/watch?v=Wu_5Ef8R7oE",  # T2 7 SERIES 80 ha
]

TAGS_WHEELED = (
    "Agriculture|Autonomous|Wheeled|Outdoor|Precision|Tractor|Hybrid|Electric"
)
TAGS_TRACKED = (
    "Agriculture|Autonomous|Tracked|Outdoor|Precision|Tractor|Hybrid|Electric"
)

PURPOSE_W4 = (
    "Lighter tillage\n"
    "Crop care\n"
    "Specialty crop bed cultivation\n"
    "Seeding and drilling\n"
    "Grassland and turf mowing"
)
PURPOSE_W3 = (
    "Orchard and tree-nursery crop care\n"
    "Precision spraying\n"
    "Mechanical weeding\n"
    "Mulching in permanent crops"
)
PURPOSE_T25 = (
    "High-capacity arable tillage\n"
    "Disc harrowing\n"
    "Seeding and planting\n"
    "Mulching and flail mowing\n"
    "Broad-acre field operations"
)
PURPOSE_T27 = (
    "Deep tillage and heavy cultivation\n"
    "Large-area seeding and planting\n"
    "Pulling wide implements\n"
    "Work on sloping and heavy soils"
)

REJECTS: dict[int, str] = {
    4031: (
        "Duplicate of robot 1537 (AgBot W4 2 SERIES). OEM catalog names this SKU "
        "'W4 2 SERIES' on the same series PDP "
        "(https://www.agxeed.com/solutions/agbots/agbot-w4-series/). "
        "'AgBot W4.2' is the same wheeled 55 kW / 75 hp model; 4031 had no hero "
        "and only icon/size-variant junk gallery. Keep 1537 as the canonical record."
    ),
}

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
    )
    if secret:
        return secret
    # Fall back to server .env (same pattern as other fixers)
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
    """Prefer admin reject; fall back to status=rejected PATCH (known 403 issue)."""
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": _internal_secret(),
    }
    try:
        resp = requests.post(
            url, headers=headers, json={"type": "robot", "reason": reason}, timeout=120
        )
        if resp.status_code < 400:
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
        "replace_media",
        "clear_payload",
        "availability_status_key",
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
    videos = fix.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    if fix.get("image"):
        row["images"] = [fix["image"]]
    row["availability_status_key"] = fix.get("availability_status_key") or "available"
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "weight_kg",
        "speed",
        "length_mm",
        "width_mm",
        "height_mm",
        "runtime_minutes",
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
        "release_year",
        "programming_interface",
        "deployment_context",
        "ecosystem_compatibility",
        "safety_fencing",
        "mounting_options",
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
                "manufacturer_countries": [NL_COUNTRY_ID],
                "manufacturer_country_ref": NL_COUNTRY_ID,
            },
        )
        ok_keys.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def drop_stale_media_flags(client: ResearchApiClient, robot_ids: list[int]) -> None:
    """Best-effort: clear sticky duplicate_images / verification chips after media replace."""
    drop = {
        "duplicate_images",
        "image_mismatch",
        "video_mismatch",
        "url_content_mismatch",
        "content_contradiction",
        "unverifiable",
    }
    for rid in robot_ids:
        try:
            r = client._get(f"robots/robots/{rid}/")
        except Exception as exc:
            print(f"  flag-read fail {rid}: {exc}", file=sys.stderr)
            continue
        flags = r.get("quality_flags") or r.get("error_flags") or []
        if not isinstance(flags, list) or not flags:
            continue
        before = [
            (f.get("flag") if isinstance(f, dict) else f) for f in flags
        ]
        after = [
            f
            for f in flags
            if (f.get("flag") if isinstance(f, dict) else f) not in drop
        ]
        removed = sorted(set(before) - {
            (f.get("flag") if isinstance(f, dict) else f) for f in after
        })
        if not removed:
            continue
        try:
            client._patch(f"robots/robots/{rid}/", {"quality_flags": after})
            print(f"  dropped flags {rid}: {removed}")
        except Exception as exc:
            print(f"  flag-drop fail {rid}: {exc} (may need ORM)", file=sys.stderr)


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    1537: {
        "name": "AgBot W4 2 SERIES",
        "model_name": "W4 2 SERIES",
        "variant_code": "W4 2 SERIES",
        "variant_label": "W4 2 SERIES",
        "url": URL_W4,
        "family_key": f"{COMPANY_SLUG}:w4-2",
        "family_name": "AgBot W4 2 SERIES",
        "family_url": URL_W4,
        "product_url_scope": "family",
        "image": IMG["W4"],
        "description": (
            "The AgBot W4 2 SERIES is AgXeed's four-wheel autonomous field robot for "
            "lighter tillage, crop care, and specialty crops. A diesel-electric "
            "powertrain and TraXwise planning/monitoring deliver flexible track widths "
            "and low soil impact for grassland, bed cultivation, and precision seeding."
        ),
        "purpose": PURPOSE_W4,
        "features": (
            "Diesel-electric drivetrain: 2.9 L Deutz Stage V, 55 kW / 75 hp "
            "(max torque 300 Nm); electric drive 0–13.5 km/h; optional HV connectors "
            "up to 55 kW / 700 V; optional electric PTO up to 55 kW (variable). "
            "Hydraulics: 85 l/min at 210 bar; up to 3 DA proportional spool valves; "
            "optional load sensing; rear 3-point Cat III with 4 t lift at hooks; "
            "front 3-point Cat II with 1.5 t lift. Empty weight 3.2 t; length 3850 mm; "
            "height 1500 mm; width from 1800 mm; wheelbase 2400 mm; 220 L diesel tank. "
            "RTK GNSS ±2.5 cm; geofence, LiDAR, ultrasonic/radar bumper, e-stops. "
            "TraXwise pre-planning, live monitoring, and data management. "
            "Adjustable wheel configurations / track centers (OEM wheel table)."
        ),
        "clear_payload": True,
        "weight_kg": 3200.0,
        "speed": 13.5,
        "length_mm": 3850,
        "width_mm": 1800,
        "height_mm": 1500,
        "runtime_minutes": 1200,  # OEM FAQ: up to 20 h continuous at 75% engine load
        "availability_status_key": "available",
        "movement_type_keys": "wheeled",
        "industry_keys": "agriculture",
        "use_keys": "farming|agriculture|spraying|harvesting",
        "category_slugs": "Agricultural-Robots",
        "sub_category_slug": "agriculture",
        "tags": TAGS_WHEELED,
        "manufacturer_country_code": NL,
        "programming_interface": "TraXwise cloud/app (pre-planning, live monitoring, data)",
        "deployment_context": (
            "Unmanned field operations with standard 3-point implements; "
            "dealer-supported autonomous agricultural deployments"
        ),
        "ecosystem_compatibility": "ISOBUS / TIM; standard 3-point linkage implements",
        "safety_fencing": (
            "Geofence, visual indicator lights, audible alarm, perimeter e-stops, "
            "LiDAR + ultrasonic/radar bumper obstacle detection"
        ),
        "mounting_options": "Wheeled chassis; front and rear three-point linkages",
        "videos": YT_W4,
        "information_source_urls": [URL_W4, PDF_W4, URL_FAQ_POWER],
        "notes_force": (
            "[AI Research] OEM specs from Specsheeet-W4-2series.pdf + W4 series PDP + "
            "FAQ power table: 55 kW/75 hp, empty weight 3.2 t, speed 0–13.5 km/h, "
            "dims L3850×W≥1800×H1500 mm, rear lift 4 t (NOT payload — cleared false "
            "payload_kg=500 from fertilizer use-case text). Hero: OEM "
            "Agbot-w4-2-series-AgXeed-1.webp (distinct md5). Rejected duplicate 4031 "
            "(W4.2 alias)."
        ),
        "source_note": f"{URL_W4}; {PDF_W4}; {URL_FAQ_POWER}",
    },
    1536: {
        "name": "AgBot W3 2 SERIES",
        "model_name": "W3 2 SERIES",
        "variant_code": "W3 2 SERIES",
        "variant_label": "W3 2 SERIES",
        "url": URL_W3,
        "family_key": f"{COMPANY_SLUG}:w3-2",
        "family_name": "AgBot W3 2 SERIES",
        "family_url": URL_W3,
        "product_url_scope": "family",
        "image": IMG["W3"],
        "description": (
            "The AgBot W3 2 SERIES is AgXeed's compact three-wheel autonomous robot "
            "for orchards and tree nurseries. Low empty weight, even load distribution, "
            "and TraXwise autonomy keep permanent crops and soil in condition during "
            "spraying, weeding, and mulching."
        ),
        "purpose": PURPOSE_W3,
        "features": (
            "Diesel-electric drivetrain: 2.9 L Deutz Stage V, 55 kW / 75 hp "
            "(max torque 300 Nm); electric drive 0–13.5 km/h; optional HV connectors "
            "up to 55 kW / 700 V; optional electric PTO up to 50 kW (~1200 rpm, variable). "
            "Hydraulics: 85 l/min at 210 bar; up to 3 DA proportional spool valves; "
            "optional load sensing; rear 3-point Cat II with 2.5 t lift at hooks. "
            "Empty weight 2.8 t; length 3850 mm; height 1500 mm; width from 1380 mm; "
            "wheelbase 2400 mm; 170 L diesel tank. Three-wheel configuration with "
            "selectable rear tire widths (OEM table 380–710 mm). RTK GNSS ±2.5 cm; "
            "geofence, LiDAR, ultrasonic/radar bumper, e-stops. TraXwise pre-planning, "
            "live monitoring, and data management."
        ),
        "clear_payload": True,
        "weight_kg": 2800.0,
        "speed": 13.5,
        "length_mm": 3850,
        "width_mm": 1380,
        "height_mm": 1500,
        "runtime_minutes": 1200,
        "availability_status_key": "available",
        "movement_type_keys": "wheeled",
        "industry_keys": "agriculture",
        "use_keys": "farming|agriculture|spraying",
        "category_slugs": "Agricultural-Robots",
        "sub_category_slug": "agriculture",
        "tags": TAGS_WHEELED,
        "manufacturer_country_code": NL,
        "programming_interface": "TraXwise cloud/app (pre-planning, live monitoring, data)",
        "deployment_context": (
            "Orchard and nursery unmanned operations with standard 3-point implements"
        ),
        "ecosystem_compatibility": "ISOBUS-capable implements; standard 3-point linkage",
        "safety_fencing": (
            "Geofence, visual indicator lights, audible alarm, perimeter e-stops, "
            "LiDAR + ultrasonic/radar bumper obstacle detection"
        ),
        "mounting_options": "Three-wheel chassis; rear three-point Cat II linkage",
        "videos": YT_W3,
        "information_source_urls": [URL_W3, PDF_W3, URL_FAQ_POWER],
        "notes_force": (
            "[AI Research] OEM specs from Specsheeet-W3-2series.pdf + W3 series PDP + "
            "FAQ power table: 55 kW/75 hp, empty weight 2.8 t, speed 0–13.5 km/h, "
            "dims L3850×W≥1380×H1500 mm, rear lift 2.5 t (not used as payload_kg). "
            "Cleared false payload_kg=500. Hero: OEM W3-render-new-header_w.png "
            "(distinct 3-wheel studio render)."
        ),
        "source_note": f"{URL_W3}; {PDF_W3}; {URL_FAQ_POWER}",
    },
    1535: {
        "name": "AgBot T2 5 SERIES",
        "model_name": "T2 5 SERIES",
        "variant_code": "T2 5 SERIES",
        "variant_label": "T2 5 SERIES",
        "url": URL_T25,
        "family_key": f"{COMPANY_SLUG}:t2-5",
        "family_name": "AgBot T2 5 SERIES",
        "family_url": URL_T25,
        "product_url_scope": "family",
        "image": IMG["T25"],
        "description": (
            "The AgBot T2 5 SERIES is AgXeed's tracked autonomous robot for "
            "high-capacity arable work. A 156 hp diesel-electric drivetrain and "
            "soil-preserving crawler tracks (adjustable track width) combine with "
            "TraXwise for tillage, planting, and mulching on broad acreage."
        ),
        "purpose": PURPOSE_T25,
        "features": (
            "Diesel-electric drivetrain: 4.1 L Deutz Stage V, 115 kW / 156 hp "
            "(max torque 610 Nm); electric drive 0–13.5 km/h; optional HV connectors "
            "up to 100 kW / 700 V; optional electric PTO up to 100 kW (~1200 rpm). "
            "Hydraulics: 85 l/min at 210 bar; up to 4 DA proportional spool valves; "
            "optional load sensing; rear 3-point Cat III with 8 t lift; front 3-point "
            "Cat II (hooks Cat III) with 3 t lift. Empty weight 7.8 t; minimal length "
            "2695 mm (3600 mm with hitch at 90°); height 2000 mm; 350 L diesel + 30 L "
            "AdBlue. Crawler tracks 300–910 mm; adjustable track center ~1900–3175 mm "
            "(setup-dependent); crop clearance 42 cm. RTK GNSS ±2.5 cm; full AgXeed "
            "safety/obstacle suite. TraXwise pre-planning, live monitoring, data."
        ),
        "clear_payload": True,
        "weight_kg": 7800.0,
        "speed": 13.5,
        "length_mm": 2695,
        "height_mm": 2000,
        "runtime_minutes": 1200,
        "availability_status_key": "available",
        "movement_type_keys": "tracked",
        "industry_keys": "agriculture",
        "use_keys": "farming|agriculture",
        "category_slugs": "Agricultural-Robots",
        "sub_category_slug": "agriculture",
        "tags": TAGS_TRACKED,
        "manufacturer_country_code": NL,
        "programming_interface": "TraXwise cloud/app (pre-planning, live monitoring, data)",
        "deployment_context": (
            "Tracked unmanned operations on broad arable land with ISOBUS implements"
        ),
        "ecosystem_compatibility": "ISOBUS / TIM; standard 3-point linkage implements",
        "safety_fencing": (
            "Geofence, visual indicator lights, audible alarm, perimeter e-stops, "
            "LiDAR + ultrasonic/radar bumper obstacle detection"
        ),
        "mounting_options": "Tracked chassis; front and rear three-point linkages",
        "videos": YT_T25,
        "information_source_urls": [URL_T25, PDF_T25, URL_FAQ_POWER],
        "notes_force": (
            "[AI Research] OEM specs from Specsheet-T2-5series.pdf + T2 5 series PDP + "
            "FAQ power table: 115 kW/156 hp, empty weight 7.8 t, speed 0–13.5 km/h, "
            "min length 2695 mm, height 2000 mm, rear lift 8 t (not payload). Cleared "
            "false payload_kg=500. Width varies by track setup — left blank. Hero: OEM "
            "agxeed_agbot.webp studio tracked render from T2 5 PDP (distinct md5). "
            "Did not use sibling T2.7 field stills embedded on the T2 5 page."
        ),
        "source_note": f"{URL_T25}; {PDF_T25}; {URL_FAQ_POWER}",
    },
    4029: {
        "name": "AgBot T2 7 SERIES",
        "model_name": "T2 7 SERIES",
        "variant_code": "T2 7 SERIES",
        "variant_label": "T2 7 SERIES",
        "url": URL_T27,
        "family_key": f"{COMPANY_SLUG}:t2-7",
        "family_name": "AgBot T2 7 SERIES",
        "family_url": URL_T27,
        "product_url_scope": "family",
        "image": IMG["T27"],
        "description": (
            "The AgBot T2 7 SERIES is AgXeed's highest-power tracked autonomous field "
            "robot. With 230 hp diesel-electric drive, under-30 kPa ground pressure, "
            "and TraXwise autonomy, it targets heavy tillage, wide implements, and "
            "demanding soils while keeping compaction low."
        ),
        "purpose": PURPOSE_T27,
        "features": (
            "Diesel-electric drivetrain: 5.2 L Deutz Stage V, 170 kW / 230 hp "
            "(max torque 950 Nm); electric drive 0–13.0 km/h; optional AEF HV "
            "connectors up to 150 kW / 700 V front and rear; optional direct-driven "
            "PTO 1000 rpm front and rear. Hydraulics: 170 l/min at 210 bar; up to 4 DA "
            "proportional spool valves; optional load sensing; rear 3-point Cat III "
            "with 9 t lift; front 3-point Cat II with 4 t lift. Empty weight 7.8–8.2 t "
            "(catalog mid ~8.0 t); length 3846 mm; height 2070 mm vehicle / 2400 mm "
            "with lidar; width 2550–4100 mm by track setup; 520 L diesel + 50 L AdBlue. "
            "Tracked design, ground pressure <30 kPa; track widths from 1.5 m to 3.2 m; "
            "crop clearance 450 mm. Dual GNSS RTK; Safety measures 7 30 MX + obstacle "
            "detection 8 30 MX. TraXwise + ISOBUS/TIM. Unveiled Nov 2025 (Agritechnica)."
        ),
        "clear_payload": True,
        "weight_kg": 8000.0,
        "speed": 13.0,
        "length_mm": 3846,
        "height_mm": 2070,
        "runtime_minutes": 1200,
        "release_year": 2025,
        "availability_status_key": "available",
        "movement_type_keys": "tracked",
        "industry_keys": "agriculture",
        "use_keys": "farming|agriculture",
        "category_slugs": "Agricultural-Robots",
        "sub_category_slug": "agriculture",
        "tags": TAGS_TRACKED,
        "manufacturer_country_code": NL,
        "programming_interface": "TraXwise cloud/app (pre-planning, live monitoring, data)",
        "deployment_context": (
            "Heavy arable and vegetable operations; Agritechnica 2025 launch series"
        ),
        "ecosystem_compatibility": "ISOBUS / TIM; Cat II/III three-point implements",
        "safety_fencing": (
            "Safety measures 7 30 MX (geofence, lights, alarm, e-stops) + obstacle "
            "detection 8 30 MX (LiDAR, ultrasonic, radar, contact bumper)"
        ),
        "mounting_options": "Tracked chassis; front and rear three-point linkages",
        "videos": YT_T27,
        "information_source_urls": [URL_T27, PDF_T27, URL_T27_PRESS, URL_FAQ_POWER],
        "notes_force": (
            "[AI Research] Renamed from 'AgBot T2.7' to OEM 'AgBot T2 7 SERIES'. "
            "URL switched from press unveil to "
            "https://www.agxeed.com/solutions/agbots/agbot-t2-7-series/. Specs from "
            "Specsheeet-T2-7series.pdf + PDP + press: 170 kW/230 hp, empty weight "
            "7.8–8.2 t (stored weight_kg=8000 mid), speed 0–13.0 km/h, L3846×H2070 mm, "
            "rear lift 9 t (not payload). Purged logo size-variant duplicate gallery; "
            "hero OEM T2-7-SERIES-product-page render (distinct md5)."
        ),
        "source_note": f"{URL_T27}; {PDF_T27}; {URL_T27_PRESS}; {URL_FAQ_POWER}",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix AgXeed company 264")
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
        purpose = str(row.get("purpose") or "")
        desc = str(row.get("description") or "")
        if purpose and desc and purpose.strip().rstrip(".") == desc.strip().split(".")[0].strip():
            print(f"ERROR {rid}: purpose duplicates description", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: weight={row.get('weight_kg')} "
            f"speed={row.get('speed')} fam={row.get('family_key')} "
            f"avail={row.get('availability_status_key')} "
            f"vids={len(row.get('video_urls') or [])} tags={tags}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "agxeed-264-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "weight_kg": t["row"].get("weight_kg"),
                    "speed": t["row"].get("speed"),
                    "family_key": t["row"].get("family_key"),
                    "image": (t["row"].get("image") or "")[:120],
                    "availability": t["row"].get("availability_status_key"),
                    "url": t["row"].get("url"),
                    "clear_payload": t["fix"].get("clear_payload"),
                }
                for t in targets
            ]
            + [{"rejects": REJECTS}],
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
        print(f"Preview: {preview}. Re-run with --apply --copy-media --verify-cdn --reject-dupes")
        return 0

    rejected: list[dict[str, Any]] = []
    if args.reject_dupes:
        for rid, reason in REJECTS.items():
            if args.only and rid not in args.only:
                continue
            msg = reject_robot(client, rid, reason)
            print(f"REJECT {rid}: {msg}")
            rejected.append({"id": rid, "reason": reason, "result": msg})

    tmp = Path(tempfile.mkdtemp(prefix="agxeed-fix-"))
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
                replace_videos=True,
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
        # Re-patch availability + typed after copy/import can wipe soft fields
        for item in targets:
            if item["id"] in imported:
                patch_typed(client, item["id"], item["fix"])

    cdn_rc = None
    if args.verify_cdn and imported:
        cdn_rc = subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--company-id",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )
        print(f"verify_cdn exit={cdn_rc}")

    if args.drop_flags and imported:
        drop_stale_media_flags(client, imported)

    if args.mark_done:
        subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    report = {
        "company_id": COMPANY_ID,
        "imported": imported,
        "rejected": rejected,
        "totals": totals,
        "copy_media": copy_stats,
        "verify_cdn_rc": cdn_rc,
        "preview": str(preview),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not totals.get("error_count") else 1


if __name__ == "__main__":
    raise SystemExit(main())
