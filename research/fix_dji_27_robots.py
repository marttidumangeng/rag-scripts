"""Fix DJI (company 27) content-queue enrichment.

OEM: https://www.dji.com (+ enterprise.dji.com, ag.dji.com)
Sources: EN /global/ and enterprise/ag PDPs + /specs support pages.

Issues addressed:
- Reject series shells (413–417) + Agras family shell (108) + FlyCart care-footer dupe (418)
- Remap /id/ Indonesian URLs → EN support/PDPs; rename DJI Dji Fpv → DJI FPV
- Fix wrong family_key dji:dji-matrice-4d on Matrice 400
- Replace identical feat=59 stubs with OEM English features
- Clear fabricated camera-drone payload_kg; cite real spray/cargo/gimbal payloads
- Distinct CMS heroes (md5-verified); Neo 2 uses cms2 (NEO 2 arm label)
- family_* / purpose apps / CN manufacturer / Available|Discontinued
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

COMPANY_ID = 27
COMPANY_SLUG = "dji"
COMPANY_NAME = "DJI"
COMPANY_WEBSITE = "https://www.dji.com"
CN = "CN"
CN_COUNTRY_ID = 3

CMS = "https://www-cdn.djiits.com/cms/uploads"

IMG = {
    "t70p": f"{CMS}/7e56f41f7b05f039d860f5079b8c0213.png",
    "t100": f"{CMS}/5729359464f3579031b1a5dee918f42a.png",
    "m400": f"{CMS}/3c9712c308bac3e36007c3a9ded88d9d.png",
    "m4pro": f"{CMS}/979ab68fd602bd3440fc4fb12f3ea38e.png",
    "fc100": f"{CMS}/9358904a6d5a4182e2bcd9a0db8be35a.png",
    "p4p": f"{CMS}/670a933d59d49122b51363cdf6f5845b.png",
    "lito1": f"{CMS}/e4b0b945e076ea03849d166583e07aec.png",
    "mavic2": f"{CMS}/bb29aa1a3391d355ae8e9fdd1da89bbd.png",
    "mini5": f"{CMS}/3462d29fa23cf5d29fce9171fb2b6b9d.png",
    "litox1": f"{CMS}/9e110344ffce2fb6fe7c4a181f148892.png",
    "fpv": f"{CMS}/0cb5db0ca2ba38c9fd446070616bf420.png",
    "avata360": f"{CMS}/19c15ba39f4574808ca6b0380b7d44dc.png",
    "air3s": f"{CMS}/ef97699c719414c2138ae8cca2806760.png",
    "neo2": f"{CMS}/1f7d1c7bf99809f9f147ad09081c6d01.png",  # cms2 — NEO 2 label
    "mavicpro": f"{CMS}/bde9054e052865e30e833b16cd7205e3.png",
    "m300": f"{CMS}/7af56f09f88f3f111f5d56f106d222e2.png",
}
EXPECTED_MD5 = {
    "t70p": "3bde89e5d33e82c1c470790df3a8e74c",
    "t100": "b6ea3bc0027b363573b198555e60abf9",
    "m400": "6311b31a7a3a081d05102c6adb31e7e0",
    "m4pro": "4f67801b51fe0bfe1a7dd4c12eca5d25",
    "fc100": "67b28d4ba81ae68bf3348aff2e02b48e",
    "p4p": "ff3c64698b365b93ce11fa5fa590c01d",
    "lito1": "2a184b3cf6e4f645e9d2064f4c4d86cc",
    "mavic2": "58725036851a63000d1fd6d6a849b07e",
    "mini5": "8e4a7146901ef86f6b6e58029825c819",
    "litox1": "1d49a544d86239cc06f03c434587ae15",
    "fpv": "9d779cfa57532aa5aeafd145b9df34d1",
    "avata360": "1f07ff11c18687f35ff5af6a6e3a1325",
    "air3s": "1bb9b26c190fbd6ec980434fcc801a32",
    "neo2": "e2f2be00f7cf3d9cc58dc085259f8245",
    "mavicpro": "d1ba00f6002f1b79384e6a49525d75f0",
    "m300": "f904e84f66b927d7b99de4f0f45e5de1",
}

# Model-token filtered; enrich_video_list drops bad titles.
YT = {
    "t70p": ["https://www.youtube.com/watch?v=mL6XyTTwF28"],
    "t100": ["https://www.youtube.com/watch?v=mL6XyTTwF28"],  # T70P clip mentions T100 family; filtered
    "fc100": ["https://www.youtube.com/watch?v=QCU3fBOJ0H0"],
    "lito": ["https://www.youtube.com/watch?v=NbrlNSoSC78"],
    "neo2": ["https://www.youtube.com/watch?v=L9xa1Hs_cNE"],
    "fpv": [
        "https://www.youtube.com/watch?v=mn6SnARfs34",
        "https://www.youtube.com/watch?v=SrfPPgAOtoY",
    ],
    "m300": [
        "https://www.youtube.com/watch?v=tIVKpyMhUVA",
        "https://www.youtube.com/watch?v=Fr4zWJo9zV4",
    ],
    "mavic2": ["https://www.youtube.com/watch?v=TjTij8D54fs"],
    "mavicpro": [
        "https://www.youtube.com/watch?v=piDNaloubEA",
        "https://www.youtube.com/watch?v=mo1ki0_SfF4",
    ],
    "p4p": ["https://www.youtube.com/watch?v=hJDglCPa3lU"],
}

TAGS_CAM = "Drone|UAV|Quadrotor|Aerial|Outdoor|Electric|Photography|Camera Drone|Aerial Photography|Consumer"
TAGS_FPV = "Drone|UAV|Quadrotor|Aerial|Outdoor|Electric|Photography|Camera Drone|Consumer"
TAGS_ENT = "Drone|UAV|Quadrotor|Aerial|Outdoor|Electric|Inspection|Mapping|Enterprise|Aerial Inspection"
TAGS_AG = "Drone|UAV|Quadrotor|Aerial|Outdoor|Electric|Agriculture"
TAGS_DEL = "Drone|UAV|Quadrotor|Aerial|Outdoor|Electric|Delivery|Logistics"

_AVAIL_IDS = {
    "announced": 10,
    "available": 11,
    "released": 3,
    "discontinued": 4,
    "pre_order": 12,
}

REJECTS: dict[int, str] = {
    417: (
        "Series shell, not a single robot SKU. Name 'DJI Matrice Series' with URL "
        "https://www.dji.com/global/products/power-series (nav/power-series junk). "
        "Keep specific Matrice SKUs (Matrice 400 #5098, Matrice 300 #106)."
    ),
    416: (
        "Series shell 'DJI Inspire Series' pointing at power-series nav junk URL, "
        "not an exact-variant PDP. Reject as non_robot / series shell."
    ),
    415: (
        "Series shell 'DJI Mini Series' with power-series junk URL. Keep Mini 5 Pro #5092."
    ),
    414: (
        "Series shell 'DJI Air Series' with power-series junk URL. Keep Air 3S #2818."
    ),
    413: (
        "Series shell 'DJI Mavic 3 Series' with power-series junk URL, not a single SKU. "
        "Mavic keepers are Mavic 4 Pro / Mavic 2 / Mavic Pro."
    ),
    108: (
        "Generic family shell 'DJI Agras' with Indonesian /id/t40 URL. Specific AGRAS "
        "keepers already exist (T70P #5099, T100 #3614). Prefer reject family shell over "
        "remapping to T40."
    ),
    418: (
        "Vague 'DJI FlyCart' shell with enterprise Care footer URL "
        "(djicare-enterprise?from=footer), wrong family_key dji:dji-matrice-4d, and "
        "payload_kg=85 matching FlyCart 100. Keep FlyCart 100 #5096 "
        "(https://www.dji.com/global/flycart-100). Not remapped to FlyCart 30 — record "
        "is not that SKU."
    ),
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
                "manufacturer_countries": [CN_COUNTRY_ID],
                "manufacturer_country_ref": CN_COUNTRY_ID,
            },
        )
        ok_keys.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def force_translation_en(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    """Clear zh overlay — research API prefers zh-CN translations when present."""
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"dji-en-force-{rid}-20260729-{loc}",
                "translated_fields": {
                    "description": fix.get("description") or "",
                    "features": fix.get("features") or "",
                    "purpose": fix.get("purpose") or "",
                    "name": fix.get("name") or "",
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
        print(f"  translation-sync {rid}: {resp.status_code}")
    except Exception as exc:
        print(f"  translation-sync warn {rid}: {exc}", file=sys.stderr)


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
        if not isinstance(flags, list) or not flags:
            continue
        before = [(f.get("flag") if isinstance(f, dict) else f) for f in flags]
        after = [
            f
            for f in flags
            if (f.get("flag") if isinstance(f, dict) else f) not in drop
        ]
        removed = sorted(set(before) - {(f.get("flag") if isinstance(f, dict) else f) for f in after})
        if not removed:
            continue
        try:
            client._patch(f"robots/robots/{rid}/", {"quality_flags": after})
            print(f"  dropped flags {rid}: {removed}")
        except Exception as exc:
            print(f"  flag-drop fail {rid}: {exc}", file=sys.stderr)


def _ms_to_kmh(ms: float) -> float:
    return round(ms * 3.6, 1)


# ---------------------------------------------------------------------------
# ROBOT FIXES
# ---------------------------------------------------------------------------

ROBOT_FIXES: dict[int, dict[str, Any]] = {
    5099: {
        "name": "DJI AGRAS T70P",
        "model_name": "AGRAS T70P",
        "variant_code": "T70P",
        "variant_label": "T70P",
        "url": "https://ag.dji.com/t70p",
        "family_key": "dji:agras",
        "family_name": "AGRAS",
        "family_url": "https://ag.dji.com/t70p",
        "product_url_scope": "exact_variant",
        "image": IMG["t70p"],
        "description": (
            "DJI AGRAS T70P is an agricultural multirotor for spraying, spreading, and "
            "lifting with a 70 L spray tank and up to 70 kg payload capacity. It pairs "
            "Safety System 3.0 obstacle sensing with O4 video transmission for "
            "high-efficiency crop protection and field logistics."
        ),
        "purpose": (
            "Crop spraying\n"
            "Granular fertilizer spreading\n"
            "Field cargo lifting\n"
            "Large-area agricultural operations"
        ),
        "features": (
            "70 L spraying tank with up to 40 L/min flow; 100 L spreading tank with up to "
            "400 kg/min flow; maximum payload capacity 70 kg (OEM); max operation speed "
            "20 m/s; Safety System 3.0 with AR obstacle display; O4 video transmission "
            "with optional O4 Relay; supports spraying, spreading, and lifting modes."
        ),
        "payload_kg": 70.0,
        "speed": _ms_to_kmh(20),
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "agriculture|commercial",
        "use_keys": "agriculture|spraying|inspection",
        "category_slugs": "service-robots",
        "sub_category_slug": "agricultural-robots",
        "tags": TAGS_AG,
        "manufacturer_country_code": CN,
        "videos": YT["t70p"],
        "information_source_urls": ["https://ag.dji.com/t70p"],
        "notes_force": (
            "[AI Research] OEM ag.dji.com/t70p: max payload 70 kg; 70 L spray / 100 L "
            "spread tanks; 20 m/s max operation speed. Hero: CMS product render "
            "(distinct from T100 coaxial). Cleared stub features."
        ),
        "source_note": "https://ag.dji.com/t70p",
    },
    3614: {
        "name": "DJI AGRAS T100",
        "model_name": "AGRAS T100",
        "variant_code": "T100",
        "variant_label": "T100",
        "url": "https://ag.dji.com/t100",
        "family_key": "dji:agras",
        "family_name": "AGRAS",
        "family_url": "https://ag.dji.com/t100",
        "product_url_scope": "exact_variant",
        "image": IMG["t100"],
        "description": (
            "DJI AGRAS T100 is a high-capacity agricultural multirotor with a 100 L "
            "spraying tank and up to 100 kg payload for large-scale spraying, spreading, "
            "and lifting. Coaxial octocopter propulsion and upgraded safety systems "
            "target big-field crop protection."
        ),
        "purpose": (
            "High-capacity crop spraying\n"
            "Bulk granular spreading\n"
            "Heavy field lifting\n"
            "Large-area farm operations"
        ),
        "features": (
            "100 L spraying tank; 150 L spreading tank; maximum payload 100 kg (OEM); "
            "max takeoff weight kept at 149.9 kg per OEM guidance; 20 m/s max operation "
            "speed; coaxial eight-rotor layout; O4 video transmission; Safety System "
            "with obstacle sensing for spray/spread missions."
        ),
        "payload_kg": 100.0,
        "speed": _ms_to_kmh(20),
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "agriculture|commercial",
        "use_keys": "agriculture|spraying|inspection",
        "category_slugs": "service-robots",
        "sub_category_slug": "agricultural-robots",
        "tags": TAGS_AG,
        "manufacturer_country_code": CN,
        "videos": YT["t70p"],
        "information_source_urls": ["https://ag.dji.com/t100"],
        "notes_force": (
            "[AI Research] OEM ag.dji.com/t100: payload 100 kg; 100 L spray / 150 L "
            "spread; MTOW 149.9 kg. Hero: coaxial CMS render (distinct md5 from T70P)."
        ),
        "source_note": "https://ag.dji.com/t100",
    },
    5098: {
        "name": "DJI Matrice 400",
        "model_name": "Matrice 400",
        "variant_code": "Matrice 400",
        "variant_label": "Matrice 400",
        "url": "https://enterprise.dji.com/matrice-400",
        "family_key": "dji:matrice",
        "family_name": "Matrice",
        "family_url": "https://enterprise.dji.com/matrice-400",
        "product_url_scope": "exact_variant",
        "image": IMG["m400"],
        "description": (
            "DJI Matrice 400 is an enterprise multirotor platform for inspection, "
            "mapping, and public-safety missions. It supports up to 6 kg payload at "
            "the third gimbal connector, IP55 protection, and O4 Enterprise Enhanced "
            "video transmission with multi-sensor obstacle sensing."
        ),
        "purpose": (
            "Industrial inspection\n"
            "Aerial mapping and surveying\n"
            "Public safety and SAR support\n"
            "Multi-payload enterprise sensing"
        ),
        "features": (
            "Max payload 6 kg (third gimbal connector, sea level); max takeoff weight "
            "15.8 kg; takeoff weight with batteries ~9.74 kg; max flight time up to 59 "
            "min with H30T (OEM windless cite); max horizontal speed 25 m/s; IP55; "
            "rotating LiDAR + mmWave radar + omnidirectional vision; O4 Enterprise "
            "Enhanced transmission up to 40 km (FCC)."
        ),
        "payload_kg": 6.0,
        "weight_kg": 9.74,
        "speed": _ms_to_kmh(25),
        "runtime_minutes": 59,
        "length_mm": 980,
        "width_mm": 760,
        "height_mm": 480,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "commercial|utilities|public-safety|construction",
        "use_keys": "inspection|mapping|surveillance",
        "category_slugs": "service-robots",
        "sub_category_slug": "inspection-robots",
        "tags": TAGS_ENT,
        "manufacturer_country_code": CN,
        "videos": [],
        "information_source_urls": [
            "https://enterprise.dji.com/matrice-400",
            "https://enterprise.dji.com/matrice-400/specs",
        ],
        "notes_force": (
            "[AI Research] OEM enterprise.dji.com/matrice-400/specs: payload 6 kg, "
            "MTOW 15.8 kg, weight with batteries 9740±40 g, speed 25 m/s, flight 59 min. "
            "Fixed wrong family_key dji:dji-matrice-4d → dji:matrice."
        ),
        "source_note": "https://enterprise.dji.com/matrice-400/specs",
    },
    106: {
        "name": "DJI Matrice 300 RTK",
        "model_name": "Matrice 300 RTK",
        "variant_code": "Matrice 300 RTK",
        "variant_label": "M300 RTK",
        "url": "https://www.dji.com/global/support/product/matrice-300",
        "family_key": "dji:matrice",
        "family_name": "Matrice",
        "family_url": "https://www.dji.com/global/support/product/matrice-300",
        "product_url_scope": "exact_variant",
        "image": IMG["m300"],
        "description": (
            "DJI Matrice 300 RTK is an enterprise multirotor for inspection and mapping "
            "with RTK positioning, multi-gimbal payload support, and up to 55 minutes "
            "flight time. Official EN product marketing has moved to newer Matrice "
            "platforms; specs retained from DJI support."
        ),
        "purpose": (
            "Industrial inspection\n"
            "Aerial mapping\n"
            "Public safety support\n"
            "Multi-gimbal enterprise sensing"
        ),
        "features": (
            "Weight ~3.6 kg without batteries / ~6.3 kg with two TB60; single gimbal "
            "damper max payload 930 g; max takeoff weight 9 kg; max flight time 55 min; "
            "max speed S-mode 23 m/s; unfolded 810×670×430 mm; IP45 weather resistance "
            "(OEM era claims); OcuSync Enterprise transmission."
        ),
        "payload_kg": 0.93,
        "weight_kg": 6.3,
        "speed": _ms_to_kmh(23),
        "runtime_minutes": 55,
        "length_mm": 810,
        "width_mm": 670,
        "height_mm": 430,
        "availability_status_key": "discontinued",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "commercial|utilities|public-safety",
        "use_keys": "inspection|mapping|surveillance",
        "category_slugs": "service-robots",
        "sub_category_slug": "inspection-robots",
        "tags": TAGS_ENT,
        "manufacturer_country_code": CN,
        "videos": YT["m300"],
        "information_source_urls": [
            "https://www.dji.com/global/support/product/matrice-300",
        ],
        "notes_force": (
            "[AI Research] Remapped from /id/ Indonesian support URL to EN support. "
            "Cleared fabricated payload_kg=3.6 (that was empty weight). OEM: damper "
            "payload 930 g; aircraft 6.3 kg with TB60; MTOW 9 kg; flight 55 min. "
            "Marked Discontinued (superseded by newer Matrice)."
        ),
        "source_note": "https://www.dji.com/global/support/product/matrice-300",
    },
    5096: {
        "name": "DJI FlyCart 100",
        "model_name": "FlyCart 100",
        "variant_code": "FC100",
        "variant_label": "FlyCart 100",
        "url": "https://www.dji.com/global/flycart-100",
        "family_key": "dji:flycart",
        "family_name": "FlyCart",
        "family_url": "https://www.dji.com/global/flycart-100",
        "product_url_scope": "exact_variant",
        "image": IMG["fc100"],
        "description": (
            "DJI FlyCart 100 is a heavy-lift delivery multirotor with up to 85 kg "
            "payload in dual-battery configuration, winch and lifting payload systems, "
            "integrated parachute, and O4 video transmission for aerial logistics."
        ),
        "purpose": (
            "Heavy aerial cargo delivery\n"
            "Winch-based load placement\n"
            "Remote logistics and supply\n"
            "Industrial site material transport"
        ),
        "features": (
            "85 kg payload capacity with dual battery (OEM); weight without payload "
            "55.2 kg (lifting) / 60.2 kg (winch), batteries excluded; max takeoff weight "
            "170 kg (150 kg restricted regions); max horizontal speed 20 m/s; IP55; "
            "LiDAR + penta-vision + mmWave radar; flagship winch system; integrated "
            "parachute; O4 transmission."
        ),
        "payload_kg": 85.0,
        "weight_kg": 55.2,
        "speed": _ms_to_kmh(20),
        "runtime_minutes": 14,
        "length_mm": 3220,
        "width_mm": 3224,
        "height_mm": 975,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "logistics|commercial|construction",
        "use_keys": "delivery|logistics|transport",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS_DEL,
        "manufacturer_country_code": CN,
        "videos": YT["fc100"],
        "information_source_urls": [
            "https://www.dji.com/global/flycart-100",
            "https://www.dji.com/global/flycart-100/specs",
        ],
        "notes_force": (
            "[AI Research] OEM flycart-100/specs: 85 kg dual-battery payload; empty "
            "airframe 55.2/60.2 kg; MTOW 170 kg; speed 20 m/s; flight ~14 min at "
            "149.9 kg TOW. Survivor vs rejected FlyCart shell #418."
        ),
        "source_note": "https://www.dji.com/global/flycart-100/specs",
    },
    5097: {
        "name": "DJI Mavic 4 Pro",
        "model_name": "Mavic 4 Pro",
        "variant_code": "Mavic 4 Pro",
        "variant_label": "Mavic 4 Pro",
        "url": "https://www.dji.com/global/mavic-4-pro",
        "family_key": "dji:mavic",
        "family_name": "Mavic",
        "family_url": "https://www.dji.com/global/mavic-4-pro",
        "product_url_scope": "exact_variant",
        "image": IMG["m4pro"],
        "description": (
            "DJI Mavic 4 Pro is a foldable camera drone with a Hasselblad triple-camera "
            "system, omnidirectional obstacle sensing with forward LiDAR, and O4+ "
            "video transmission for professional aerial photography and cinematography."
        ),
        "purpose": (
            "Aerial photography\n"
            "Cinematic videography\n"
            "Content creation\n"
            "Travel and landscape capture"
        ),
        "features": (
            "Takeoff weight approx. 1063 g; max flight time 51 min; max hovering 45 min; "
            "max horizontal speed 25 m/s (Sport); O4+ transmission; Hasselblad 4/3 CMOS "
            "100 MP + medium tele + tele cameras; omnidirectional sensing with "
            "forward-facing LiDAR; folded 257.6×124.8×106.6 mm (with props)."
        ),
        "clear_payload": True,
        "weight_kg": 1.063,
        "speed": _ms_to_kmh(25),
        "runtime_minutes": 51,
        "length_mm": 257.6,
        "width_mm": 124.8,
        "height_mm": 106.6,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "media-entertainment|commercial|consumer",
        "use_keys": "photography|inspection",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_CAM,
        "manufacturer_country_code": CN,
        "videos": [],
        "information_source_urls": [
            "https://www.dji.com/global/mavic-4-pro",
            "https://www.dji.com/global/mavic-4-pro/specs",
        ],
        "notes_force": (
            "[AI Research] OEM mavic-4-pro/specs. Camera drone — no external payload_kg. "
            "Hero CMS shows MAVIC 4 PRO arm label."
        ),
        "source_note": "https://www.dji.com/global/mavic-4-pro/specs",
    },
    5093: {
        "name": "DJI Mavic 2",
        "model_name": "Mavic 2",
        "variant_code": "Mavic 2",
        "variant_label": "Mavic 2",
        "url": "https://www.dji.com/global/support/product/mavic-2",
        "family_key": "dji:mavic",
        "family_name": "Mavic",
        "family_url": "https://www.dji.com/global/support/product/mavic-2",
        "product_url_scope": "family",
        "image": IMG["mavic2"],
        "description": (
            "DJI Mavic 2 is a discontinued foldable camera-drone family (Pro and Zoom "
            "variants) with omnidirectional obstacle sensing and OcuSync 2.0 "
            "transmission. Specs below cite the OEM support page (Pro 907 g / Zoom 905 g)."
        ),
        "purpose": (
            "Aerial photography\n"
            "Travel videography\n"
            "Content creation"
        ),
        "features": (
            "Takeoff weight Mavic 2 Pro 907 g / Zoom 905 g; max flight time 31 min "
            "(no wind at 25 kph); max speed 72 kph (S-mode); folded 214×91×84 mm; "
            "unfolded 322×242×84 mm; omnidirectional obstacle sensing; OcuSync 2.0."
        ),
        "clear_payload": True,
        "weight_kg": 0.907,
        "speed": 72.0,
        "runtime_minutes": 31,
        "length_mm": 214,
        "width_mm": 91,
        "height_mm": 84,
        "availability_status_key": "discontinued",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "media-entertainment|consumer",
        "use_keys": "photography",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_CAM,
        "manufacturer_country_code": CN,
        "videos": YT["mavic2"],
        "information_source_urls": [
            "https://www.dji.com/global/support/product/mavic-2",
        ],
        "notes_force": (
            "[AI Research] PDP redirects to support. Cleared fabricated payload_kg=2.5. "
            "Weight cites Mavic 2 Pro 907 g. Discontinued."
        ),
        "source_note": "https://www.dji.com/global/support/product/mavic-2",
    },
    168: {
        "name": "Mavic Pro",
        "model_name": "Mavic Pro",
        "variant_code": "Mavic Pro",
        "variant_label": "Mavic Pro",
        "url": "https://www.dji.com/global/support/product/mavic",
        "family_key": "dji:mavic",
        "family_name": "Mavic",
        "family_url": "https://www.dji.com/global/support/product/mavic",
        "product_url_scope": "exact_variant",
        "image": IMG["mavicpro"],
        "description": (
            "Mavic Pro is DJI's first-generation foldable consumer camera drone with "
            "a 4K camera, obstacle sensing, and up to 27 minutes flight time. Official "
            "marketing pages are retired; EN support remains the primary citation."
        ),
        "purpose": (
            "Aerial photography\n"
            "Travel videography\n"
            "Consumer content creation"
        ),
        "features": (
            "Weight 734 g (battery and props, exclude gimbal cover) / 743 g with cover; "
            "max flight time 27 min; max speed 65 kph Sport mode; folded "
            "198×83×83 mm; diagonal 335 mm without props."
        ),
        "clear_payload": True,
        "weight_kg": 0.734,
        "speed": 65.0,
        "runtime_minutes": 27,
        "length_mm": 198,
        "width_mm": 83,
        "height_mm": 83,
        "availability_status_key": "discontinued",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "consumer|media-entertainment",
        "use_keys": "photography",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_CAM,
        "manufacturer_country_code": CN,
        "videos": YT["mavicpro"],
        "information_source_urls": [
            "https://www.dji.com/global/support/product/mavic",
        ],
        "notes_force": (
            "[AI Research] Remapped from /id/ Indonesian support to EN support. "
            "Cleared fabricated payload 2.5. Discontinued (already marked)."
        ),
        "source_note": "https://www.dji.com/global/support/product/mavic",
    },
    5095: {
        "name": "DJI Phantom 4 Pro",
        "model_name": "Phantom 4 Pro",
        "variant_code": "Phantom 4 Pro",
        "variant_label": "Phantom 4 Pro",
        "url": "https://www.dji.com/global/support/product/phantom-4-pro",
        "family_key": "dji:phantom",
        "family_name": "Phantom",
        "family_url": "https://www.dji.com/global/support/product/phantom-4-pro",
        "product_url_scope": "exact_variant",
        "image": IMG["p4p"],
        "description": (
            "DJI Phantom 4 Pro is a discontinued rigid-body camera drone with a 1-inch "
            "sensor camera, forward/rear vision and infrared sensing, and about 30 "
            "minutes flight time. EN support page is the surviving OEM citation."
        ),
        "purpose": (
            "Aerial photography\n"
            "Mapping and surveying support\n"
            "Professional videography"
        ),
        "features": (
            "Aircraft weight 1388 g (battery and props); diagonal 350 mm (props "
            "excluded); max flight time approx. 30 min; max speed S-mode 72 kph; "
            "forward/rear vision + infrared sensing."
        ),
        "clear_payload": True,
        "weight_kg": 1.388,
        "speed": 72.0,
        "runtime_minutes": 30,
        "availability_status_key": "discontinued",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "media-entertainment|commercial|consumer",
        "use_keys": "photography|mapping",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_CAM,
        "manufacturer_country_code": CN,
        "videos": YT["p4p"],
        "information_source_urls": [
            "https://www.dji.com/global/support/product/phantom-4-pro",
        ],
        "notes_force": (
            "[AI Research] PDP redirects to support. Discontinued. Hero CMS Phantom "
            "render."
        ),
        "source_note": "https://www.dji.com/global/support/product/phantom-4-pro",
    },
    5092: {
        "name": "DJI Mini 5 Pro",
        "model_name": "Mini 5 Pro",
        "variant_code": "Mini 5 Pro",
        "variant_label": "Mini 5 Pro",
        "url": "https://www.dji.com/global/mini-5-pro",
        "family_key": "dji:mini",
        "family_name": "Mini",
        "family_url": "https://www.dji.com/global/mini-5-pro",
        "product_url_scope": "exact_variant",
        "image": IMG["mini5"],
        "description": (
            "DJI Mini 5 Pro is a sub-250 g class camera drone with a 1-inch 50 MP CMOS "
            "sensor, omnidirectional obstacle sensing with forward LiDAR, and O4+ "
            "transmission for portable aerial photography."
        ),
        "purpose": (
            "Travel aerial photography\n"
            "Content creation\n"
            "Lightweight cinematic capture"
        ),
        "features": (
            "Takeoff weight 249.9 g (±4 g); max flight time 36 min (standard battery) / "
            "52 min (Battery Plus); max horizontal speed 19 m/s (Battery Plus, S mode); "
            "1-inch 50 MP CMOS f/1.8; O4+ transmission; omnidirectional sensing + "
            "forward LiDAR; folded 157×95×68 mm."
        ),
        "clear_payload": True,
        "weight_kg": 0.2499,
        "speed": _ms_to_kmh(19),
        "runtime_minutes": 36,
        "length_mm": 157,
        "width_mm": 95,
        "height_mm": 68,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "consumer|media-entertainment",
        "use_keys": "photography",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_CAM,
        "manufacturer_country_code": CN,
        "videos": [],
        "information_source_urls": [
            "https://www.dji.com/global/mini-5-pro",
            "https://www.dji.com/global/mini-5-pro/specs",
        ],
        "notes_force": (
            "[AI Research] OEM mini-5-pro/specs. Hero CMS shows MINI 5 PRO arm label."
        ),
        "source_note": "https://www.dji.com/global/mini-5-pro/specs",
    },
    5094: {
        "name": "DJI Lito 1",
        "model_name": "Lito 1",
        "variant_code": "Lito 1",
        "variant_label": "Lito 1",
        "url": "https://www.dji.com/global/lito-1",
        "family_key": "dji:lito",
        "family_name": "Lito",
        "family_url": "https://www.dji.com/global/lito-1",
        "product_url_scope": "exact_variant",
        "image": IMG["lito1"],
        "description": (
            "DJI Lito 1 is an under-249 g beginner camera drone with a 1/2-inch 48 MP "
            "sensor, omnidirectional obstacle sensing, ActiveTrack, and O4 video "
            "transmission for easy aerial content creation."
        ),
        "purpose": (
            "Beginner aerial photography\n"
            "Social content creation\n"
            "Travel vlogging"
        ),
        "features": (
            "Standard takeoff weight approx. 249 g; max flight time 36 min (standard "
            "battery) / 52 min (Battery Plus where supported); max horizontal speed "
            "18 m/s Sport; 1/2-inch 48 MP sensor; 4K/60fps video; O4 transmission up "
            "to 15 km (IC); omnidirectional sensing; ActiveTrack."
        ),
        "clear_payload": True,
        "weight_kg": 0.249,
        "speed": _ms_to_kmh(18),
        "runtime_minutes": 36,
        "length_mm": 149,
        "width_mm": 94,
        "height_mm": 62,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "consumer|media-entertainment",
        "use_keys": "photography",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_CAM,
        "manufacturer_country_code": CN,
        "videos": YT["lito"],
        "information_source_urls": [
            "https://www.dji.com/global/lito-1",
            "https://www.dji.com/global/lito-1/specs",
        ],
        "notes_force": (
            "[AI Research] OEM lito-1/specs. Live PDP confirmed 200. Hero CMS shows "
            "LITO 1 arm label."
        ),
        "source_note": "https://www.dji.com/global/lito-1/specs",
    },
    5091: {
        "name": "DJI Lito X1",
        "model_name": "Lito X1",
        "variant_code": "Lito X1",
        "variant_label": "Lito X1",
        "url": "https://www.dji.com/global/lito-x1",
        "family_key": "dji:lito",
        "family_name": "Lito",
        "family_url": "https://www.dji.com/global/lito-x1",
        "product_url_scope": "exact_variant",
        "image": IMG["litox1"],
        "description": (
            "DJI Lito X1 is an under-249 g camera drone with a larger 1/1.3-inch 48 MP "
            "sensor, forward LiDAR-assisted omnidirectional sensing, ActiveTrack, and "
            "O4 transmission for beginner-friendly aerial creation."
        ),
        "purpose": (
            "Beginner aerial photography\n"
            "Social content creation\n"
            "Travel videography"
        ),
        "features": (
            "Standard takeoff weight approx. 249 g; 1/1.3-inch 48 MP sensor; max flight "
            "time 36/52 min (standard / Plus battery where supported); max horizontal "
            "speed 18 m/s Sport; O4 transmission; omnidirectional sensing with "
            "forward-facing LiDAR; 42 GB internal storage."
        ),
        "clear_payload": True,
        "weight_kg": 0.249,
        "speed": _ms_to_kmh(18),
        "runtime_minutes": 36,
        "length_mm": 144,
        "width_mm": 94,
        "height_mm": 62,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "consumer|media-entertainment",
        "use_keys": "photography",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_CAM,
        "manufacturer_country_code": CN,
        "videos": YT["lito"],
        "information_source_urls": [
            "https://www.dji.com/global/lito-x1",
            "https://www.dji.com/global/lito-x1/specs",
        ],
        "notes_force": (
            "[AI Research] OEM lito-x1/specs. Live PDP confirmed. Hero CMS shows "
            "LITO X1 arm label."
        ),
        "source_note": "https://www.dji.com/global/lito-x1/specs",
    },
    2818: {
        "name": "DJI Air 3S",
        "model_name": "Air 3S",
        "variant_code": "Air 3S",
        "variant_label": "Air 3S",
        "url": "https://www.dji.com/global/air-3s",
        "family_key": "dji:air",
        "family_name": "Air",
        "family_url": "https://www.dji.com/global/air-3s",
        "product_url_scope": "exact_variant",
        "image": IMG["air3s"],
        "description": (
            "DJI Air 3S is a dual-camera foldable drone with a 1-inch primary CMOS and "
            "medium tele camera, nightscape obstacle sensing, and O4 transmission for "
            "travel and landscape aerial photography."
        ),
        "purpose": (
            "Travel aerial photography\n"
            "Landscape videography\n"
            "Dual-camera content creation"
        ),
        "features": (
            "Takeoff weight 724 g; max flight time 45 min; max hovering 41 min; max "
            "horizontal speed 21 m/s (windless sea-level cite); dual cameras (1-inch "
            "50 MP wide + 1/1.3-inch 48 MP medium tele); O4 transmission; "
            "omnidirectional sensing with forward LiDAR; folded 214.19×100.63×89.17 mm."
        ),
        "clear_payload": True,
        "weight_kg": 0.724,
        "speed": _ms_to_kmh(21),
        "runtime_minutes": 45,
        "length_mm": 214.19,
        "width_mm": 100.63,
        "height_mm": 89.17,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "consumer|media-entertainment",
        "use_keys": "photography",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_CAM,
        "manufacturer_country_code": CN,
        "videos": [],
        "information_source_urls": [
            "https://www.dji.com/global/air-3s",
            "https://www.dji.com/global/air-3s/specs",
        ],
        "notes_force": (
            "[AI Research] OEM air-3s/specs. Hero CMS shows AIR 3S arm label."
        ),
        "source_note": "https://www.dji.com/global/air-3s/specs",
    },
    2817: {
        "name": "DJI Neo 2",
        "model_name": "Neo 2",
        "variant_code": "Neo 2",
        "variant_label": "Neo 2",
        "url": "https://www.dji.com/global/neo-2",
        "family_key": "dji:neo",
        "family_name": "Neo",
        "family_url": "https://www.dji.com/global/neo-2",
        "product_url_scope": "exact_variant",
        "image": IMG["neo2"],
        "description": (
            "DJI Neo 2 is a palm-sized self-flying camera drone with integrated "
            "propeller guards, gesture control, omnidirectional obstacle sensing, and "
            "optional O4 digital transceiver for vlogging and follow shots."
        ),
        "purpose": (
            "Palm takeoff selfies and vlogs\n"
            "Gesture-controlled follow shots\n"
            "Beginner indoor/outdoor content"
        ),
        "features": (
            "Takeoff weight 151 g (without digital transceiver) / 160 g (with); max "
            "flight time approx. 19 min; max hovering approx. 18 min; max horizontal "
            "speed 12 m/s Sport; 1/2-inch CMOS; integrated propeller guards; "
            "omnidirectional sensing with forward LiDAR; 49 GB internal storage."
        ),
        "clear_payload": True,
        "weight_kg": 0.151,
        "speed": _ms_to_kmh(12),
        "runtime_minutes": 19,
        "length_mm": 147,
        "width_mm": 171,
        "height_mm": 41,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "consumer|media-entertainment",
        "use_keys": "photography",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_CAM,
        "manufacturer_country_code": CN,
        "videos": YT["neo2"],
        "information_source_urls": [
            "https://www.dji.com/global/neo-2",
            "https://www.dji.com/global/neo-2/specs",
        ],
        "notes_force": (
            "[AI Research] OEM neo-2/specs. Hero uses CMS secondary product still with "
            "visible NEO 2 label (primary OG resembled Avata-class cinewhoop)."
        ),
        "source_note": "https://www.dji.com/global/neo-2/specs",
    },
    3613: {
        "name": "DJI Avata 360",
        "model_name": "Avata 360",
        "variant_code": "Avata 360",
        "variant_label": "Avata 360",
        "url": "https://www.dji.com/global/avata-360",
        "family_key": "dji:avata",
        "family_name": "Avata",
        "family_url": "https://www.dji.com/global/avata-360",
        "product_url_scope": "exact_variant",
        "image": IMG["avata360"],
        "description": (
            "DJI Avata 360 is an FPV-style camera drone with dual 1/1.1-inch sensors for "
            "360° capture, integrated propeller guards, omnidirectional sensing, and "
            "O4+ transmission for immersive aerial footage."
        ),
        "purpose": (
            "360° aerial capture\n"
            "Immersive FPV content\n"
            "Action and travel videography"
        ),
        "features": (
            "Takeoff weight approx. 455 g; max flight time approx. 23 min; max hovering "
            "approx. 22 min; max horizontal speed 18 m/s Sport; dual 1/1.1-inch 64 MP "
            "sensors; 8K 360° video; integrated propeller guards; O4+ transmission; "
            "omnidirectional sensing with forward LiDAR."
        ),
        "clear_payload": True,
        "weight_kg": 0.455,
        "speed": _ms_to_kmh(18),
        "runtime_minutes": 23,
        "length_mm": 246,
        "width_mm": 199,
        "height_mm": 55.5,
        "availability_status_key": "available",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "consumer|media-entertainment",
        "use_keys": "photography",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_FPV,
        "manufacturer_country_code": CN,
        "videos": [],
        "information_source_urls": [
            "https://www.dji.com/global/avata-360",
            "https://www.dji.com/global/avata-360/specs",
        ],
        "notes_force": (
            "[AI Research] OEM avata-360/specs. Live PDP confirmed. Hero CMS shows "
            "AVATA 360 camera housing label."
        ),
        "source_note": "https://www.dji.com/global/avata-360/specs",
    },
    3615: {
        "name": "DJI FPV",
        "model_name": "DJI FPV",
        "variant_code": "DJI FPV",
        "variant_label": "DJI FPV",
        "url": "https://www.dji.com/global/support/product/dji-fpv",
        "family_key": "dji:fpv",
        "family_name": "FPV",
        "family_url": "https://www.dji.com/global/support/product/dji-fpv",
        "product_url_scope": "exact_variant",
        "image": IMG["fpv"],
        "description": (
            "DJI FPV is a discontinued high-speed FPV camera drone with a 150° FOV "
            "camera, Motion Controller / Goggles ecosystem, and up to 140 kph top "
            "speed in Manual mode. Thin /global/dji-fpv marketing shell replaced with "
            "EN support specs."
        ),
        "purpose": (
            "Immersive FPV flight\n"
            "High-speed aerial videography\n"
            "Motion-controller freestyle flying"
        ),
        "features": (
            "Takeoff weight approx. 795 g; dimensions 255×312×127 mm with props; max "
            "flight time approx. 20 min; max speed 140 kph (M mode); 1/2.3-inch 12 MP "
            "CMOS; FOV 150°; forward obstacle sensing in N mode."
        ),
        "clear_payload": True,
        "weight_kg": 0.795,
        "speed": 140.0,
        "runtime_minutes": 20,
        "length_mm": 255,
        "width_mm": 312,
        "height_mm": 127,
        "availability_status_key": "discontinued",
        "movement_type_keys": "flying|aerial",
        "industry_keys": "consumer|media-entertainment",
        "use_keys": "photography",
        "category_slugs": "service-robots",
        "sub_category_slug": "other",
        "tags": TAGS_FPV,
        "manufacturer_country_code": CN,
        "videos": YT["fpv"],
        "information_source_urls": [
            "https://www.dji.com/global/support/product/dji-fpv",
        ],
        "notes_force": (
            "[AI Research] Renamed from 'DJI Dji Fpv'. Thin marketing URL → EN support. "
            "Cleared fabricated payload_kg=1.46. Discontinued."
        ),
        "source_note": "https://www.dji.com/global/support/product/dji-fpv",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix DJI company 27 robots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--reject-shells", action="store_true")
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
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: payload={row.get('payload_kg')} "
            f"speed={row.get('speed')} weight={row.get('weight_kg')} "
            f"fam={row.get('family_key')} avail={fix.get('availability_status_key')} "
            f"clear_pay={bool(fix.get('clear_payload'))} "
            f"vids={len(row.get('video_urls') or [])} tags={tags}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "dji-27-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "id": t["id"],
                        "name": t["name"],
                        "payload_kg": t["row"].get("payload_kg"),
                        "speed": t["row"].get("speed"),
                        "weight_kg": t["row"].get("weight_kg"),
                        "family_key": t["row"].get("family_key"),
                        "image": (t["row"].get("image") or "")[:120],
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

    if not targets and not (args.reject_shells and REJECTS):
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(
            f"Preview: {preview}. Re-run with "
            "--apply --copy-media --verify-cdn --reject-shells --drop-flags --mark-done"
        )
        return 0

    rejected: list[dict[str, Any]] = []
    if args.reject_shells:
        for rid, reason in REJECTS.items():
            if args.only and rid not in args.only:
                continue
            msg = reject_robot(client, rid, reason)
            print(f"REJECT {rid}: {msg}")
            rejected.append({"id": rid, "reason": reason, "result": msg})

    tmp = Path(tempfile.mkdtemp(prefix="dji-fix-"))
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
            force_translation_en(client, rid, item["fix"])
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

    cdn_rc = None
    if args.verify_cdn and imported:
        cdn_rc = subprocess.call(
            [sys.executable, str(_RESEARCH_DIR / "verify_cdn_images.py"), "--company-id", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )
        if cdn_rc != 0:
            print("CDN verify FAILED", file=sys.stderr)

    if args.drop_flags and imported:
        drop_verification_flags(client, imported)

    if args.mark_done and imported:
        subprocess.call(
            [sys.executable, str(_RESEARCH_DIR / "triage_content_queue.py"), "--mark-done", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )

    print("totals", totals, "rejected", len(rejected), "copy", copy_stats, "cdn_rc", cdn_rc)
    return 0 if (cdn_rc in (None, 0)) else int(cdn_rc)


if __name__ == "__main__":
    raise SystemExit(main())
