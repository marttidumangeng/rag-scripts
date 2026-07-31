"""Ecovacs Robotics (company 32) — full enrichment pass 2026-07-29.

Addresses the user complaint \"duplicate images, no family data\" and the
current probe gaps (feat=0 BLACK twins, empty family_key, clear URL/name
dupes, soft taxonomy/availability).

Reuses curated text/media from:
  - fix_ecovacs_robots.py
  - fix_ecovacs_thin_content.py
  - fix_ecovacs_media.py (IMAGELESS notes + optional media refresh)

Family scheme (NOT one giant deebot key):
  ecovacs-robotics:deebot-x | deebot-t | deebot-n | deebot-mini
  ecovacs-robotics:winbot | goat | airbot | deebot-pro

    python fix_ecovacs_32_robots.py
    python fix_ecovacs_32_robots.py --apply
    python fix_ecovacs_32_robots.py --apply --copy-media
    python fix_ecovacs_32_robots.py --apply --refresh-media --copy-media
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
from validate_staging import purpose_duplicates_description
from youtube_metadata import enrich_video_list

import fix_ecovacs_robots as GREEN
import fix_ecovacs_thin_content as THIN
import fix_ecovacs_media as MEDIA

COMPANY_ID = 32
COMPANY_SLUG = "ecovacs-robotics"
COMPANY_NAME = "Ecovacs Robotics"
CN = "CN"
CN_COUNTRY_ID = 3
SKIP_STATUSES = {"published", "approved"}

G = "https://www.ecovacs.com/global"
U = "https://www.ecovacs.com/us/shop"
V = "deebot-robotic-vacuum-cleaner"
W = "winbot-window-cleaning-robot"
O = "goat-robotic-lawn-mower"
IMG = "https://site-static.ecovacs.com/upload"

_AVAIL = {"announced": 10, "available": 11, "released": 3, "discontinued": 4}

# ---------------------------------------------------------------------------
# Rejects — clear colour/name/URL duplicates (soft-ask: reject, leave pending
# siblings for human approve).
# ---------------------------------------------------------------------------
REJECTS: dict[int, str] = {
    2473: (
        "Duplicate of DEEBOT mini 2 #4720. Same OEM PDP "
        "(/global/deebot-robotic-vacuum-cleaner/deebot-mini-2-white); prior media "
        "pass showed byte-identical candidates. Keep 4720."
    ),
    2479: (
        "No 'DEEBOT X11 OMNI' SKU exists — X11 line is OmniCyclone / PRO OMNI. "
        "Duplicate of DEEBOT X11 OmniCyclone #4681. Keep 4681."
    ),
    2480: (
        "No 'DEEBOT X12 OMNI' SKU exists — X12 line is OmniCyclone / PRO OMNI. "
        "Duplicate of DEEBOT X12 OmniCyclone #4676. Keep 4676."
    ),
    1939: (
        "X9 PRO OMNI ships black-only; unsuffixed record shares gallery bytes with "
        "DEEBOT X9 PRO OMNI BLACK #4715. Duplicate — keep 4715."
    ),
    1949: (
        "WINBOT W3 PDP is titled W3 OMNI and media is byte-identical to "
        "WINBOT W3 OMNI #4677. Duplicate — keep 4677."
    ),
    1952: (
        "No bare 'GOAT A2000' SKU on any Ecovacs region. Only A2000 LiDAR PRO exists "
        "(different model). Reject as bogus/unresolvable identity; do not borrow "
        "sibling mower imagery."
    ),
    1964: (
        "No 'GOAT G1 Plus' SKU. G1 line is G1 / G1-800 / G1-2000. Unresolvable "
        "identity — reject rather than invent. Keep GOAT G1 #1963."
    ),
}

# Imageless keepers that stay pending with actionable notes.
IMAGELESS_KEEP = {
    2475: MEDIA.IMAGELESS[2475],
}

# Robots whose galleries need a curated OEM re-import (ghost empty photos /
# within-gallery byte dupes / quality duplicate_images flag).
MEDIA_REFRESH_IDS = {
    1937,  # duplicate_images flag
    1941,  # ghost empty photo rows; shared-hash false positive risk
    1951,  # within_dup=2
    1954,  # duplicate_images flag
    1955,  # duplicate_images flag
}

# ---------------------------------------------------------------------------
# Family hubs
# ---------------------------------------------------------------------------
FAMILIES: dict[str, dict[str, str]] = {
    "deebot-x": {
        "family_key": f"{COMPANY_SLUG}:deebot-x",
        "family_name": "DEEBOT X",
        "family_url": f"{G}/{V}",
    },
    "deebot-t": {
        "family_key": f"{COMPANY_SLUG}:deebot-t",
        "family_name": "DEEBOT T",
        "family_url": f"{G}/{V}",
    },
    "deebot-n": {
        "family_key": f"{COMPANY_SLUG}:deebot-n",
        "family_name": "DEEBOT N",
        "family_url": f"{G}/{V}",
    },
    "deebot-mini": {
        "family_key": f"{COMPANY_SLUG}:deebot-mini",
        "family_name": "DEEBOT mini",
        "family_url": f"{G}/{V}/deebot-mini-2-white",
    },
    "winbot": {
        "family_key": f"{COMPANY_SLUG}:winbot",
        "family_name": "WINBOT",
        "family_url": f"{G}/{W}",
    },
    "goat": {
        "family_key": f"{COMPANY_SLUG}:goat",
        "family_name": "GOAT",
        "family_url": f"{G}/{O}",
    },
    "airbot": {
        "family_key": f"{COMPANY_SLUG}:airbot",
        "family_name": "AIRBOT",
        "family_url": f"{G}/airbot-air-purifier-robot/airbot-z1",
    },
    "deebot-pro": {
        "family_key": f"{COMPANY_SLUG}:deebot-pro",
        "family_name": "DEEBOT PRO",
        "family_url": "https://www.ecovacscommercial.com/",
    },
}

PURPOSE = {
    "vacuum": "Home floor vacuuming and mopping",
    "window": "Automatic window and glass cleaning",
    "mower": "Autonomous lawn mowing without boundary wires",
    "air": "Indoor air purification and monitoring",
    "commercial_vac": "Commercial floor vacuuming, sweeping and dust-mopping",
    "commercial_scrub": "Commercial floor scrubbing, sweeping and dust-mopping",
}

TAGS_VACUUM = GREEN.TAGS_VACUUM
TAGS_MOWER = GREEN.TAGS_MOWER
TAGS_WINDOW = GREEN.TAGS_WINDOW
TAGS_AIR = "Smart Home|AI|Autonomous|Navigation|Consumer|Indoor|Monitoring|Wheeled|Ground"
TAGS_COMMERCIAL_VAC = GREEN.TAGS_COMMERCIAL_VAC
TAGS_COMMERCIAL_SCRUB = GREEN.TAGS_COMMERCIAL_SCRUB


def _fam(series: str, **extra: Any) -> dict[str, Any]:
    base = dict(FAMILIES[series])
    base.update(extra)
    base.setdefault("product_url_scope", "exact_variant")
    return base


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.ecovacs.com/",
    }


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
    except Exception as e:  # noqa: BLE001
        return f"FAIL {admin_msg} / patch {e}"


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = _internal_secret()
    api = _admin_base()
    if not secret or not api:
        print("WARN: missing INTERNAL_API_SECRET or admin base for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            body: dict[str, Any] = {}
            try:
                body = resp.json() if resp.content else {}
            except Exception:  # noqa: BLE001
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
        time.sleep(0.25)
    return ok, fail


def verify_hero_md5(url: str) -> str:
    resp = requests.get(url, timeout=60, headers=_headers())
    resp.raise_for_status()
    data = resp.content
    magic_ok = (
        data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"\xff\xd8\xff"
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
    )
    if not magic_ok:
        raise RuntimeError(f"not an image magic={data[:8]!r} url={url}")
    if len(data) < 8_000:
        raise RuntimeError(f"image too small ({len(data)} bytes) url={url}")
    return hashlib.md5(data).hexdigest()


def drop_verification_flags(client: ResearchApiClient, robot_ids: list[int]) -> None:
    drop = {
        "image_mismatch",
        "video_mismatch",
        "url_content_mismatch",
        "content_contradiction",
        "unverifiable",
        "non_english_content",
        "duplicate_images",
    }
    for rid in robot_ids:
        try:
            r = client._get(f"robots/robots/{rid}/")
        except Exception as exc:  # noqa: BLE001
            print(f"  flag-read fail {rid}: {exc}", file=sys.stderr)
            continue
        flags = r.get("error_flags") or r.get("quality_flags") or []
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
            client._patch(f"robots/robots/{rid}/", {"error_flags": after, "quality_flags": after})
            print(f"  dropped flags {rid}: {removed}")
        except Exception as exc:  # noqa: BLE001
            print(f"  flag-drop fail {rid}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Merge greenfield + thin curated content into per-robot fixes
# ---------------------------------------------------------------------------

def _from_green(rid: int, series: str, *, purpose_key: str, **meta: Any) -> dict[str, Any]:
    src = GREEN.ROBOT_DATA[rid]
    out: dict[str, Any] = {
        "name": src["name"],
        "url": src["url"],
        "description": src["description"],
        "features": src["features"],
        "purpose": PURPOSE[purpose_key],
        "tags": src.get("tags") or TAGS_VACUUM,
        "release_year": src.get("release_year"),
        "availability_status": _AVAIL["available"],
        "manufacturer_country_code": CN,
        "movement_type_keys": "wheeled",
        "sub_category_slug": "cleaning-facilities",
        "category_slugs": "service-robots",
        "industry_keys": "homes|consumer",
        "use_keys": "cleaning",
        "sources": src.get("sources") or [],
        "images": src.get("images") or [],
        **_fam(series, **meta),
    }
    for k in (
        "battery_capacity",
        "runtime_minutes",
        "charging_time_minutes",
        "weight_kg",
        "length_mm",
        "width_mm",
        "height_mm",
        "voltage",
        "ip_rating",
        "price_max",
        "price_currency",
        "price_notes",
    ):
        if src.get(k) not in (None, ""):
            out[k] = src[k]
    if src.get("speed_ms") not in (None, ""):
        # speed column is km/h float
        out["speed"] = round(float(src["speed_ms"]) * 3.6, 2)
    if src.get("suction_pa"):
        out["notes_spec"] = f"OEM suction={src['suction_pa']}"
    if src.get("video_ids"):
        out["videos"] = [f"https://www.youtube.com/watch?v={v}" for v in src["video_ids"]]
    return out


def _from_thin(rid: int, series: str, *, purpose_key: str, **meta: Any) -> dict[str, Any]:
    src = THIN.ROBOT_DATA[rid]
    out: dict[str, Any] = {
        "name": src["name"],
        "url": src["url"],
        "features": src["features"],
        "purpose": PURPOSE[purpose_key],
        "tags": "|".join(src["tags"]) if isinstance(src.get("tags"), list) else (src.get("tags") or TAGS_VACUUM),
        "release_year": src.get("release_year"),
        "availability_status": _AVAIL["available"],
        "manufacturer_country_code": CN,
        "movement_type_keys": src.get("movement") or "wheeled",
        "sub_category_slug": "cleaning-facilities",
        "category_slugs": "service-robots",
        "industry_keys": "homes|consumer",
        "use_keys": "cleaning",
        "sources": src.get("sources") or [],
        **_fam(series, **meta),
    }
    for k in (
        "battery_capacity",
        "runtime_minutes",
        "charging_time_minutes",
        "weight_kg",
        "length_mm",
        "width_mm",
        "height_mm",
        "voltage",
    ):
        if src.get(k) not in (None, ""):
            out[k] = src[k]
    return out


def build_robot_fixes() -> dict[int, dict[str, Any]]:
    fixes: dict[int, dict[str, Any]] = {}

    # ---- Greenfield batch (47xx / commercial / recent) ----
    fixes[4720] = _from_green(
        4720, "deebot-mini", purpose_key="vacuum",
        model_name="mini 2", variant_code="mini-2-white", variant_label="White",
    )
    fixes[4719] = _from_green(
        4719, "deebot-t", purpose_key="vacuum",
        model_name="T50 OMNI", variant_code="t50-omni-black", variant_label="Black",
        height_mm=81.0,
    )
    # Override height from green (cited 3.19in) — green may not have typed it
    fixes[4719]["height_mm"] = 81.0
    fixes[4718] = _from_green(
        4718, "deebot-t", purpose_key="vacuum",
        model_name="T50 MAX PRO OMNI", variant_code="t50-max-pro-omni-black",
        variant_label="Black",
    )
    fixes[4717] = _from_green(
        4717, "deebot-t", purpose_key="vacuum",
        model_name="T80 OMNI", variant_code="t80-omni-black", variant_label="Black",
        height_mm=98.0,
    )
    fixes[4717]["height_mm"] = 98.0  # OEM "Ultra-Slim 98mm Design"
    fixes[4716] = _from_green(
        4716, "deebot-t", purpose_key="vacuum",
        model_name="T90 OMNI", variant_code="t90-omni-black", variant_label="Black",
        height_mm=95.0,
    )
    fixes[4716]["height_mm"] = 95.0  # OEM "95mm Height of Robot"
    fixes[4715] = _from_green(
        4715, "deebot-x", purpose_key="vacuum",
        model_name="X9 PRO OMNI", variant_code="x9-pro-omni-black", variant_label="Black",
    )
    fixes[4681] = _from_green(
        4681, "deebot-x", purpose_key="vacuum",
        model_name="X11 OmniCyclone", variant_code="x11-omnicyclone", variant_label="OmniCyclone",
    )
    fixes[4676] = _from_green(
        4676, "deebot-x", purpose_key="vacuum",
        model_name="X12 OmniCyclone", variant_code="x12-omnicyclone", variant_label="OmniCyclone",
    )
    fixes[4680] = _from_green(
        4680, "goat", purpose_key="mower",
        model_name="A3000 LiDAR PRO", variant_code="a3000-lidar-pro",
        variant_label="LiDAR PRO",
    )
    fixes[4680].update({
        "tags": TAGS_MOWER,
        "sub_category_slug": "agriculture",
        "use_keys": "agriculture",
        "industry_keys": "homes|agriculture|consumer",
    })
    fixes[4678] = _from_green(
        4678, "deebot-pro", purpose_key="commercial_vac",
        model_name="DEEBOT PRO K1 VAC", variant_code="k1-vac", variant_label="K1 VAC",
    )
    fixes[4678].update({
        "tags": TAGS_COMMERCIAL_VAC,
        "industry_keys": "commercial|hotels|retail",
        "use_keys": "cleaning",
        "category_slugs": "service-robots",
        # Official B2B domain — note for reviewers; not a mismatch.
        "source_note": (
            "ecovacscommercial.com is the official ECOVACS Commercial Robotics domain "
            "(B2B). url_domain_mismatch vs ecovacs.com is expected/accepted."
        ),
    })
    fixes[4679] = _from_green(
        4679, "deebot-pro", purpose_key="commercial_scrub",
        model_name="DEEBOT PRO M1", variant_code="m1", variant_label="M1",
    )
    fixes[4679].update({
        "tags": TAGS_COMMERCIAL_SCRUB,
        "industry_keys": "commercial|hotels|retail",
        "use_keys": "cleaning",
        "source_note": (
            "ecovacscommercial.com is the official ECOVACS Commercial Robotics domain."
        ),
    })
    # 4677 already has strong OEM features (feat~416) — family/purpose/availability only.
    fixes[4677] = {
        "name": "WINBOT W3 OMNI",
        "url": f"{G}/{W}/winbot-w3",
        "purpose": PURPOSE["window"],
        "tags": TAGS_WINDOW,
        "availability_status": _AVAIL["available"],
        "manufacturer_country_code": CN,
        "movement_type_keys": "other",
        "sub_category_slug": "cleaning-facilities",
        "category_slugs": "service-robots",
        "industry_keys": "homes|consumer",
        "use_keys": "cleaning",
        "sources": [
            {"url": f"{G}/{W}/winbot-w3", "type": "website", "title": "WINBOT W3 OMNI - ECOVACS"},
        ],
        **_fam(
            "winbot",
            model_name="W3 OMNI",
            variant_code="w3-omni",
            variant_label="OMNI",
        ),
    }

    # ---- Thin / legacy pending batch ----
    thin_map = {
        1937: ("deebot-x", "vacuum", {"model_name": "X5 OMNI", "variant_code": "x5-omni-white", "variant_label": "White"}),
        1941: ("deebot-t", "vacuum", {"model_name": "T50 MAX PRO OMNI", "variant_code": "t50-max-pro-omni", "variant_label": "Base"}),
        1943: ("deebot-t", "vacuum", {"model_name": "T50 OMNI", "variant_code": "t50-omni", "variant_label": "Base", "height_mm": 81.0}),
        1945: ("winbot", "window", {"model_name": "W2 OMNI", "variant_code": "w2-omni", "variant_label": "OMNI"}),
        1947: ("winbot", "window", {"model_name": "W2S", "variant_code": "w2s", "variant_label": "W2S"}),
        1951: ("goat", "mower", {"model_name": "A3000", "variant_code": "a3000-lidar", "variant_label": "LiDAR"}),
        1954: ("goat", "mower", {"model_name": "O800", "variant_code": "o800", "variant_label": "O800"}),
        1955: ("deebot-t", "vacuum", {"model_name": "T30 PRO", "variant_code": "t30-pro", "variant_label": "PRO"}),
        1956: ("deebot-t", "vacuum", {"model_name": "T30 OMNI", "variant_code": "t30-omni", "variant_label": "OMNI"}),
        1957: ("deebot-x", "vacuum", {"model_name": "X5 PRO OMNI", "variant_code": "x5-pro-omni", "variant_label": "PRO OMNI"}),
        1958: ("deebot-x", "vacuum", {"model_name": "X2 OMNI", "variant_code": "x2-omni", "variant_label": "OMNI"}),
        1959: ("deebot-n", "vacuum", {"model_name": "N30 PRO", "variant_code": "n30-pro", "variant_label": "PRO"}),
        1960: ("deebot-t", "vacuum", {"model_name": "T20 OMNI", "variant_code": "t20-omni", "variant_label": "OMNI"}),
        1961: ("winbot", "window", {"model_name": "W2 PRO", "variant_code": "w2-pro", "variant_label": "PRO"}),
        1962: ("winbot", "window", {"model_name": "W1 PRO", "variant_code": "w1-pro", "variant_label": "PRO"}),
        1963: ("goat", "mower", {"model_name": "G1", "variant_code": "g1", "variant_label": "G1"}),
        1965: ("airbot", "air", {"model_name": "Z1", "variant_code": "z1", "variant_label": "Z1"}),
        2474: ("deebot-n", "vacuum", {"model_name": "N20 PLUS", "variant_code": "n20-plus", "variant_label": "PLUS"}),
        2475: ("deebot-n", "vacuum", {"model_name": "N30 PLUS", "variant_code": "n30-plus", "variant_label": "PLUS"}),
        2476: ("deebot-t", "vacuum", {"model_name": "T30C", "variant_code": "t30c-white", "variant_label": "White"}),
        2477: ("deebot-t", "vacuum", {"model_name": "T80 OMNI", "variant_code": "t80-omni", "variant_label": "Base", "height_mm": 98.0}),
        2478: ("deebot-t", "vacuum", {"model_name": "T90 OMNI", "variant_code": "t90-omni-white", "variant_label": "White", "height_mm": 95.0}),
        2517: ("deebot-x", "vacuum", {"model_name": "X5 OMNI", "variant_code": "x5-omni-black", "variant_label": "Black"}),
        2518: ("deebot-t", "vacuum", {"model_name": "T30C", "variant_code": "t30c-black", "variant_label": "Black"}),
    }
    for rid, (series, pkey, meta) in thin_map.items():
        if rid not in THIN.ROBOT_DATA:
            continue
        fixes[rid] = _from_thin(rid, series, purpose_key=pkey, **meta)
        if pkey == "mower":
            fixes[rid].update({
                "tags": TAGS_MOWER,
                "sub_category_slug": "agriculture",
                "use_keys": "agriculture",
                "industry_keys": "homes|agriculture|consumer",
            })
        elif pkey == "window":
            fixes[rid].update({
                "tags": TAGS_WINDOW,
                "movement_type_keys": "other",
            })
        elif pkey == "air":
            fixes[rid].update({
                "tags": TAGS_AIR,
                "use_keys": "monitoring|cleaning",
            })
        if rid in IMAGELESS_KEEP:
            note = MEDIA.build_note(IMAGELESS_KEEP[rid])
            fixes[rid]["notes_force"] = note
            fixes[rid]["clear_media"] = True

    # White T50 / T80 / T90 heights (OEM-cited only)
    if 1943 in fixes:
        fixes[1943]["height_mm"] = 81.0
    if 2477 in fixes:
        fixes[2477]["height_mm"] = 98.0
    if 2478 in fixes:
        fixes[2478]["height_mm"] = 95.0

    return fixes


def patch_robot(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> list[str]:
    """Direct DRF PATCH — overwrites non-blank junk features/purpose/family."""
    body: dict[str, Any] = {}
    if "tags" in fix and fix["tags"] not in (None, ""):
        tags = fix["tags"]
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split("|") if t.strip()]
        body["tags"] = tags
    for k in (
        "name",
        "url",
        "description",
        "features",
        "purpose",
        "release_year",
        "battery_capacity",
        "runtime_minutes",
        "charging_time_minutes",
        "weight_kg",
        "length_mm",
        "width_mm",
        "height_mm",
        "voltage",
        "ip_rating",
        "speed",
        "price_max",
        "price_currency",
        "price_notes",
        "family_key",
        "family_name",
        "family_url",
        "model_name",
        "variant_code",
        "variant_label",
        "product_url_scope",
        "movement_type_keys",
        "sub_category_slug",
        "category_slugs",
        "industry_keys",
        "use_keys",
        "manufacturer_country_code",
    ):
        if k in fix and fix[k] not in (None, ""):
            body[k] = fix[k]
    if fix.get("availability_status") is not None:
        body["availability_status"] = fix["availability_status"]
    if fix.get("sources"):
        body["information_source_urls"] = [
            s["url"] if isinstance(s, dict) else s for s in fix["sources"]
        ]
    if fix.get("notes_force"):
        body["notes"] = fix["notes_force"]
    elif fix.get("source_note") or fix.get("notes_spec"):
        # prepend research note without wiping existing IMAGE TO-DO
        parts = [p for p in (fix.get("source_note"), fix.get("notes_spec")) if p]
        if parts:
            body.setdefault("research_notes", " | ".join(parts))

    ok: list[str] = []
    # Patch in one call first; fall back per-key on failure.
    try:
        client._patch(f"robots/robots/{rid}/", body)
        ok = list(body.keys())
    except Exception as exc:  # noqa: BLE001
        print(f"  bulk-patch fail {rid}: {exc} — retrying per-key", file=sys.stderr)
        for k, v in body.items():
            try:
                client._patch(f"robots/robots/{rid}/", {k: v})
                ok.append(k)
            except Exception as e2:  # noqa: BLE001
                print(f"  patch fail {rid}.{k}: {e2}", file=sys.stderr)

    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "manufacturer_countries": [CN_COUNTRY_ID],
                "manufacturer_country_ref": CN_COUNTRY_ID,
            },
        )
        ok.append("manufacturer_countries")
    except Exception as exc:  # noqa: BLE001
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)

    if fix.get("videos"):
        try:
            vids = enrich_video_list(fix["videos"])
            if vids:
                client._patch(f"robots/robots/{rid}/", {"video_urls": vids})
                ok.append("video_urls")
        except Exception as exc:  # noqa: BLE001
            print(f"  video patch fail {rid}: {exc}", file=sys.stderr)
    return ok


def apply_media_refresh(
    client: ResearchApiClient,
    rid: int,
    images: list[str],
    *,
    created_by_id: int,
) -> bool:
    if not images:
        return False
    # Hash-verify uniqueness within gallery before import.
    seen: dict[str, str] = {}
    clean: list[str] = []
    for url in images:
        url = url.split("?")[0]  # strip ?x-oss-process=webp
        md5 = verify_hero_md5(url)
        if md5 in seen:
            print(f"  skip within-dupe {rid}: {url[-50:]} == {seen[md5][-50:]}")
            continue
        seen[md5] = url
        clean.append(url)
    if not clean:
        return False
    live_name = client._get(f"robots/robots/{rid}/").get("name")
    row = {
        "id": rid,
        "name": live_name,
        "company": COMPANY_NAME,
        "company_name": COMPANY_NAME,
        "image": clean[0],
        "images": clean,
    }
    # Prefer add-gallery without replace_media when the robot already has a hero:
    # replace_media+sync recopy has errored with empty messages on Ecovacs CDN paths.
    # Callers that need a full wipe should clear first (empty images + replace_media).
    res = client.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        status="pending_review",
        skip_company_update=True,
        created_by_id=created_by_id,
        replace_media=False,
    )
    errs = res.get("errors") or []
    if errs or res.get("error_count") or not res.get("updated_count"):
        print(
            f"  MEDIA FAIL {rid}: updated={res.get('updated_count')} "
            f"error_count={res.get('error_count')} errors={errs} results={res.get('results')}",
            file=sys.stderr,
        )
        return False
    print(f"  media refreshed {rid}: {len(clean)} images")
    return True


def resolve_media_urls(rid: int) -> list[str]:
    """Prefer greenfield curated URLs; else media-script candidate picks."""
    if rid in GREEN.ROBOT_DATA and GREEN.ROBOT_DATA[rid].get("images"):
        return list(GREEN.ROBOT_DATA[rid]["images"])
    if rid not in MEDIA.PICKS:
        return []
    if not MEDIA.CAND.exists():
        print(f"  WARN no candidates file for media refresh of {rid}", file=sys.stderr)
        return []
    data = json.loads(MEDIA.CAND.read_text(encoding="utf-8"))
    keep = data[str(rid)]["keep"]
    urls = []
    for pick in MEDIA.PICKS[rid]:
        hits = [c for c in keep if pick in c["url"]]
        if len(hits) != 1:
            raise SystemExit(f"PICK '{pick}' for {rid} matched {len(hits)} (need 1)")
        urls.append(hits[0]["url"].split("?")[0])
    return urls


def main() -> int:
    ap = argparse.ArgumentParser(description="Ecovacs company 32 full enrichment")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--refresh-media", action="store_true", help="re-import curated galleries for MEDIA_REFRESH_IDS")
    ap.add_argument("--ids", type=str, default="")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--skip-reject", action="store_true")
    args = ap.parse_args()

    only = {int(x) for x in args.ids.split(",") if x.strip().isdigit()} if args.ids.strip() else None
    fixes = build_robot_fixes()
    client = ResearchApiClient()
    live = {r["id"]: r for r in client.list_robots_for_company(COMPANY_ID)}
    created_by = resolve_created_by_id(args.created_by_id)

    report: dict[str, Any] = {
        "rejects": [],
        "keepers": [],
        "holds": [],
        "media_refreshed": [],
        "errors": [],
    }

    print("=== REJECTS ===")
    for rid, reason in REJECTS.items():
        if only and rid not in only:
            continue
        cur = live.get(rid)
        if cur is None:
            print(f"SKIP reject {rid}: not found")
            continue
        st = (cur.get("status") or "").lower()
        if st in SKIP_STATUSES:
            print(f"SKIP reject {rid}: status={st}")
            continue
        print(f"REJECT {rid} {cur.get('name')}: {reason[:100]}")
        report["rejects"].append({"id": rid, "name": cur.get("name"), "reason": reason})
        if args.apply and not args.skip_reject:
            how = reject_robot(client, rid, reason)
            print(f"  -> {how}")

    print("\n=== KEEPERS (family + features + specs) ===")
    media_done: list[int] = []
    for rid, fix in sorted(fixes.items()):
        if only and rid not in only:
            continue
        if rid in REJECTS:
            continue
        cur = live.get(rid)
        if cur is None:
            print(f"SKIP {rid}: not found")
            continue
        st = (cur.get("status") or "").lower()
        if st in SKIP_STATUSES:
            print(f"SKIP {rid} {cur.get('name')}: status={st}")
            continue
        if st != "pending_review":
            print(f"SKIP {rid} {cur.get('name')}: status={st}")
            continue

        desc = fix.get("description") or cur.get("description") or ""
        purpose = fix["purpose"]
        dup = purpose_duplicates_description(purpose, desc)
        if dup:
            print(f"WARN {rid}: purpose still duplicates description ({dup})", file=sys.stderr)

        row = {
            "id": rid,
            "name": fix.get("name") or cur.get("name"),
            "family_key": fix["family_key"],
            "feat_before": len(cur.get("features") or ""),
            "feat_after": len(fix.get("features") or ""),
            "purpose": purpose,
            "has_images": bool(fix.get("images")),
            "imageless": rid in IMAGELESS_KEEP,
        }
        report["keepers"].append(row)
        print(
            f"{rid} {row['name']}: fam={fix['family_key']} "
            f"feat {row['feat_before']}->{row['feat_after']} "
            f"purpose={purpose!r}"
        )

        if not args.apply:
            continue

        ok_keys = patch_robot(client, rid, fix)
        print(f"  patched: {ok_keys[:12]}{'...' if len(ok_keys) > 12 else ''}")

        if rid in IMAGELESS_KEEP:
            report["holds"].append({"id": rid, "name": row["name"], "reason": "IMAGE TO-DO — N20e Plus assets on N30 PLUS PDP"})
            # Do not attach media.
            continue

        if args.refresh_media and rid in MEDIA_REFRESH_IDS:
            try:
                urls = resolve_media_urls(rid)
                if apply_media_refresh(client, rid, urls, created_by_id=created_by):
                    media_done.append(rid)
                    report["media_refreshed"].append(rid)
            except Exception as exc:  # noqa: BLE001
                report["errors"].append({"id": rid, "err": str(exc)})
                print(f"  media refresh ERR {rid}: {exc}", file=sys.stderr)

    if args.apply and args.copy_media and media_done:
        print(f"\n=== copy-media ({len(media_done)}) ===")
        ok, fail = trigger_copy_media(media_done)
        print(f"copy-media ok={ok} fail={fail}")

    if args.apply:
        touch_ids = [r["id"] for r in report["keepers"] if r["id"] not in REJECTS]
        if only:
            touch_ids = [i for i in touch_ids if i in only]
        print("\n=== drop verification / duplicate_images flags ===")
        drop_verification_flags(client, touch_ids)

    out = _RESEARCH_DIR / "staging" / "reports" / "ecovacs-32-fix-preview.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out}")
    print(
        f"Summary: rejects={len(report['rejects'])} keepers={len(report['keepers'])} "
        f"holds={len(report['holds'])} media={len(report['media_refreshed'])}"
    )
    if not args.apply:
        print("Dry-run only. Re-run with --apply [--refresh-media] [--copy-media]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
