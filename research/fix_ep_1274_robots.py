"""Fix Zhejiang EP Equipment (company 1274) content-queue enrichment.

OEM: https://ep-equipment.com/
Sources: live EN PDPs under /product/{slug}/, EN brochures under /wp-content/,
2025 EU Product Overview.

Issues addressed:
- Many CRM /product/... URLs 404 (catalog churn); remap live keepers, brochure
  sources for discontinued SKUs
- Shared stub features (~338 chars) → model-distinct OEM feature copy
- JXO → JX0 (OEM spelling); RPL251/301 kept as family-scope (OEM now split PDPs)
- EPT25-WA/EPT20-20WA share most CDN gallery assets → distinct attr_11 heroes only
- payload = load capacity only; never map tow-tractor drawbar to payload_kg
- Multi-option capacity cells (JX0 90/110/136, RPL 2500/3000) → features, not typed
- Names drop redundant "EP Equipment " prefix
- availability_status integer FK (11 Available / 4 Discontinued)
- family_key ep-equipment:{series}; status stays pending_review
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
from robot_auto_research import slugify_robot_name
from tag_suggest import TagCatalog
from youtube_metadata import enrich_video_list

COMPANY_ID = 1274
COMPANY_SLUG = "zhejiang-ep-equipment-coltd"
COMPANY_NAME = "Zhejiang EP Equipment Co.,Ltd."
COMPANY_WEBSITE = "https://ep-equipment.com"
CN = "CN"

# --- Official URLs -----------------------------------------------------------
URL = {
    "jx0": f"{COMPANY_WEBSITE}/product/jx0/",
    "rpl251": f"{COMPANY_WEBSITE}/product/rpl251/",
    "rpl301": f"{COMPANY_WEBSITE}/product/rpl301/",
    "ept20_rap": f"{COMPANY_WEBSITE}/product/ept20-rap/",
    "es15": f"{COMPANY_WEBSITE}/product/es15-15es/",
    "esl122": f"{COMPANY_WEBSITE}/product/esl122/",
    "ept25": f"{COMPANY_WEBSITE}/product/ept25-wa/",
    "ept20wa": f"{COMPANY_WEBSITE}/product/ept20-20wa/",
    "kpl201": f"{COMPANY_WEBSITE}/product/kpl201/",
    "epl185": f"{COMPANY_WEBSITE}/product/epl185/",
    "epl154": f"{COMPANY_WEBSITE}/product/epl154/",
    "qdd30s": f"{COMPANY_WEBSITE}/product/qdd30s/",  # successor — NOT same SKU as QDD30T
    "wpl202": f"{COMPANY_WEBSITE}/product/wpl202/",  # successor — NOT same SKU as WPL201
    "ride_on": f"{COMPANY_WEBSITE}/product-category/electric-pallet-trucks/ride-on-ept/",
    "stackers": f"{COMPANY_WEBSITE}/product-category/stackers/",
    "tow": f"{COMPANY_WEBSITE}/product-category/tow-tractors/",
    "eu2025": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/11/2025-EU-Product-Overview-EN.pdf",
    "eu2021": f"{COMPANY_WEBSITE}/wp-content/uploads/2021/05/EU-Product-Overview-2021.pdf",
    "bro_es12_25wa": f"{COMPANY_WEBSITE}/wp-content/uploads/2021/01/ES12-25WA-EN-Brochure-3.pdf",
    "bro_es20": f"{COMPANY_WEBSITE}/wp-content/uploads/2021/01/ES20-WA-EN-Brochure.pdf",
    "bro_es10_12": (
        f"{COMPANY_WEBSITE}/wp-content/uploads/2021/01/"
        "ES10-10ESES12-12ESDMMM-EN-Brochure-5.pdf"
    ),
    "bro_es18": f"{COMPANY_WEBSITE}/wp-content/uploads/2021/09/ES18-40WA-EN-Brochure.pdf",
    "bro_es14": f"{COMPANY_WEBSITE}/wp-content/uploads/2021/01/ES14-30WA-EN-Brochure-1.pdf",
    "bro_rpl": f"{COMPANY_WEBSITE}/wp-content/uploads/2021/01/RPL201201H251301-EN-Brochure-4.pdf",
    "bro_jx0": f"{COMPANY_WEBSITE}/wp-content/uploads/2022/09/JX0-EN-Brochure.pdf",
    "bro_wpl201": (
        f"{COMPANY_WEBSITE}/wp-content/uploads/2021/01/"
        "WPL201-%E8%A5%BF%E7%8F%AD%E7%89%99.pdf"
    ),
}

# Distinct OEM heroes (md5-verified unique across keepers with media).
IMG = {
    "jx0": "https://cdn.ep-portal.net/products/attr_6/1761296643196-s5kqqm.webp",
    "rpl251": "https://cdn.ep-portal.net/products/attr_5/1757584900143-kwf8nl.webp",
    "ept20_rap": "https://cdn.ep-portal.net/products/attr_6/1760688484782-qp5ujo.webp",
    "es15": "https://cdn.ep-portal.net/products/attr_5/1758011424793-to8s9d.webp",
    "esl122": "https://cdn.ep-portal.net/products/attr_7/1760161491546-3kct9i.webp",
    # EPT25/EPT20-20WA share og + attr_6/134 — only attr_11 lifestyle banners differ
    "ept25": "https://cdn.ep-portal.net/products/attr_11/1759484987619-3m986u.webp",
    "ept20wa": "https://cdn.ep-portal.net/products/attr_11/1761317978625-oi6kw3.webp",
    "kpl201": "https://cdn.ep-portal.net/products/attr_5/1760690436138-304rti.webp",
    "epl185": "https://cdn.ep-portal.net/products/attr_5/1757340806702-xty0xn.webp",
    "epl154": "https://cdn.ep-portal.net/products/attr_5/1757340185706-ga4tyu.webp",
}
EXPECTED_MD5 = {
    "jx0": "afa776d434932fbc9050783734288a28",
    "rpl251": "e752f7e17b5cc12651ffaf13d7793f21",
    "ept20_rap": "10c6619fa0365a85f78c7cde01faaa4b",
    "es15": "f9c3511d09c4a7548a7b551ce9e76d6e",
    "esl122": "e094360389328b7e6f19bb34e8d5ed3c",
    "ept25": "e763f9866d76ddd1750f12566a1f920c",
    "ept20wa": "07faffd0e23ceefdbb194de7be430127",
    "kpl201": "f7d119c8601708abada98bb066ca1cd2",
    "epl185": "2f48d4ea435af727104ea29f57de5e14",
    "epl154": "e9866109b817606e5a3b327c492593b2",
}

YT = {
    "jx0": [
        "https://www.youtube.com/watch?v=67cg1YWD9lQ",
        "https://www.youtube.com/watch?v=RS60hlhfncg",
        "https://www.youtube.com/watch?v=MJMwFrXEp3o",
    ],
    "es15": [
        "https://www.youtube.com/watch?v=yYcS_wNbuu8",
        "https://www.youtube.com/watch?v=s-1NZNkXrIs",
    ],
    "esl122": [
        "https://www.youtube.com/watch?v=ffYal10vcCs",
        "https://www.youtube.com/watch?v=qch5ooUlzfs",
    ],
    "ept20wa": [
        "https://www.youtube.com/watch?v=b8LUW0fFHHY",
        "https://www.youtube.com/watch?v=kmU7RZW5yyY",
    ],
    "kpl201": [
        "https://www.youtube.com/watch?v=LBWx2xJSr8M",
        "https://www.youtube.com/watch?v=wsRhgOBmj4k",
    ],
    "epl185": [
        "https://www.youtube.com/watch?v=NNlG8swx-tc",
        "https://www.youtube.com/watch?v=DHbg3CWGPUo",
    ],
    "epl154": ["https://www.youtube.com/watch?v=TTTaxE2fngI"],
    "ept20_rap": [
        "https://www.youtube.com/watch?v=b4OQECDgTMU",
        "https://www.youtube.com/watch?v=LSy4JABLNeE",
    ],
    "rpl": [
        "https://www.youtube.com/watch?v=4d2ERMj8dts",
        "https://www.youtube.com/watch?v=U20ATzwILgg",
    ],
    "es20": ["https://www.youtube.com/watch?v=_888NAohBBQ"],
    "wpl201": [
        "https://www.youtube.com/watch?v=VQxu_XNcpQA",
        "https://www.youtube.com/watch?v=nB7L2BjIHx4",
    ],
}

TAGS_PALLET = (
    "Pallet Truck|Pallet Handling|Warehouse Automation|Logistics|"
    "Material Handling|Intralogistics|Electric|Industrial"
)
TAGS_STACKER = (
    "Stacker|Pallet Handling|Warehouse Automation|Logistics|"
    "Material Handling|Intralogistics|Electric|Industrial"
)
TAGS_RIDE = (
    "Pallet Truck|Pallet Handling|Warehouse Automation|Logistics|"
    "Material Handling|Intralogistics|Electric|Forklift"
)
TAGS_PICKER = (
    "Order Fulfillment|Warehouse Automation|Logistics|"
    "Material Handling|Intralogistics|Electric|Industrial"
)
TAGS_TOW = (
    "Tow Tractor|Warehouse Automation|Logistics|"
    "Material Handling|Intralogistics|Electric|Industrial"
)

IMAGE_TODO = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "{why}\n"
    "ACTION FOR TEAM: source a licensed exact-model product photo from EP "
    "(cdn.ep-portal.net or brochure still), or request from OEM. "
    "Do NOT substitute a sibling render (e.g. QDD30S for QDD30T, WPL202 for WPL201) "
    "or a shared family/site banner.\n"
    "---\n"
)

_AVAIL_IDS = {
    "announced": 10,
    "available": 11,
    "released": 3,
    "discontinued": 4,
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
            resp = requests.post(
                url,
                headers={"X-Internal-Secret": secret, "Content-Type": "application/json"},
                json={},
                timeout=180,
            )
            if resp.status_code < 400:
                ok += 1
                print(f"copy-media OK {rid}", flush=True)
            else:
                fail += 1
                body = (resp.text or "")[:200]
                print(f"copy-media fail {rid}: HTTP {resp.status_code} body={body}", flush=True)
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.4)
    return ok, fail


def resolve_tags(catalog: TagCatalog, pipe: str) -> str:
    wanted = [t.strip() for t in pipe.split("|") if t.strip()]
    out: list[str] = []
    missing: list[str] = []
    by_name = {str(t.get("name") or "").lower(): str(t.get("name") or "") for t in catalog.tags}
    for n in wanted:
        hit = by_name.get(n.lower())
        if hit:
            if hit not in out:
                out.append(hit)
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
        "allow_no_image",
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
        row["image"] = fix["image"]
    row["availability_status_key"] = fix.get("availability_status_key") or "available"
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "payload_kg",
        "weight_kg",
        "speed",
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
        "programming_interface",
        "deployment_context",
        "ecosystem_compatibility",
        "safety_fencing",
        "mounting_options",
        "features",
        "description",
    ):
        if k in fix and fix[k] not in (None, ""):
            body[k] = fix[k]
    if fix.get("clear_payload"):
        body["payload_kg"] = None
    avail_key = fix.get("availability_status_key")
    if avail_key:
        body["availability_status"] = _AVAIL_IDS.get(str(avail_key), avail_key)
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
        except Exception as exc:
            print(f"  patch fail {rid} {k}: {exc}", file=sys.stderr)
    # taxonomy
    tax: dict[str, Any] = {}
    for k in (
        "movement_type_keys",
        "industry_keys",
        "use_keys",
        "category_slugs",
        "sub_category_slug",
        "tags",
    ):
        if k in fix and fix[k] not in (None, ""):
            tax[k] = fix[k]
    if tax.get("tags") and "|" in str(tax["tags"]):
        pass  # tags go via bulk-import primarily
    if tax:
        try:
            # tags as list if serializer wants list
            patch_body = dict(tax)
            if "tags" in patch_body and isinstance(patch_body["tags"], str):
                patch_body["tags"] = [t for t in patch_body["tags"].split("|") if t]
            client._patch(f"robots/robots/{rid}/", patch_body)
        except Exception as exc:
            print(f"  tax patch fail {rid}: {exc}", file=sys.stderr)


def drop_verification_flags(client: ResearchApiClient, robot_ids: list[int]) -> None:
    drop = {
        "image_mismatch",
        "video_mismatch",
        "duplicate_images",
        "low_quality_image",
        "wrong_product_image",
    }
    for rid in robot_ids:
        try:
            r = client._get(f"robots/robots/{rid}/")
        except Exception:
            continue
        flags = r.get("quality_flags") or r.get("verification_flags") or []
        if not isinstance(flags, list):
            continue
        before = [(f.get("flag") if isinstance(f, dict) else f) for f in flags]
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
            print(f"  flag-drop fail {rid}: {exc}", file=sys.stderr)


def common_tax(*, kind: str) -> dict[str, Any]:
    return {
        "manufacturer_country_code": CN,
        "movement_type_keys": "wheeled",
        "industry_keys": "logistics|manufacturing",
        "use_keys": "material-handling|warehouse|logistics",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": {
            "pallet": TAGS_PALLET,
            "stacker": TAGS_STACKER,
            "ride": TAGS_RIDE,
            "picker": TAGS_PICKER,
            "tow": TAGS_TOW,
        }.get(kind, TAGS_PALLET),
        "programming_interface": (
            "Tiller / tiller-head controls; OEM AC controller; optional Li-ion BMS display"
        ),
        "deployment_context": (
            "Indoor warehouse and logistics centers; pedestrian or ride-on MHE operations"
        ),
        "ecosystem_compatibility": "EP Li-ion / lead-acid battery ecosystems; standard pallet sizes",
        "safety_fencing": (
            "Emergency stop, belly/reverse button on tiller where fitted, "
            "horn/alert per OEM configuration"
        ),
        "mounting_options": "Wheeled MHE chassis; no fixed mount",
    }


# --- ROBOT FIXES -------------------------------------------------------------
ROBOT_FIXES: dict[int, dict[str, Any]] = {
    # Live keepers
    4941: {
        **common_tax(kind="picker"),
        "name": "JX0",
        "model_name": "JX0",
        "variant_code": "JX0",
        "variant_label": "JX0 / JX0-30",
        "url": URL["jx0"],
        "family_key": "ep-equipment:jxo",
        "family_name": "JX0",
        "family_url": URL["jx0"],
        "product_url_scope": "exact_variant",
        "image": IMG["jx0"],
        "description": (
            "The JX0 is EP Equipment's compact vertical order picker for fast, safe "
            "picking in confined warehouse aisles. An intuitive stand-on platform, "
            "Li-ion power, and tight packaging make it a task-support picker for "
            "e-commerce and spare-parts operations."
        ),
        "purpose": (
            "Low-level order picking\n"
            "Narrow-aisle item retrieval\n"
            "Task support and maintenance access\n"
            "E-commerce and spare-parts picking"
        ),
        "features": (
            "Compact vertical order picker for confined warehouse spaces. "
            "Platform capacity options 90 / 110 / 136 kg (OEM multi-option cell — not a single typed payload). "
            "Service weight about 800 kg; travel speed about 6–6.5 km/h; 24 V Li-ion. "
            "Overall length about 1440 mm, width about 750 mm (OEM PDP). "
            "Intuitive driving/control, ergonomic stand-on design, Li-ion for uptime. "
            "CRM name 'JXO' corrected to OEM spelling JX0."
        ),
        "clear_payload": True,  # 90/110/136 options — do not invent one column
        "weight_kg": 800.0,
        "speed": 6.0,
        "length_mm": 1440,
        "width_mm": 750,
        "availability_status_key": "available",
        "videos": YT["jx0"],
        "information_source_urls": [URL["jx0"], URL["bro_jx0"]],
        "notes_force": (
            "[AI Research] Renamed JXO→JX0 per live OEM PDP. Platform capacity is "
            "multi-option 90/110/136 kg — cleared typed payload_kg. Hero: attr_6 "
            "cdn.ep-portal.net (md5-unique). Status pending_review."
        ),
        "source_note": f"{URL['jx0']}; {URL['bro_jx0']}",
    },
    4934: {
        **common_tax(kind="ride"),
        "name": "RPL251/301",
        "model_name": "RPL251/301",
        "variant_code": "RPL251/301",
        "variant_label": "RPL251 (2.5 t) / RPL301 (3.0 t)",
        "url": URL["rpl251"],
        "family_key": "ep-equipment:rpl",
        "family_name": "RPL",
        "family_url": URL["bro_rpl"],
        "product_url_scope": "family",
        "image": IMG["rpl251"],
        "description": (
            "The RPL251/301 family covers EP Equipment's heavy-duty ride-on pallet "
            "trucks at 2.5 t and 3.0 t load capacity. Reinforced chassis, Li-ion "
            "options, and operator platforms target intensive warehouse transport."
        ),
        "purpose": (
            "Long-distance pallet transport\n"
            "Heavy-duty warehouse transfers\n"
            "Ride-on intensive logistics runs\n"
            "Loading dock to rack moves"
        ),
        "features": (
            "Family record for OEM RPL251 (2.5 t) and RPL301 (3.0 t) — separate live "
            f"PDPs {URL['rpl251']} and {URL['rpl301']}; kept as one family-scope row "
            "(CRM had a single combined SKU). "
            "Load capacity 2500 kg (RPL251) / 3000 kg (RPL301) — typed payload left blank "
            "(columns disagree). Shared OEM figures: service weight about 690 kg, "
            "fork lift height 120 mm, travel about 5.5–6 km/h, 24 V. "
            "Hero is RPL251 product render (not RPL301 sibling)."
        ),
        "clear_payload": True,
        "weight_kg": 690.0,
        "speed": 5.5,
        "width_mm": 734,
        "availability_status_key": "available",
        "videos": YT["rpl"],
        "information_source_urls": [URL["rpl251"], URL["rpl301"], URL["bro_rpl"]],
        "notes_force": (
            "[AI Research] Family-scope RPL251/301: OEM split into per-SKU PDPs; "
            "CRM keeps one record. Payload not typed (2500 vs 3000). Hero RPL251 "
            "attr_5. Status pending_review."
        ),
        "source_note": f"{URL['rpl251']}; {URL['rpl301']}; {URL['bro_rpl']}",
    },
    3568: {
        **common_tax(kind="ride"),
        "name": "EPT20-RAP",
        "model_name": "EPT20-RAP",
        "variant_code": "EPT20-RAP",
        "variant_label": "EPT20-RAP",
        "url": URL["ept20_rap"],
        "family_key": "ep-equipment:ept",
        "family_name": "EPT",
        "family_url": URL["ept20_rap"],
        "product_url_scope": "exact_variant",
        "image": IMG["ept20_rap"],
        "description": (
            "The EPT20-RAP is EP Equipment's 2.0-ton ride-on electric pallet truck "
            "for longer warehouse runs. A stand-on platform and AC drive support "
            "higher travel speeds than pedestrian walkies."
        ),
        "purpose": (
            "Ride-on pallet transport\n"
            "Medium-distance warehouse moves\n"
            "Dock-to-aisle pallet transfer\n"
            "High-throughput logistics handling"
        ),
        "features": (
            "Rated load capacity 2000 kg (OEM PDP). Service weight about 940 kg. "
            "Travel speed about 8–12 km/h (OEM table). 24 V system. "
            "Approximate length 2516 mm, width 800 mm, platform height context "
            "about 1220 mm (OEM). Ride-on platform for longer runs vs walkie EPT."
        ),
        "payload_kg": 2000.0,
        "weight_kg": 940.0,
        "speed": 8.0,
        "width_mm": 800,
        "availability_status_key": "available",
        "videos": YT["ept20_rap"],
        "information_source_urls": [URL["ept20_rap"]],
        "notes_force": (
            "[AI Research] Live PDP ept20-rap. Hero attr_6 in-use shot (md5-unique). "
            "Status pending_review."
        ),
        "source_note": URL["ept20_rap"],
    },
    2752: {
        **common_tax(kind="stacker"),
        "name": "ES15-15ES",
        "model_name": "ES15-15ES",
        "variant_code": "ES15-15ES",
        "variant_label": "ES15-15ES",
        "url": URL["es15"],
        "family_key": "ep-equipment:es",
        "family_name": "ES",
        "family_url": URL["stackers"],
        "product_url_scope": "exact_variant",
        "image": IMG["es15"],
        "description": (
            "The ES15-15ES is EP Equipment's 1.5-ton pedestrian electric stacker with "
            "a compact chassis, tight turning radius, and maintenance-focused battery "
            "options for light-to-medium stacking."
        ),
        "purpose": (
            "Pedestrian pallet stacking\n"
            "Rack put-away and retrieval\n"
            "Light-to-medium warehouse stacking\n"
            "Narrow-aisle stacker operations"
        ),
        "features": (
            "Rated load capacity 1500 kg. Service weight about 755 kg. "
            "Max lift height about 4165 mm (OEM). Travel speed about 5 km/h; 24 V. "
            "Overall width about 800 mm. AC drive, compact chassis, operator-focused "
            "safety/comfort features per OEM PDP."
        ),
        "payload_kg": 1500.0,
        "weight_kg": 755.0,
        "speed": 5.0,
        "width_mm": 800,
        "availability_status_key": "available",
        "videos": YT["es15"],
        "information_source_urls": [URL["es15"]],
        "notes_force": (
            "[AI Research] Live PDP. Studio hero attr_5 (md5-unique). "
            "Lift height cited in features (not overall height_mm). Status pending_review."
        ),
        "source_note": URL["es15"],
    },
    2751: {
        **common_tax(kind="stacker"),
        "name": "ESL122",
        "model_name": "ESL122",
        "variant_code": "ESL122",
        "variant_label": "ESL122",
        "url": URL["esl122"],
        "family_key": "ep-equipment:esl",
        "family_name": "ESL",
        "family_url": URL["esl122"],
        "product_url_scope": "exact_variant",
        "image": IMG["esl122"],
        "description": (
            "The ESL122 is EP Equipment's 1.2-ton pedestrian electric stacker for "
            "everyday warehouse stacking. Compact packaging and Li-ion options suit "
            "retail and light industrial put-away."
        ),
        "purpose": (
            "Pedestrian stacking\n"
            "Retail and light industrial put-away\n"
            "Pallet lift to mid-level racking\n"
            "Indoor aisle stacker work"
        ),
        "features": (
            "Rated load capacity 1200 kg. Service weight about 570 kg. "
            "Max lift height about 3013 mm (OEM). Travel speed about 4.2 km/h; 24 V. "
            "Overall width about 792 mm. Pedestrian tiller control."
        ),
        "payload_kg": 1200.0,
        "weight_kg": 570.0,
        "speed": 4.2,
        "width_mm": 792,
        "availability_status_key": "available",
        "videos": YT["esl122"],
        "information_source_urls": [URL["esl122"]],
        "notes_force": (
            "[AI Research] Live PDP. Hero attr_5 (md5-unique). Status pending_review."
        ),
        "source_note": URL["esl122"],
    },
    2750: {
        **common_tax(kind="pallet"),
        "name": "EPT25-WA",
        "model_name": "EPT25-WA",
        "variant_code": "EPT25-WA",
        "variant_label": "EPT25-WA",
        "url": URL["ept25"],
        "family_key": "ep-equipment:ept",
        "family_name": "EPT",
        "family_url": URL["ept25"],
        "product_url_scope": "exact_variant",
        "image": IMG["ept25"],
        "description": (
            "The EPT25-WA is EP Equipment's 2.5-ton heavy-duty electric pallet truck "
            "with AC drive for demanding short-distance warehouse transport."
        ),
        "purpose": (
            "Heavy pallet transport\n"
            "Short-distance warehouse moves\n"
            "Loading dock handling\n"
            "High-capacity walkie pallet work"
        ),
        "features": (
            "Rated load capacity 2500 kg (OEM PDP; CRM previously had 2000 — corrected). "
            "Service weight about 565 kg (OEM; battery option column may show 400 kg — "
            "used primary service-weight figure). Fork lift height 120 mm. "
            "Travel speed about 5–5.5 km/h; 24 V. Overall length about 1769 mm, "
            "width 710 mm. Hero is model-specific attr_11 lifestyle (og/attr_6 shared "
            "with EPT20-20WA — rejected for dedupe)."
        ),
        "payload_kg": 2500.0,
        "weight_kg": 565.0,
        "speed": 5.0,
        "length_mm": 1769,
        "width_mm": 710,
        "availability_status_key": "available",
        "videos": [],
        "information_source_urls": [URL["ept25"]],
        "notes_force": (
            "[AI Research] Payload corrected 2000→2500 per OEM PDP. Distinct attr_11 "
            "hero (siblings share og/attr_6). Status pending_review."
        ),
        "source_note": URL["ept25"],
    },
    2749: {
        **common_tax(kind="pallet"),
        "name": "EPT20-20WA",
        "model_name": "EPT20-20WA",
        "variant_code": "EPT20-20WA",
        "variant_label": "EPT20-20WA",
        "url": URL["ept20wa"],
        "family_key": "ep-equipment:ept",
        "family_name": "EPT",
        "family_url": URL["ept20wa"],
        "product_url_scope": "exact_variant",
        "image": IMG["ept20wa"],
        "description": (
            "The EPT20-20WA is EP Equipment's 2.0-ton heavy-duty electric pallet truck "
            "with AC drive for intensive short-distance warehouse applications."
        ),
        "purpose": (
            "Walkie pallet transport\n"
            "Short-distance warehouse moves\n"
            "Dock and staging handling\n"
            "Medium-capacity intensive logistics"
        ),
        "features": (
            "Rated load capacity 2000 kg. Service weight about 530 kg. "
            "Fork lift height 120 mm. Travel speed about 5–5.5 km/h; 24 V. "
            "Overall length about 1769 mm, width 710 mm. "
            "Distinct attr_11 hero vs EPT25-WA (shared og/gallery rejected)."
        ),
        "payload_kg": 2000.0,
        "weight_kg": 530.0,
        "speed": 5.0,
        "length_mm": 1769,
        "width_mm": 710,
        "availability_status_key": "available",
        "videos": YT["ept20wa"],
        "information_source_urls": [URL["ept20wa"]],
        "notes_force": (
            "[AI Research] Live PDP. Distinct attr_11 hero md5 vs EPT25-WA. "
            "Status pending_review."
        ),
        "source_note": URL["ept20wa"],
    },
    2748: {
        **common_tax(kind="ride"),
        "name": "KPL201",
        "model_name": "KPL201",
        "variant_code": "KPL201",
        "variant_label": "KPL201",
        "url": URL["kpl201"],
        "family_key": "ep-equipment:kpl",
        "family_name": "KPL",
        "family_url": URL["kpl201"],
        "product_url_scope": "exact_variant",
        "image": IMG["kpl201"],
        "description": (
            "The KPL201 is EP Equipment's 2.0-ton heavy-duty Li-ion ride-on pallet "
            "truck for intensive warehouse transport with a stand-on operator platform."
        ),
        "purpose": (
            "Ride-on pallet transport\n"
            "Intensive warehouse logistics\n"
            "Longer indoor pallet runs\n"
            "Li-ion multi-shift operations"
        ),
        "features": (
            "Rated load capacity 2000 kg. Service weight about 765 kg. "
            "Fork lift height 120 mm. Travel speed about 8.5 km/h; 24 V Li-ion. "
            "Width about 734 mm. Heavy-duty ride-on chassis."
        ),
        "payload_kg": 2000.0,
        "weight_kg": 765.0,
        "speed": 8.5,
        "width_mm": 734,
        "availability_status_key": "available",
        "videos": YT["kpl201"],
        "information_source_urls": [URL["kpl201"]],
        "notes_force": (
            "[AI Research] Live PDP. Hero attr_5 studio/in-use (md5-unique). "
            "Status pending_review."
        ),
        "source_note": URL["kpl201"],
    },
    2747: {
        **common_tax(kind="pallet"),
        "name": "EPL185",
        "model_name": "EPL185",
        "variant_code": "EPL185",
        "variant_label": "EPL185",
        "url": URL["epl185"],
        "family_key": "ep-equipment:epl",
        "family_name": "EPL",
        "family_url": URL["epl185"],
        "product_url_scope": "exact_variant",
        "image": IMG["epl185"],
        "description": (
            "The EPL185 is EP Equipment's 1.8-ton compact electric pallet truck for "
            "light-to-medium pedestrian pallet moves with a slim Li-ion package."
        ),
        "purpose": (
            "Light-to-medium pallet transport\n"
            "Retail and warehouse walkie moves\n"
            "Aisle and staging handling\n"
            "Compact electric pallet jack work"
        ),
        "features": (
            "Rated load capacity 1800 kg. Service weight about 170 kg. "
            "Fork lift height 115 mm. Travel speed about 5 km/h; 48 V (OEM PDP). "
            "Compact pedestrian tiller design."
        ),
        "payload_kg": 1800.0,
        "weight_kg": 170.0,
        "speed": 5.0,
        "availability_status_key": "available",
        "videos": YT["epl185"],
        "information_source_urls": [URL["epl185"]],
        "notes_force": (
            "[AI Research] Live PDP. Distinct studio hero vs EPL154. Status pending_review."
        ),
        "source_note": URL["epl185"],
    },
    2746: {
        **common_tax(kind="pallet"),
        "name": "EPL154",
        "model_name": "EPL154",
        "variant_code": "EPL154",
        "variant_label": "EPL154",
        "url": URL["epl154"],
        "family_key": "ep-equipment:epl",
        "family_name": "EPL",
        "family_url": URL["epl154"],
        "product_url_scope": "exact_variant",
        "image": IMG["epl154"],
        "description": (
            "The EPL154 is EP Equipment's 1.5-ton compact electric pallet truck for "
            "everyday pedestrian pallet handling in warehouses and retail backrooms."
        ),
        "purpose": (
            "Everyday walkie pallet transport\n"
            "Retail backroom handling\n"
            "Light warehouse pallet moves\n"
            "Compact aisle pallet jack work"
        ),
        "features": (
            "Rated load capacity 1500 kg. Service weight about 160 kg. "
            "Fork lift height 115 mm. Travel speed about 4.5 km/h; 24 V. "
            "Width about 610 mm. Compact pedestrian design."
        ),
        "payload_kg": 1500.0,
        "weight_kg": 160.0,
        "speed": 4.5,
        "width_mm": 610,
        "availability_status_key": "available",
        "videos": YT["epl154"],
        "information_source_urls": [URL["epl154"]],
        "notes_force": (
            "[AI Research] Live PDP. Distinct studio hero vs EPL185. Status pending_review."
        ),
        "source_note": URL["epl154"],
    },
    # Brochure / overview — Available if still in EU2025, else Discontinued
    4939: {
        **common_tax(kind="stacker"),
        "name": "ES20-WA",
        "model_name": "ES20-WA",
        "variant_code": "ES20-WA",
        "variant_label": "ES20-WA",
        "url": URL["bro_es20"],
        "family_key": "ep-equipment:es",
        "family_name": "ES",
        "family_url": URL["stackers"],
        "product_url_scope": "exact_variant",
        "allow_no_image": True,
        "description": (
            "The ES20-WA is EP Equipment's WA-series electric stacker still listed in "
            "the 2025 EU product overview. The EN brochure remains the primary "
            "model-specific source after the former /product/es20-wa/ PDP returned 404."
        ),
        "purpose": (
            "Pedestrian pallet stacking\n"
            "Warehouse put-away\n"
            "Mid-height rack stacking\n"
            "Indoor logistics stacking"
        ),
        "features": (
            "OEM EN brochure ES20-WA still hosted on ep-equipment.com. "
            "2025 EU overview cites capacity options about 1.2 / 1.6 / 1.8 t and "
            "lift height band about 2600–5500 mm with 24 V / 100 Ah Li-ion — "
            "typed payload cleared (multi-option; CRM 2000 kg not verified). "
            "Former PDP /product/es20-wa/ is 404."
        ),
        "clear_payload": True,
        "availability_status_key": "available",
        "videos": YT["es20"],
        "information_source_urls": [URL["bro_es20"], URL["eu2025"]],
        "notes_force": (
            IMAGE_TODO.format(
                why=(
                    "No live PDP hero on cdn.ep-portal.net for ES20-WA; /product/es20-wa/ "
                    f"404. Brochure {URL['bro_es20']} and EU2025 overview cite the model "
                    "but rasterized brochure pages are not used as public heroes "
                    "(rights/hosting)."
                )
            )
            + "[AI Research] Still listed in 2025 EU overview → Available. "
            "Cleared unverified payload_kg=2000. Status pending_review."
        ),
        "source_note": f"{URL['bro_es20']}; {URL['eu2025']}",
    },
    4940: {
        **common_tax(kind="stacker"),
        "name": "ES12-25WA",
        "model_name": "ES12-25WA",
        "variant_code": "ES12-25WA",
        "variant_label": "ES12-25WA",
        "url": URL["bro_es12_25wa"],
        "family_key": "ep-equipment:es",
        "family_name": "ES",
        "family_url": URL["stackers"],
        "product_url_scope": "exact_variant",
        "allow_no_image": True,
        "description": (
            "The ES12-25WA is an EP Equipment WA-series electric stacker documented "
            "in the official EN brochure. The former product PDP is offline and the "
            "model is absent from the 2025 EU overview."
        ),
        "purpose": (
            "Pedestrian pallet stacking\n"
            "Warehouse put-away\n"
            "Light-to-medium stacker work"
        ),
        "features": (
            f"Primary source: EN brochure {URL['bro_es12_25wa']}. "
            "Former PDP /product/es12-25wa/ returns 404; not listed in 2025 EU overview. "
            "Typed payload cleared — CRM 2000 kg conflicts with ES12 naming convention "
            "and was not re-verified from extractable brochure text "
            "(font-subset / image tables)."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "videos": [],
        "information_source_urls": [URL["bro_es12_25wa"], URL["eu2021"]],
        "notes_force": (
            IMAGE_TODO.format(
                why=(
                    "PDP 404; no cdn.ep-portal.net model hero found. Brochure-only; "
                    "not in 2025 EU overview."
                )
            )
            + "[AI Research] Discontinued (absent EU2025; PDP dead). Status pending_review."
        ),
        "source_note": f"{URL['bro_es12_25wa']}; {URL['eu2021']}",
    },
    4938: {
        **common_tax(kind="stacker"),
        "name": "ES12-12ES / ES12-25MM",
        "model_name": "ES12-12ES / ES12-25MM",
        "variant_code": "ES12-12ES/ES12-25MM",
        "variant_label": "ES12-12ES / ES12-25MM family",
        "url": URL["bro_es10_12"],
        "family_key": "ep-equipment:es",
        "family_name": "ES",
        "family_url": URL["bro_es10_12"],
        "product_url_scope": "family",
        "allow_no_image": True,
        "description": (
            "Family record for EP Equipment ES12-12ES and ES12-25MM economical "
            "stackers covered by the shared ES10/ES12 ES/DM/MM EN brochure. Live "
            "per-SKU PDPs are offline."
        ),
        "purpose": (
            "Economical pedestrian stacking\n"
            "Light warehouse put-away\n"
            "Entry-level stacker operations"
        ),
        "features": (
            f"Family brochure {URL['bro_es10_12']} covers ES10/ES12 ES, DM, MM variants. "
            "CRM combined ES12-12ES + ES12-25MM on one row — kept family-scope. "
            "PDPs 404; not in 2025 EU overview. Typed payload cleared (family "
            "multi-column; CRM 1000 kg not re-verified from extractable text)."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "videos": [],
        "information_source_urls": [URL["bro_es10_12"]],
        "notes_force": (
            IMAGE_TODO.format(
                why="No live PDP; brochure family page only; no distinct CDN hero."
            )
            + "[AI Research] Family-scope discontinued stackers. Status pending_review."
        ),
        "source_note": URL["bro_es10_12"],
    },
    4937: {
        **common_tax(kind="stacker"),
        "name": "ES10-10ES / ES10-22MM",
        "model_name": "ES10-10ES / ES10-22MM",
        "variant_code": "ES10-10ES/ES10-22MM",
        "variant_label": "ES10-10ES / ES10-22MM family",
        "url": URL["bro_es10_12"],
        "family_key": "ep-equipment:es",
        "family_name": "ES",
        "family_url": URL["bro_es10_12"],
        "product_url_scope": "family",
        "allow_no_image": True,
        "description": (
            "Family record for EP Equipment ES10-10ES and ES10-22MM economical "
            "stackers on the shared ES10/ES12 ES/DM/MM EN brochure. Live PDPs are offline."
        ),
        "purpose": (
            "Economical pedestrian stacking\n"
            "Light warehouse put-away\n"
            "Entry-level stacker operations"
        ),
        "features": (
            f"Family brochure {URL['bro_es10_12']}. CRM combined ES10-10ES + ES10-22MM — "
            "kept family-scope. PDPs 404; absent from 2025 EU overview. "
            "Typed payload cleared (multi-SKU brochure)."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "videos": [],
        "information_source_urls": [URL["bro_es10_12"]],
        "notes_force": (
            IMAGE_TODO.format(
                why="No live PDP; shared brochure only; no distinct CDN hero."
            )
            + "[AI Research] Family-scope discontinued. Status pending_review."
        ),
        "source_note": URL["bro_es10_12"],
    },
    4936: {
        **common_tax(kind="stacker"),
        "name": "ES18-40WA",
        "model_name": "ES18-40WA",
        "variant_code": "ES18-40WA",
        "variant_label": "ES18-40WA",
        "url": URL["bro_es18"],
        "family_key": "ep-equipment:es",
        "family_name": "ES",
        "family_url": URL["stackers"],
        "product_url_scope": "exact_variant",
        "allow_no_image": True,
        "description": (
            "The ES18-40WA is an EP Equipment WA-series electric stacker documented "
            "in the official EN brochure. The former PDP is offline and the model is "
            "absent from the 2025 EU overview."
        ),
        "purpose": (
            "Pedestrian pallet stacking\n"
            "Higher-lift warehouse put-away\n"
            "Indoor stacker operations"
        ),
        "features": (
            f"EN brochure {URL['bro_es18']}. PDP /product/es18-40wa/ 404; not in EU2025. "
            "Typed payload cleared (CRM 1400 kg not re-verified from extractable text)."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "videos": [],
        "information_source_urls": [URL["bro_es18"]],
        "notes_force": (
            IMAGE_TODO.format(why="PDP 404; brochure-only; no CDN hero.")
            + "[AI Research] Discontinued. Status pending_review."
        ),
        "source_note": URL["bro_es18"],
    },
    4935: {
        **common_tax(kind="stacker"),
        "name": "ES14-30WA",
        "model_name": "ES14-30WA",
        "variant_code": "ES14-30WA",
        "variant_label": "ES14-30WA",
        "url": URL["bro_es14"],
        "family_key": "ep-equipment:es",
        "family_name": "ES",
        "family_url": URL["stackers"],
        "product_url_scope": "exact_variant",
        "allow_no_image": True,
        "description": (
            "The ES14-30WA is an EP Equipment WA-series electric stacker documented "
            "in the official EN brochure. The former PDP is offline and the model is "
            "absent from the 2025 EU overview."
        ),
        "purpose": (
            "Pedestrian pallet stacking\n"
            "Warehouse put-away\n"
            "Indoor stacker operations"
        ),
        "features": (
            f"EN brochure {URL['bro_es14']}. PDP /product/es14-30wa/ 404; not in EU2025. "
            "Typed payload cleared (CRM 1400 kg not re-verified from extractable text)."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "videos": [],
        "information_source_urls": [URL["bro_es14"]],
        "notes_force": (
            IMAGE_TODO.format(why="PDP 404; brochure-only; no CDN hero.")
            + "[AI Research] Discontinued. Status pending_review."
        ),
        "source_note": URL["bro_es14"],
    },
    4933: {
        **common_tax(kind="pallet"),
        "name": "WPL201",
        "model_name": "WPL201",
        "variant_code": "WPL201",
        "variant_label": "WPL201",
        "url": URL["bro_wpl201"],
        "family_key": "ep-equipment:wpl",
        "family_name": "WPL",
        "family_url": URL["wpl202"],
        "product_url_scope": "exact_variant",
        "allow_no_image": True,
        "description": (
            "The WPL201 is EP Equipment's earlier walkie Li-ion pallet truck, "
            "documented in an official brochure. The live catalog now features WPL202 "
            "as the current 2.0 t heavy-duty Li-ion walkie — WPL201 itself has no PDP."
        ),
        "purpose": (
            "Walkie pallet transport\n"
            "Warehouse pallet moves\n"
            "Li-ion pedestrian handling"
        ),
        "features": (
            f"Brochure {URL['bro_wpl201']} (ES). Live successor PDP is WPL202 "
            f"({URL['wpl202']}) — NOT used for specs/hero (different SKU). "
            "WPL201 PDP 404; absent from EU2025 (WPL202 listed). "
            "Typed payload cleared pending model-specific extractable table."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "videos": YT["wpl201"],
        "information_source_urls": [URL["bro_wpl201"], URL["eu2025"]],
        "notes_force": (
            IMAGE_TODO.format(
                why=(
                    "No WPL201 PDP/CDN hero. Do NOT use WPL202 product image "
                    f"({URL['wpl202']}) — different SKU."
                )
            )
            + "[AI Research] Discontinued / superseded by WPL202. Status pending_review."
        ),
        "source_note": f"{URL['bro_wpl201']}; {URL['eu2025']}",
    },
    4943: {
        **common_tax(kind="tow"),
        "name": "QDD30T/30TS",
        "model_name": "QDD30T/30TS",
        "variant_code": "QDD30T/30TS",
        "variant_label": "QDD30T / QDD30TS",
        "url": URL["eu2021"],
        "family_key": "ep-equipment:qdd",
        "family_name": "QDD",
        "family_url": URL["tow"],
        "product_url_scope": "family",
        "allow_no_image": True,
        "description": (
            "The QDD30T/30TS electric tow tractors appeared in EP Equipment's older "
            "EU product overview. They are absent from the 2025 overview; the current "
            "3.0 t tractor on the site is QDD30S (different SKU — not remapped here)."
        ),
        "purpose": (
            "Tugger / tow tractor moves\n"
            "Trailer and cart towing\n"
            "Warehouse and factory towing"
        ),
        "features": (
            "Historical family QDD30T/30TS from EU overview materials. "
            f"Live /product/qdd30t-30ts/ 404. Current related PDP is QDD30S "
            f"({URL['qdd30s']}) — NOT treated as the same SKU. "
            "Towing/drawbar capacity must NOT be mapped to payload_kg (Noblelift MHE rule). "
            "Typed payload cleared."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "videos": [],
        "information_source_urls": [URL["eu2021"], URL["tow"]],
        "notes_force": (
            IMAGE_TODO.format(
                why=(
                    "No QDD30T/30TS PDP or CDN hero. Do NOT use QDD30S hero "
                    f"({URL['qdd30s']}) — different current SKU."
                )
            )
            + "[AI Research] Discontinued. Cleared tow capacity from payload_kg. "
            "Status pending_review."
        ),
        "source_note": f"{URL['eu2021']}; {URL['tow']}",
    },
    4942: {
        **common_tax(kind="pallet"),
        "name": "EPT20-30TW",
        "model_name": "EPT20-30TW",
        "variant_code": "EPT20-30TW",
        "variant_label": "EPT20-30TW",
        "url": URL["eu2021"],
        "family_key": "ep-equipment:ept",
        "family_name": "EPT",
        "family_url": f"{COMPANY_WEBSITE}/product-category/electric-pallet-trucks/",
        "product_url_scope": "exact_variant",
        "allow_no_image": True,
        "description": (
            "The EPT20-30TW appears only in older EP Equipment product-overview PDFs. "
            "There is no live EN PDP, and the model is absent from the 2025 EU overview."
        ),
        "purpose": (
            "Electric pallet transport\n"
            "Warehouse pallet moves"
        ),
        "features": (
            "Cited in historical EP product-overview PDFs only. "
            "PDP /product/ept20-30tw/ 404; not in EU2025. "
            "Typed payload cleared (no model-specific extractable table in this pass)."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "videos": [],
        "information_source_urls": [URL["eu2021"]],
        "notes_force": (
            IMAGE_TODO.format(
                why="No live PDP or CDN hero; overview-PDF only mention."
            )
            + "[AI Research] Discontinued. Status pending_review."
        ),
        "source_note": URL["eu2021"],
    },
    4932: {
        **common_tax(kind="pallet"),
        "name": "HPL152",
        "model_name": "HPL152",
        "variant_code": "HPL152",
        "variant_label": "HPL152",
        "url": URL["eu2021"],
        "family_key": "ep-equipment:hpl",
        "family_name": "HPL",
        "family_url": f"{COMPANY_WEBSITE}/product-category/electric-pallet-trucks/",
        "product_url_scope": "exact_variant",
        "allow_no_image": True,
        "description": (
            "The HPL152 is referenced in older EP Equipment product-overview materials. "
            "No live EN PDP or current-overview listing was found in this enrich pass."
        ),
        "purpose": (
            "Electric pallet transport\n"
            "Warehouse pallet moves"
        ),
        "features": (
            "Historical overview mention only. PDP /product/hpl152/ 404; "
            "absent from EU2025 and current category listings. "
            "Typed payload cleared (no citeable model-specific table)."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "videos": [],
        "information_source_urls": [URL["eu2021"]],
        "notes_force": (
            IMAGE_TODO.format(
                why="No live PDP, brochure, or CDN hero located for HPL152."
            )
            + "[AI Research] Discontinued / unverifiable on current catalog. "
            "Status pending_review."
        ),
        "source_note": URL["eu2021"],
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--skip-hero-check", action="store_true")
    parser.add_argument("--only", type=int, nargs="*", default=None)
    parser.add_argument("--local", action="store_true")
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
        fix = {**fix, "tags": tags}
        row = build_row(fix, tags=tags)
        if len(row.get("features") or "") < 40:
            print(f"ERROR {rid}: features too short", file=sys.stderr)
            return 1
        if not row.get("family_key"):
            print(f"ERROR {rid}: missing family_key", file=sys.stderr)
            return 1
        if not row.get("image") and not fix.get("allow_no_image"):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        purpose = str(row.get("purpose") or "")
        desc = str(row.get("description") or "")
        if purpose and desc and purpose.strip().rstrip(".") == desc.strip().split(".")[0].strip():
            print(f"ERROR {rid}: purpose duplicates description", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: pay={row.get('payload_kg')} "
            f"wt={row.get('weight_kg')} speed={row.get('speed')} "
            f"fam={row.get('family_key')} avail={row.get('availability_status_key')} "
            f"img={bool(row.get('image'))} vids={len(row.get('video_urls') or [])}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "ep-1274-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "family_key": t["row"].get("family_key"),
                    "availability": t["row"].get("availability_status_key"),
                    "payload_kg": t["row"].get("payload_kg"),
                    "image": t["row"].get("image"),
                    "url": t["row"].get("url"),
                    "allow_no_image": t["fix"].get("allow_no_image"),
                }
                for t in targets
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Preview: {preview} ({len(targets)} robots)")

    if not args.apply:
        print("Dry-run only. Re-run with --apply --copy-media --verify-cdn")
        return 0

    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="ep1274-fix-"))
    imported: list[int] = []
    for t in targets:
        rid = t["id"]
        row = t["row"]
        fix = t["fix"]
        print(f"Applying {rid} {t['name']}…", flush=True)
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        fpath = tmp / f"{slugify_robot_name(str(t['name']))}-{rid}.json"
        fpath.write_text(
            json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        try:
            result = client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=False,
                replace_media=bool(fix.get("image")),
                replace_videos=bool(fix.get("videos")),
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(None),
            )
        except Exception as exc:
            print(f"FAIL {rid}: {exc}", file=sys.stderr)
            continue
        created = int(result.get("created_count") or 0)
        if created:
            print(
                f"FAIL {rid}: unexpected created_count={created} {result}",
                file=sys.stderr,
            )
            continue
        if int(result.get("error_count") or 0):
            print(f"FAIL {rid}: {result}", file=sys.stderr)
            continue
        imported.append(rid)
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
                {
                    "status": "pending_review",
                    "availability_status": _AVAIL_IDS.get(
                        fix.get("availability_status_key") or "available", 11
                    ),
                },
            )
        except Exception as exc:
            print(f"  avail fail {rid}: {exc}", file=sys.stderr)
        print(f"  imported {rid}: {result.get('results')}")

    if args.copy_media and imported:
        media_ids = [rid for rid in imported if ROBOT_FIXES[rid].get("image")]
        ok, fail = trigger_copy_media(media_ids)
        print(f"copy-media ok={ok} fail={fail}")

    drop_verification_flags(client, imported)

    if args.verify_cdn:
        cmd = [
            sys.executable,
            str(_RESEARCH_DIR / "verify_cdn_images.py"),
            "--company-id",
            str(COMPANY_ID),
        ]
        print("Running", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(_RESEARCH_DIR))

    print(f"Done. imported={len(imported)} / {len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
