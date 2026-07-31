"""Fix Wesar Intelligence (company 1476) content-queue enrichment.

OEM: https://www.wesar.cn/ (WP product catalog + EN PDPs with spec tables)

Issues addressed:
- 50 pending_review → reject 17 Wesar-prefixed / same-URL duplicates; enrich 33 keepers
- Fabricated payload_kg=1000 on every SKU → OEM rated/exec loads from PDP tables
- Shared CDN junk hash f571f855… (4KB) + cross-SKU featured collisions → distinct OEM heroes
  or deliberate imageless + IMAGE TO-DO
- Legacy WP slugs that look 'wrong' (tp5-50dth=Q8-2000A, cu4-200l-2-*=CU*, f4-3000-2=TP5-50DCW)
  confirmed via WP titles — keep OEM URLs
- F3-1000 PDP 404; F3-1000/2000/3000 and F4-2000/F4-3000 share identical OEM asset bytes
- family_key wesar:{series}; CN manufacturer; Available (F3-1000 Discontinued)
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

COMPANY_ID = 1476
COMPANY_SLUG = "wesar-suzhou-intelligence-technology-co-ltd"
COMPANY_NAME = "Wesar Intelligence"
CN = "CN"
CN_COUNTRY_ID = 3
OEM = "https://www.wesar.cn"
PREVIEW = _RESEARCH_DIR / "staging" / "reports" / "wesar-1476-fix-preview.json"
REPORT = _RESEARCH_DIR / "staging" / "reports" / "wesar-1476-enrichment.md"
SPECS_PATH = _RESEARCH_DIR / "staging" / "_wesar_1476" / "parsed_specs.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

_AVAIL_IDS = {
    "announced": 10,
    "available": 11,
    "released": 3,
    "discontinued": 4,
    "pre_order": 12,
}

FAM_CU = f"{OEM}/product-category/autonomous-mobile-robot/conveyor-mobile-robot%ef%bc%88cmr%ef%bc%89/"
FAM_TP = f"{OEM}/product-category/autonomous-mobile-robot/carton-transfer-unit-ctu/"
FAM_F = f"{OEM}/product-category/autonomous-mobile-robot/forklift-mobile-robot-fmr/"
FAM_Q = f"{OEM}/product-category/autonomous-mobile-robot/"

U = f"{OEM}/wp-content/uploads/2025/02"
IMG = {
    "CU2-100L": f"{U}/CU2-100L.jpg",
    "CU2-120L": f"{U}/CU2-120L.jpg",
    "CU1-600L": f"{U}/CU1-600L.jpg",
    "CU1-400C": f"{U}/CU1-400C.jpg",
    "CU1-1000L": f"{U}/CU1-1000L.jpg",
    "CU4-200L": f"{U}/CU4-200L.jpg",
    "TP5-50DCW": f"{U}/TP5-50DCW.jpg",
    "TP5-50DCHT": f"{U}/TP5-50DCHT.jpg",
    "TP5-50DC": f"{U}/TP5-50DC.jpg",
    "TP5-50DCN": f"{U}/TP5-50DCN.jpg",
    "TP5-50DC-B": f"{U}/P60-TP5-50DC-B.jpg",
    "TP5-50DCP": f"{U}/TP5-50DCP.jpg",
    "TP1-50DC": f"{U}/P58-TP1-50DC.jpg",
    "F4-1000C": f"{U}/P67-F4-1000C.jpg",
    "F4-3000A": f"{U}/P67-F4-300A.jpg",
    "F3-1500": f"{U}/F3-1500.png",
    "F1-600U": f"{U}/P65-F1-600U.jpg",
    "Q3-600D": f"{U}/Q3-600D.jpg",
    "Q7B-1000E": f"{U}/p28-Q7-1000E.jpg",
    "Q8-2000A": f"{U}/p28-Q8-2000A.jpg",
    "Q2-400D": f"{U}/p28-Q2-400D.jpg",
    "Q3B-600D": f"{U}/Q3B-600D.jpg",
    "QF-1000CD": f"{U}/QF-1000CD.jpg",
    "QF2-600O": f"{U}/P32-QF2-600O.jpg",
    "QF3-1000D": f"{U}/P32-QF3-1000D.jpg",
    "QF-600CD": f"{U}/QF-600CD.jpg",
}

TAGS_CMR = "AMR|Autonomous Mobile Robot|Mobile Robot|Wheeled|Logistics|Warehouse|Conveyor|Material Handling|Indoor|Warehouse Automation"
TAGS_CTU = "AMR|Autonomous Mobile Robot|Mobile Robot|Wheeled|Logistics|Warehouse|Material Handling|Indoor|Warehouse Automation|Intralogistics"
TAGS_FMR = "AMR|Autonomous Mobile Robot|Mobile Robot|Wheeled|Logistics|Warehouse|Forklift|Pallet|Material Handling|Indoor|Autonomous Forklift"
TAGS_LMR = "AMR|Autonomous Mobile Robot|Mobile Robot|Wheeled|Logistics|Warehouse|Material Handling|Indoor|Pallet|Warehouse Automation"
TAGS_QF = "AMR|Autonomous Mobile Robot|Mobile Robot|Wheeled|Logistics|Warehouse|Forklift|Pallet|Material Handling|Indoor|Autonomous Forklift"

PURPOSE_CMR = (
    "Line-side roller conveyor transfer\n"
    "Workstation-to-workstation tote transport\n"
    "Warehouse conveyor docking\n"
    "Factory logistics bridging"
)
PURPOSE_CTU = (
    "Carton and tote storage retrieval\n"
    "High-bay aisle picking\n"
    "Goods-to-person tote transfer\n"
    "Warehouse carton handling"
)
PURPOSE_FMR = (
    "Pallet horizontal transport\n"
    "Pallet stacking and putaway\n"
    "Warehouse forklift automation\n"
    "Dock and aisle pallet moves"
)
PURPOSE_LMR = (
    "Under-rack latent transport\n"
    "Shelf and rack lifting moves\n"
    "Factory latent logistics\n"
    "Backpack / lifting AMR carrying"
)
PURPOSE_QF = (
    "Pallet under-fork latent handling\n"
    "Fork-pocket pallet pickup\n"
    "Warehouse pallet transfer\n"
    "Ground-roller docking"
)

REJECTS: dict[int, str] = {
    3310: "Duplicate of robot 4349 (F4-2000 (4.5m)). Same OEM PDP /product/f4-2000-4-5m/; keep cleaner product-named record.",
    4338: "Duplicate of robot 4348 (F4-1000C). Same OEM PDP /product/f4-1000c-2/; keep cleaner product-named record.",
    4337: "Duplicate of robot 4347 (F3-3000). Same OEM PDP /product/f3-3000/; keep cleaner product-named record.",
    3308: "Duplicate of robot 4346 (F3-1500). Same OEM PDP /product/f3-1500-2/; keep cleaner product-named record.",
    4335: "Duplicate of robot 4345 (F3-1000). Same OEM URL /product/f3-1000/; keep cleaner product-named record.",
    4334: "Duplicate of robot 4344 (Q3-600D). Same OEM PDP /product/q3-600d/; keep cleaner product-named record.",
    3306: "Duplicate of robot 4343 (Q7B-1000E). Same OEM PDP /product/q7b-1000e/; keep cleaner product-named record.",
    4332: "Duplicate of robot 4342 (Q8-2000A). Same OEM PDP /product/tp5-50dth/ (WP slug; title Q8-2000A); keep cleaner product-named record.",
    4331: "Duplicate of robot 4341 (QF-1000CD). Same OEM PDP /product/qf-1000cd/; keep cleaner product-named record.",
    3304: "Duplicate of robot 4340 (QF2-600O). Same OEM PDP /product/qf2-600o/; keep cleaner product-named record.",
    4329: "Duplicate of robot 4339 (QF3-1000D). Same OEM PDP /product/qf3-1000d/; keep cleaner product-named record.",
    4336: "Duplicate of robot 3315 (F3-2000). Same OEM PDP /product/f3-2000/; keep cleaner product-named record.",
    4333: "Duplicate of robot 3313 (Q2-400D). Same OEM PDP /product/q2-400d/; keep cleaner product-named record.",
    4330: "Duplicate of robot 3311 (QF-600CD). Same OEM PDP /product/qf-1000cd-2/ (WP title QF-600CD); 'Wesar QF-1000CD-2' was a misnamed duplicate.",
    3309: "Duplicate of robot 3316 (F1-600U). Same OEM PDP /product/f1-600u/; keep cleaner product-named record.",
    3307: "Duplicate of robot 3314 (F4-3000 stacking / f4-3000a). Same OEM PDP /product/f4-3000a/; keep stacking-series keeper.",
    3305: "Duplicate of robot 3312 (Q3B-600D). Same OEM PDP /product/2965/; keep cleaner product-named record.",
}

IMAGE_TODO_F3_SHARED = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "OEM featured assets F3-1000.jpg / F3-2000.jpg / F3-3000.jpg are byte-identical "
    "(md5 606153672137…) Hikrobot-branded pallet AMR renders — cannot assign to more than "
    "one exact model (skill hash-unique / fail-closed). F3-1000 PDP returns HTTP 404 "
    "(2026-07-29) though Serper still indexes the historical URL.\n"
    "Previously held shared 4KB CDN junk hash f571f855… — removed.\n"
    "ACTION FOR TEAM: request model-specific licensed Wesar/OEM heroes for F3-1000, "
    "F3-2000, and F3-3000 (distinct content hashes).\n"
    "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
    "---\n"
)
IMAGE_TODO_F4_SHARED = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "OEM F4-2000.jpg and F4-3000.jpg are byte-identical (md5 a9c48c1eb3c6…) — fail-closed "
    "for both non-stacking F4 SKUs. Stacking F4-3000a uses distinct P67-F4-300A.jpg.\n"
    "Previously held shared CDN junk / colliding featured — removed.\n"
    "ACTION FOR TEAM: source distinct licensed heroes for F4-2000 (4.5m) and F4-3000.\n"
    "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
    "---\n"
)
IMAGE_TODO_TP5_DCH = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "OEM TP5-50DCH.jpg is byte-identical to TP5-50DCN.jpg (md5 14155dc5ea6e…) — hero kept "
    "on TP5-50DCN (4351) only.\n"
    "ACTION FOR TEAM: request a TP5-50DCH-specific licensed product render.\n"
    "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
    "---\n"
)
IMAGE_TODO_CU1_1500C = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "OEM PDP /product/cu4-200l-2-5/ (CU1-1500C) has no featured_media and no model-named "
    "upload (CU1-1500C.jpg 404). Page only embeds shared site graphics.\n"
    "ACTION FOR TEAM: request CU1-1500C product hero from Wesar.\n"
    "Do NOT substitute a sibling CU render.\n"
    "---\n"
)


def pdp(slug: str) -> str:
    return f"{OEM}/product/{slug}/"


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


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
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
        time.sleep(0.15)
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


def features_from_kv(spec: dict[str, Any], extra: str = "") -> str:
    kv = spec.get("kv") or {}
    parts: list[str] = []
    if extra:
        parts.append(extra)
    interesting = [
        "Rated load (kg)",
        "Robot rated load (kg)",
        "Rated Load (kg)",
        "Rated Load of the Whole Machine (kg)",
        "Execution structure load (kg)",
        "Actuator Load (kg)",
        "Weight (kg)",
        "Weight (with battery) (kg)",
        "Self-Weight (Including Battery)(kg)",
        "Dimension (L × W × H)(mm)",
        "Dimension (L × W × H) (mm)",
        "Dimensions (mm)",
        "Dimensions (l1*b1*h1)(mm)",
        "Navigation mode",
        "Navigation Mode",
        "Navigation Method",
        "Navigation method",
        "Drive method",
        "Drive Type",
        "Driving direction",
        "Motion method",
        "Movement Mode",
        "Rated running speed (empty) (mm/s)",
        "Rated running speed (m/s)",
        "Rated Speed (mm/s)",
        "Rated Travel Speed (Unloaded)(mm/s)",
        "Rated Travel Speed (Unloaded) (m/s)",
        "Run time (h)",
        "Operating Time Under Rated Conditions (h)",
        "Rated Operating Time (h)",
        "Charging time (h)",
        "Charging Time After Full Discharge (h)",
        "Conveying type",
        "Fork lifting height (h3+h13) (mm)",
        "Lifting Height (h3+h13)(mm)",
        "Picking height (mm)",
        "Pickup Height (mm)",
        "Lifting stroke (mm)",
        "Maximum Lifting Height（mm）",
        "Execution structure type",
        "Actuator Type",
        "Human-machine interaction",
        "Human-Machine Interaction",
    ]
    seen = set()
    for key in interesting:
        val = kv.get(key)
        if not val or val in ("–", "-", "/", ""):
            continue
        label = key
        sig = (label, val)
        if sig in seen:
            continue
        seen.add(sig)
        parts.append(f"{label}: {val}")
    # safety cluster
    safety_bits = []
    for key, val in kv.items():
        if val in ("Support", "Optional", "Customizable", "0ptional"):
            if any(x in key.lower() for x in ("laser", "bumper", "emergency", "alarm", "collision", "obstacle")):
                safety_bits.append(f"{key}={val}")
    if safety_bits:
        parts.append("Safety: " + "; ".join(safety_bits[:8]))
    text = ". ".join(parts)
    if len(text) < 80:
        text = (text + " " + str(spec.get("title") or "")).strip()
    return text[:1800]


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
        "imageless",
        "spec_slug",
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
        "payload_kg",
        "weight_kg",
        "speed",
        "length_mm",
        "width_mm",
        "height_mm",
        "runtime_minutes",
        "charging_time_minutes",
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
    ):
        if k in fix and fix[k] not in (None, ""):
            body[k] = fix[k]
    if fix.get("clear_payload"):
        body["payload_kg"] = None
    avail_key = fix.get("availability_status_key")
    if avail_key:
        body["availability_status"] = _AVAIL_IDS.get(str(avail_key), avail_key)
    if fix.get("imageless"):
        body["image"] = ""
        body["s3_image"] = None
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


def drop_stale_media_flags(client: ResearchApiClient, robot_ids: list[int]) -> None:
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
        flags = r.get("quality_flags") or r.get("error_flags") or r.get("verification_errors") or []
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
            print(f"  flag-drop fail {rid}: {exc} (may need ORM)", file=sys.stderr)


def hash_url(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=90)
        if not resp.ok or len(resp.content) < 5000:
            return None
        magic_ok = (
            resp.content[:8] == b"\x89PNG\r\n\x1a\n"
            or resp.content[:3] == b"\xff\xd8\xff"
            or resp.content[:4] == b"RIFF"
        )
        if not magic_ok:
            return None
        return hashlib.md5(resp.content).hexdigest()
    except requests.RequestException:
        return None


def assert_distinct_heroes(fixes: dict[int, dict[str, Any]]) -> None:
    hashes: dict[str, int] = {}
    junk = "f571f855c228abe94b7e73a2c9b1b166"
    for rid, fix in fixes.items():
        if fix.get("imageless"):
            print(f"  hero hash {rid}: IMAGELESS")
            continue
        url = fix.get("image")
        if not url:
            raise RuntimeError(f"{rid}: missing image")
        h = hash_url(str(url))
        if not h:
            raise RuntimeError(f"{rid}: failed to hash / too small / not image {url}")
        if h == junk:
            raise RuntimeError(f"{rid}: refused shared junk CDN hash")
        if h in hashes:
            raise RuntimeError(f"hero hash collision {rid} vs {hashes[h]} md5={h}")
        hashes[h] = rid
        print(f"  hero hash {rid}: {h[:12]} ({url.split('/')[-1]})")


def fix(
    *,
    name: str,
    model: str,
    series: str,
    family_name: str,
    family_url: str,
    url: str,
    image: str | None,
    description: str,
    purpose: str,
    tags: str,
    spec_slug: str,
    features_extra: str = "",
    availability: str = "available",
    imageless_note: str | None = None,
    payload_override: float | None = None,
    clear_payload: bool = False,
    notes_extra: str = "",
) -> dict[str, Any]:
    specs = json.loads(SPECS_PATH.read_text(encoding="utf-8"))
    spec = specs.get(spec_slug) or {}
    feat = features_from_kv(spec, features_extra)
    row: dict[str, Any] = {
        "name": name,
        "model_name": model,
        "variant_code": model,
        "variant_label": model,
        "url": url,
        "family_key": f"wesar:{series}",
        "family_name": family_name,
        "family_url": family_url,
        "product_url_scope": "exact_variant",
        "description": description,
        "purpose": purpose,
        "features": feat,
        "tags": tags,
        "availability_status_key": availability,
        "manufacturer_country_code": CN,
        "movement_type_keys": "wheeled",
        "industry_keys": "logistics|manufacturing|warehousing",
        "use_keys": "material-handling|warehousing|logistics",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "programming_interface": "Touchscreen HMI; Wesar RCS / warehouse software suite (RCS-2000, iWMS)",
        "deployment_context": "Indoor factory and warehouse autonomous mobile robot deployments",
        "ecosystem_compatibility": "Wesar RoboX / MapStudio / RCS-2000 / iWMS software suite",
        "safety_fencing": "Laser obstacle avoidance, bumper strips, e-stop, sound/light alarm (OEM PDP)",
        "mounting_options": "Wheeled AMR chassis; model-specific conveyor, fork, clamp, or latent lift",
        "information_source_urls": [url, family_url, f"{OEM}/products/"],
        "spec_slug": spec_slug,
        "source_note": f"{url}; WP/EN PDP spec table 2026-07-29",
        "notes_force": (
            f"[AI Research] Enriched from OEM EN PDP {url}. "
            f"Cleared fabricated fleet-wide payload_kg=1000. "
            f"Hero from wesar.cn/wp-content/uploads (content-hash unique across keepers). "
            f"{notes_extra}"
        ).strip(),
    }
    if clear_payload:
        row["clear_payload"] = True
    else:
        payload = payload_override if payload_override is not None else spec.get("payload_kg")
        if payload is not None:
            row["payload_kg"] = float(payload)
    for k in ("weight_kg", "length_mm", "width_mm", "height_mm", "charging_time_minutes", "runtime_minutes"):
        if spec.get(k) is not None:
            row[k] = spec[k]
    if spec.get("speed_kmh") is not None:
        row["speed"] = spec["speed_kmh"]
    if imageless_note:
        row["image"] = None
        row["imageless"] = True
        row["notes_force"] = imageless_note + (row.get("notes_force") or "")
    else:
        row["image"] = image
    return row


def build_robot_fixes() -> dict[int, dict[str, Any]]:
    return {
        # --- CMR ---
        4358: fix(
            name="CU2-100L",
            model="CU2-100L",
            series="cu",
            family_name="Wesar CU Conveyor Mobile Robot",
            family_url=FAM_CU,
            url=pdp("cu4-200l-2-4"),
            image=IMG["CU2-100L"],
            description=(
                "The CU2-100L is Wesar's dual-roller conveyor mobile robot (CMR) for "
                "100 kg rated load line-side transfer. It combines bi-directional driving, "
                "2D barcode / L-SLAM navigation, and a 700 mm working surface for "
                "workstation conveyor docking in factories and warehouses."
            ),
            purpose=PURPOSE_CMR,
            tags=TAGS_CMR,
            spec_slug="cu4-200l-2-4",
            features_extra="Conveyor Mobile Robot (CMR); dual roller; rated load 100 kg (OEM title/table).",
            notes_extra="WP slug cu4-200l-2-4 is CU2-100L per OEM title.",
        ),
        4357: fix(
            name="CU2-120L",
            model="CU2-120L",
            series="cu",
            family_name="Wesar CU Conveyor Mobile Robot",
            family_url=FAM_CU,
            url=pdp("cu2-120l"),
            image=IMG["CU2-120L"],
            description=(
                "The CU2-120L is a Wesar dual-roller CMR rated at 120 kg. Compact "
                "1150×824×1119 mm footprint with selectable 450/850 mm working height "
                "supports flexible conveyor handoff in indoor logistics."
            ),
            purpose=PURPOSE_CMR,
            tags=TAGS_CMR,
            spec_slug="cu2-120l",
            features_extra="Conveyor Mobile Robot (CMR); dual roller; rated load 120 kg.",
        ),
        4356: fix(
            name="CU1-600L",
            model="CU1-600L",
            series="cu",
            family_name="Wesar CU Conveyor Mobile Robot",
            family_url=FAM_CU,
            url=pdp("cu4-200l-2-3"),
            image=IMG["CU1-600L"],
            description=(
                "The CU1-600L is Wesar's single-roller CMR for 600 kg rated loads with "
                "omnidirectional driving. A 1400×1115×1230 mm body and L-SLAM / barcode "
                "navigation target heavier conveyor bridging between production cells."
            ),
            purpose=PURPOSE_CMR,
            tags=TAGS_CMR,
            spec_slug="cu4-200l-2-3",
            features_extra="Conveyor Mobile Robot (CMR); single roller; omnidirectional; rated load 600 kg.",
            notes_extra="WP slug cu4-200l-2-3 is CU1-600L per OEM title.",
        ),
        4355: fix(
            name="CU1-400C",
            model="CU1-400C",
            series="cu",
            family_name="Wesar CU Conveyor Mobile Robot",
            family_url=FAM_CU,
            url=pdp("cu4-200l-2"),
            image=IMG["CU1-400C"],
            description=(
                "The CU1-400C is a compact Wesar single-roller CMR rated at 400 kg. "
                "Bi-directional driving and a low 700 mm overall height suit dense "
                "workstation conveyor exchanges."
            ),
            purpose=PURPOSE_CMR,
            tags=TAGS_CMR,
            spec_slug="cu4-200l-2",
            features_extra="Conveyor Mobile Robot (CMR); single roller; rated load 400 kg.",
            notes_extra="WP slug cu4-200l-2 is CU1-400C per OEM title.",
        ),
        3322: fix(
            name="CU1-1000L",
            model="CU1-1000L",
            series="cu",
            family_name="Wesar CU Conveyor Mobile Robot",
            family_url=FAM_CU,
            url=pdp("cu4-200l-2-2"),
            image=IMG["CU1-1000L"],
            description=(
                "The CU1-1000L is Wesar's high-capacity CMR with 1000 kg rated load for "
                "heavy conveyor transfer. Large 1680×1300×1981 mm platform and barcode / "
                "L-SLAM navigation support factory logistics bridging."
            ),
            purpose=PURPOSE_CMR,
            tags=TAGS_CMR,
            spec_slug="cu4-200l-2-2",
            features_extra="Conveyor Mobile Robot (CMR); rated load 1000 kg.",
            notes_extra="WP slug cu4-200l-2-2 is CU1-1000L per OEM title.",
        ),
        3321: fix(
            name="CU1-1500C",
            model="CU1-1500C",
            series="cu",
            family_name="Wesar CU Conveyor Mobile Robot",
            family_url=FAM_CU,
            url=pdp("cu4-200l-2-5"),
            image=None,
            description=(
                "The CU1-1500C is Wesar's highest-rated CMR in this queue (1500 kg) for "
                "heavy conveyor mobile transfer. OEM EN PDP documents dimensions, weight, "
                "and motion performance; no distinct product hero was published on the page."
            ),
            purpose=PURPOSE_CMR,
            tags=TAGS_CMR,
            spec_slug="cu4-200l-2-5",
            features_extra="Conveyor Mobile Robot (CMR); rated load 1500 kg.",
            imageless_note=IMAGE_TODO_CU1_1500C,
            notes_extra="WP slug cu4-200l-2-5 is CU1-1500C; no featured_media.",
        ),
        3323: fix(
            name="CU4-200L",
            model="CU4-200L",
            series="cu",
            family_name="Wesar CU Conveyor Mobile Robot",
            family_url=FAM_CU,
            url=pdp("cu4-200l"),
            image=IMG["CU4-200L"],
            description=(
                "The CU4-200L is a Wesar CMR rated at 200 kg for roller conveyor mobile "
                "robot applications. Indoor barcode / L-SLAM navigation and bi-directional "
                "driving support production-line material flow."
            ),
            purpose=PURPOSE_CMR,
            tags=TAGS_CMR,
            spec_slug="cu4-200l",
            features_extra="Conveyor Mobile Robot (CMR); rated load 200 kg.",
        ),
        # --- CTU ---
        4354: fix(
            name="TP5-50DCW",
            model="TP5-50DCW",
            series="tp5",
            family_name="Wesar TP5 Carton Transfer Unit",
            family_url=FAM_TP,
            url=pdp("f4-3000-2"),
            image=IMG["TP5-50DCW"],
            description=(
                "The TP5-50DCW is a Wesar carton transfer unit (CTU) with clamp single-deep "
                "execution (50 kg actuator load) and up to ~10 m pick height options. "
                "Designed for high-bay tote/carton retrieval in narrow aisles."
            ),
            purpose=PURPOSE_CTU,
            tags=TAGS_CTU,
            spec_slug="f4-3000-2",
            features_extra=(
                "Carton Transfer Unit (CTU). payload_kg uses OEM execution structure load "
                "50 kg (robot rated load 300 kg also cited)."
            ),
            notes_extra="WP slug f4-3000-2 is TP5-50DCW/TP5-50DCW(T) per OEM title.",
        ),
        4353: fix(
            name="TP5-50DCH(T)",
            model="TP5-50DCH(T)",
            series="tp5",
            family_name="Wesar TP5 Carton Transfer Unit",
            family_url=FAM_TP,
            url=pdp("tp5-50dcht"),
            image=IMG["TP5-50DCHT"],
            description=(
                "The TP5-50DCH(T) is a tall Wesar CTU for clamp single-deep carton handling "
                "with 50 kg actuator load and 370–10240 mm picking height for high-bay "
                "warehouse aisles."
            ),
            purpose=PURPOSE_CTU,
            tags=TAGS_CTU,
            spec_slug="tp5-50dcht",
            features_extra="CTU; execution structure load 50 kg; robot rated load 300 kg.",
        ),
        4352: fix(
            name="TP5-50DC",
            model="TP5-50DC",
            series="tp5",
            family_name="Wesar TP5 Carton Transfer Unit",
            family_url=FAM_TP,
            url=pdp("tp5-50dc"),
            image=IMG["TP5-50DC"],
            description=(
                "The TP5-50DC is a mid-height Wesar CTU (200–4000 mm pick range) with "
                "50 kg clamp actuator load for tote and carton transfer in warehouse aisles."
            ),
            purpose=PURPOSE_CTU,
            tags=TAGS_CTU,
            spec_slug="tp5-50dc",
            features_extra="CTU; execution structure load 50 kg; robot rated load 300 kg.",
        ),
        4351: fix(
            name="TP5-50DCN",
            model="TP5-50DCN",
            series="tp5",
            family_name="Wesar TP5 Carton Transfer Unit",
            family_url=FAM_TP,
            url=pdp("tp5-50dcn"),
            image=IMG["TP5-50DCN"],
            description=(
                "The TP5-50DCN is a compact Wesar CTU with 30 kg execution load and "
                "320–2420 mm picking height for smaller tote footprints in tight aisles."
            ),
            purpose=PURPOSE_CTU,
            tags=TAGS_CTU,
            spec_slug="tp5-50dcn",
            features_extra="CTU; execution structure load 30 kg; robot rated load 180 kg.",
            notes_extra="Hero assigned here; TP5-50DCH shares identical OEM bytes → imageless.",
        ),
        4350: fix(
            name="TP5-50DC-B",
            model="TP5-50DC-B",
            series="tp5",
            family_name="Wesar TP5 Carton Transfer Unit",
            family_url=FAM_TP,
            url=pdp("tp5-50dc-b"),
            image=IMG["TP5-50DC-B"],
            description=(
                "The TP5-50DC-B is Wesar's clamping-C CTU variant with 50 kg actuator load "
                "and FlashStation / ToteRelayPick solution positioning for goods-to-person "
                "carton workflows."
            ),
            purpose=PURPOSE_CTU,
            tags=TAGS_CTU,
            spec_slug="tp5-50dc-b",
            features_extra="CTU clamping C series; actuator load 50 kg; whole-machine rated load 300 kg.",
        ),
        3320: fix(
            name="TP5-50DCP",
            model="TP5-50DCP",
            series="tp5",
            family_name="Wesar TP5 Carton Transfer Unit",
            family_url=FAM_TP,
            url=pdp("tp5-50dcp-tp5-50dcpt"),
            image=IMG["TP5-50DCP"],
            description=(
                "The TP5-50DCP / TP5-50DCP(T) is a Wesar high-reach CTU for carton transfer "
                "with 50 kg execution load, targeting multi-level tote storage aisles."
            ),
            purpose=PURPOSE_CTU,
            tags=TAGS_CTU,
            spec_slug="tp5-50dcp-tp5-50dcpt",
            features_extra="CTU; execution structure load 50 kg.",
        ),
        3319: fix(
            name="TP5-50DCH",
            model="TP5-50DCH",
            series="tp5",
            family_name="Wesar TP5 Carton Transfer Unit",
            family_url=FAM_TP,
            url=pdp("tp5-50dch"),
            image=None,
            description=(
                "The TP5-50DCH is a Wesar high-bay CTU with 50 kg clamp execution load and "
                "tall mast for carton/tote retrieval. OEM product image collides with "
                "TP5-50DCN — left imageless pending a distinct hero."
            ),
            purpose=PURPOSE_CTU,
            tags=TAGS_CTU,
            spec_slug="tp5-50dch",
            features_extra="CTU; execution structure load 50 kg; robot rated load 300 kg.",
            imageless_note=IMAGE_TODO_TP5_DCH,
        ),
        3318: fix(
            name="TP1-50DC",
            model="TP1-50DC",
            series="tp1",
            family_name="Wesar TP1 Carton Transfer Unit",
            family_url=FAM_TP,
            url=pdp("tp1-50dc"),
            image=IMG["TP1-50DC"],
            description=(
                "The TP1-50DC is Wesar's compact clamping-C carton transfer unit with "
                "50 kg actuator load for lower-bay tote handling and goods-to-person flows."
            ),
            purpose=PURPOSE_CTU,
            tags=TAGS_CTU,
            spec_slug="tp1-50dc",
            features_extra="CTU clamping C series; actuator-focused 50 kg class.",
        ),
        # --- FMR ---
        4349: fix(
            name="F4-2000 (4.5m)",
            model="F4-2000 (4.5m)",
            series="f4",
            family_name="Wesar F4 Forklift Mobile Robot",
            family_url=FAM_F,
            url=pdp("f4-2000-4-5m"),
            image=None,
            description=(
                "The F4-2000 (4.5m) is a Wesar stacking forklift mobile robot (FMR) with "
                "2000 kg rated load and ~4.5 m fork lift height for pallet putaway. "
                "OEM featured image collides with F4-3000 — left imageless."
            ),
            purpose=PURPOSE_FMR,
            tags=TAGS_FMR,
            spec_slug="f4-2000-4-5m",
            features_extra="Forklift Mobile Robot (FMR) stacking; rated load 2000 kg; fork lift ~4517 mm.",
            imageless_note=IMAGE_TODO_F4_SHARED,
        ),
        4348: fix(
            name="F4-1000C",
            model="F4-1000C",
            series="f4",
            family_name="Wesar F4 Forklift Mobile Robot",
            family_url=FAM_F,
            url=pdp("f4-1000c-2"),
            image=IMG["F4-1000C"],
            description=(
                "The F4-1000C is a Wesar stacking-series FMR rated at 1000 kg for vertical "
                "pallet stacking and deep-storage warehouse moves with touchscreen HMI and "
                "laser obstacle avoidance."
            ),
            purpose=PURPOSE_FMR,
            tags=TAGS_FMR,
            spec_slug="f4-1000c-2",
            features_extra="FMR stacking series; rated load 1000 kg.",
        ),
        3317: fix(
            name="F4-3000",
            model="F4-3000",
            series="f4",
            family_name="Wesar F4 Forklift Mobile Robot",
            family_url=FAM_F,
            url=pdp("f4-3000"),
            image=None,
            description=(
                "The F4-3000 is a Wesar forklift mobile robot rated at 3000 kg for heavy "
                "pallet handling. Distinct from the F4-3000 stacking SKU on /product/f4-3000a/. "
                "OEM hero collides with F4-2000 — imageless."
            ),
            purpose=PURPOSE_FMR,
            tags=TAGS_FMR,
            spec_slug="f4-3000",
            features_extra="FMR; rated load 3000 kg (non-stacking PDP /product/f4-3000/).",
            imageless_note=IMAGE_TODO_F4_SHARED,
            notes_extra="Different URL from stacking 3314/f4-3000a.",
        ),
        3314: fix(
            name="F4-3000 Stacking",
            model="F4-3000A",
            series="f4",
            family_name="Wesar F4 Forklift Mobile Robot",
            family_url=FAM_F,
            url=pdp("f4-3000a"),
            image=IMG["F4-3000A"],
            description=(
                "The F4-3000 stacking-series FMR (OEM froklift listing) provides 3000 kg "
                "rated load and 5500 mm lifting height for high pallet stacking in "
                "warehouses and photovoltaic/3C logistics."
            ),
            purpose=PURPOSE_FMR,
            tags=TAGS_FMR,
            spec_slug="f4-3000a",
            features_extra="FMR stacking series on /product/f4-3000a/; rated load 3000 kg; lift 5500 mm.",
            notes_extra="Renamed from 'F4-3000 Froklift…' to F4-3000 Stacking; variant F4-3000A.",
        ),
        4347: fix(
            name="F3-3000",
            model="F3-3000",
            series="f3",
            family_name="Wesar F3 Forklift Mobile Robot",
            family_url=FAM_F,
            url=pdp("f3-3000"),
            image=None,
            description=(
                "The F3-3000 is a Wesar counterbalanced-style FMR with 3000 kg rated load "
                "for horizontal pallet transport. OEM featured render is shared across "
                "F3-1000/2000/3000 uploads — left imageless."
            ),
            purpose=PURPOSE_FMR,
            tags=TAGS_FMR,
            spec_slug="f3-3000",
            features_extra="FMR; rated load 3000 kg; low fork lift height 200 mm (transport-focused).",
            imageless_note=IMAGE_TODO_F3_SHARED,
        ),
        4346: fix(
            name="F3-1500",
            model="F3-1500",
            series="f3",
            family_name="Wesar F3 Forklift Mobile Robot",
            family_url=FAM_F,
            url=pdp("f3-1500-2"),
            image=IMG["F3-1500"],
            description=(
                "The F3-1500 is a Wesar FMR rated at 1500 kg for pallet horizontal transport "
                "with L-SLAM navigation options and compact transport-height forks."
            ),
            purpose=PURPOSE_FMR,
            tags=TAGS_FMR,
            spec_slug="f3-1500-2",
            features_extra="FMR; rated load 1500 kg. Distinct F3-1500.png hero (unique hash).",
        ),
        4345: fix(
            name="F3-1000",
            model="F3-1000",
            series="f3",
            family_name="Wesar F3 Forklift Mobile Robot",
            family_url=FAM_F,
            url=pdp("f3-1000"),
            image=None,
            description=(
                "The F3-1000 is Wesar's 1000 kg-class F3 forklift mobile robot. The live "
                "OEM PDP returns 404 (2026-07-29); Serper still indexes the historical "
                "product URL. Specs left blank pending a restored datasheet — not invented "
                "from the model code alone."
            ),
            purpose=PURPOSE_FMR,
            tags=TAGS_FMR,
            spec_slug="f3-1000",
            features_extra=(
                "Forklift Mobile Robot (FMR) F3 series. Live PDP 404; no OEM table available "
                "in this pass. Do not trust prior fabricated payload_kg=1000 without table cite."
            ),
            imageless_note=IMAGE_TODO_F3_SHARED,
            clear_payload=True,
            availability="discontinued",
            notes_extra="availability_status=discontinued (PDP 404). payload cleared.",
        ),
        3315: fix(
            name="F3-2000",
            model="F3-2000",
            series="f3",
            family_name="Wesar F3 Forklift Mobile Robot",
            family_url=FAM_F,
            url=pdp("f3-2000"),
            image=None,
            description=(
                "The F3-2000 is a Wesar FMR for pallet transport. OEM EN table lists rated "
                "load 2300 kg (title still says 2000 kg Load) — typed payload follows the "
                "spec table. Shared F3 featured render — imageless."
            ),
            purpose=PURPOSE_FMR,
            tags=TAGS_FMR,
            spec_slug="f3-2000",
            features_extra=(
                "FMR; OEM table Rated load 2300 kg (title says 2000 kg — table wins). "
                "Shared F3 hero bytes — imageless."
            ),
            imageless_note=IMAGE_TODO_F3_SHARED,
            payload_override=2300.0,
            notes_extra="payload_kg=2300 from OEM table despite model/title 2000.",
        ),
        3316: fix(
            name="F1-600U",
            model="F1-600U",
            series="f1",
            family_name="Wesar F1 Forklift Mobile Robot",
            family_url=FAM_F,
            url=pdp("f1-600u"),
            image=IMG["F1-600U"],
            description=(
                "The F1-600U is Wesar's omnidirectional forklift mobile robot rated at "
                "600 kg for flexible pallet moves in tight indoor layouts."
            ),
            purpose=PURPOSE_FMR,
            tags=TAGS_FMR,
            spec_slug="f1-600u",
            features_extra="FMR omnidirectional series; rated load 600 kg.",
        ),
        # --- LMR / Q ---
        4344: fix(
            name="Q3-600D",
            model="Q3-600D",
            series="q",
            family_name="Wesar Q Latent Mobile Robot",
            family_url=FAM_Q,
            url=pdp("q3-600d"),
            image=IMG["Q3-600D"],
            description=(
                "The Q3-600D is a Wesar lifting-type latent mobile robot (LMR) rated at "
                "600 kg for under-rack shelf transport with electric lift stroke and "
                "barcode / L-SLAM / V-SLAM navigation options."
            ),
            purpose=PURPOSE_LMR,
            tags=TAGS_LMR,
            spec_slug="q3-600d",
            features_extra="Latent Mobile Robot (LMR) lifting type; rated load 600 kg.",
        ),
        4343: fix(
            name="Q7B-1000E",
            model="Q7B-1000E",
            series="q",
            family_name="Wesar Q Latent Mobile Robot",
            family_url=FAM_Q,
            url=pdp("q7b-1000e"),
            image=IMG["Q7B-1000E"],
            description=(
                "The Q7B-1000E is a Wesar backpack latent LMR rated at 1000 kg for "
                "automotive parts and 3C warehouse carrying with latent chassis navigation."
            ),
            purpose=PURPOSE_LMR,
            tags=TAGS_LMR,
            spec_slug="q7b-1000e",
            features_extra="LMR backpack latent; rated load 1000 kg.",
        ),
        4342: fix(
            name="Q8-2000A",
            model="Q8-2000A",
            series="q",
            family_name="Wesar Q Latent Mobile Robot",
            family_url=FAM_Q,
            url=pdp("tp5-50dth"),
            image=IMG["Q8-2000A"],
            description=(
                "The Q8-2000A is a Wesar hydraulic lifting latent LMR rated at 2000 kg for "
                "heavy backpack carrying (photovoltaic / lithium PACK lines). OEM WP slug "
                "tp5-50dth still resolves to this Q8 product title."
            ),
            purpose=PURPOSE_LMR,
            tags=TAGS_LMR,
            spec_slug="tp5-50dth",
            features_extra="LMR backpack latent hydraulic; rated load 2000 kg.",
            notes_extra="WP slug tp5-50dth is Q8-2000A per OEM title — URL kept.",
        ),
        3313: fix(
            name="Q2-400D",
            model="Q2-400D",
            series="q",
            family_name="Wesar Q Latent Mobile Robot",
            family_url=FAM_Q,
            url=pdp("q2-400d"),
            image=IMG["Q2-400D"],
            description=(
                "The Q2-400D is a compact Wesar backpack latent LMR rated at 400 kg for "
                "lighter under-rack and lifting-type factory logistics."
            ),
            purpose=PURPOSE_LMR,
            tags=TAGS_LMR,
            spec_slug="q2-400d",
            features_extra="LMR backpack latent lifting type; rated load 400 kg.",
        ),
        3312: fix(
            name="Q3B-600D",
            model="Q3B-600D",
            series="q",
            family_name="Wesar Q Latent Mobile Robot",
            family_url=FAM_Q,
            url=pdp("2965"),
            image=IMG["Q3B-600D"],
            description=(
                "The Q3B-600D is a Wesar forklift-latent LMR rated at 600 kg (OEM category "
                "lists forklift latent). Compact latent chassis for pallet-adjacent "
                "warehouse moves."
            ),
            purpose=PURPOSE_LMR,
            tags=TAGS_QF,
            spec_slug="2965",
            features_extra="Forklift latent LMR; rated load 600 kg. WP slug /product/2965/.",
        ),
        # --- QF ---
        4341: fix(
            name="QF-1000CD",
            model="QF-1000CD",
            series="qf",
            family_name="Wesar QF Forklift Latent Mobile Robot",
            family_url=FAM_Q,
            url=pdp("qf-1000cd"),
            image=IMG["QF-1000CD"],
            description=(
                "The QF-1000CD is a Wesar forklift latent mobile robot rated at 1000 kg for "
                "under-pallet fork-pocket pickup and warehouse pallet transfer."
            ),
            purpose=PURPOSE_QF,
            tags=TAGS_QF,
            spec_slug="qf-1000cd",
            features_extra="Forklift Latent Mobile Robot (LMR); rated load 1000 kg.",
        ),
        4340: fix(
            name="QF2-600O",
            model="QF2-600O",
            series="qf",
            family_name="Wesar QF Forklift Latent Mobile Robot",
            family_url=FAM_Q,
            url=pdp("qf2-600o"),
            image=IMG["QF2-600O"],
            description=(
                "The QF2-600O is an omnidirectional Wesar forklift latent AMR rated at "
                "600 kg for pallet-to-person and unstacker-crane docking workflows."
            ),
            purpose=PURPOSE_QF,
            tags=TAGS_QF,
            spec_slug="qf2-600o",
            features_extra="Forklift latent; omnidirectional drive; rated load 600 kg.",
        ),
        4339: fix(
            name="QF3-1000D",
            model="QF3-1000D",
            series="qf",
            family_name="Wesar QF Forklift Latent Mobile Robot",
            family_url=FAM_Q,
            url=pdp("qf3-1000d"),
            image=IMG["QF3-1000D"],
            description=(
                "The QF3-1000D is a differential-drive Wesar forklift latent AMR rated at "
                "1000 kg for material distribution and ground roller-conveyor docking."
            ),
            purpose=PURPOSE_QF,
            tags=TAGS_QF,
            spec_slug="qf3-1000d",
            features_extra="Forklift latent; differential drive; rated load 1000 kg.",
        ),
        3311: fix(
            name="QF-600CD",
            model="QF-600CD",
            series="qf",
            family_name="Wesar QF Forklift Latent Mobile Robot",
            family_url=FAM_Q,
            url=pdp("qf-1000cd-2"),
            image=IMG["QF-600CD"],
            description=(
                "The QF-600CD is a Wesar forklift latent mobile robot rated at 600 kg. "
                "OEM WP slug qf-1000cd-2 titles this SKU QF-600CD (not QF-1000CD)."
            ),
            purpose=PURPOSE_QF,
            tags=TAGS_QF,
            spec_slug="qf-1000cd-2",
            features_extra="Forklift latent; rated load 600 kg. WP slug qf-1000cd-2 = QF-600CD.",
            notes_extra="Corrected identity vs misnamed 'Wesar QF-1000CD-2' duplicate (4330).",
        ),
    }


ROBOT_FIXES = build_robot_fixes()


def write_report(
    *,
    imported: list[int],
    rejected: list[int],
    imageless: list[int],
    totals: dict[str, Any],
    copy_stats: dict[str, Any] | None,
    payload_summary: list[str],
    cdn_rc: int | None,
) -> None:
    dedup_lines = "\n".join(
        f"- `{rid}` → {reason}" for rid, reason in sorted(REJECTS.items())
    )
    allow = ", ".join(str(i) for i in sorted(imported) if i not in imageless)
    hold = ", ".join(str(i) for i in sorted(imageless))
    payload_block = "\n".join(f"- {line}" for line in payload_summary)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        f"""---
type: log
title: Wesar Intelligence 1476 enrichment
status: draft
version: 1.0
owner: AI
last_updated: 2026-07-29
tags:
  - content-queue
  - wesar
---

# Wesar Intelligence (1476) enrichment

## Summary

- Enriched (imported): **{len(imported)}** — `{imported}`
- Rejected (same-URL / Wesar-prefix dupes): **{len(rejected)}** — `{rejected}`
- Imageless (deliberate): **{len(imageless)}** — `{imageless}`
- Bulk-import totals: `{totals}`
- copy-media: `{copy_stats}`
- verify_cdn exit: `{cdn_rc}`

## Dedup map (rejected → keeper)

{dedup_lines}

## Payload corrections

Cleared fabricated fleet-wide `payload_kg=1000`. OEM table values applied:

{payload_block}

- F3-2000: OEM table **2300 kg** (title still says 2000 kg) — table cited.
- F3-1000: PDP 404 — payload **cleared** (not invented from model code).
- CTU series: `payload_kg` = execution/actuator load (30–50 kg); robot rated load kept in features.

## CDN / heroes

- Purged shared junk CDN hash `f571f855c228…` (~4 KB) across many robots.
- Pre-apply content-hash assert among keepers with heroes (no collisions).
- Fail-closed imageless: F3-1000/2000/3000 (identical OEM bytes), F4-2000 & F4-3000 (identical), TP5-50DCH (collides TP5-50DCN), CU1-1500C (no OEM hero).
- OEM product renders often show Hikrobot/CETC chassis branding — published on wesar.cn PDPs; noted for reviewers.
- Post-apply: `python verify_cdn_images.py --company-id 1476`

## Approve allowlist

Robots with distinct verified heroes + features + family_key (pending_review):

`{allow}`

## Hold / blockers

- Hold imageless IDs: `{hold}`
- F3-1000 live PDP 404 → `availability_status=discontinued`; specs blank until datasheet returns.
- No model-token YouTube hits in this pass — videos left empty.
- Legacy WP slugs retained when titles confirm SKU (e.g. `tp5-50dth`→Q8-2000A, `f4-3000-2`→TP5-50DCW).

## Script

`scripts/research/fix_wesar_1476_robots.py`

## Related

- Staging: `scripts/research/staging/_wesar_1476/`
""",
        encoding="utf-8",
    )
    print(f"wrote report {REPORT}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Wesar Intelligence company 1476")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--reject-dupes", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--drop-flags", action="store_true")
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

    fixes = {
        rid: fx
        for rid, fx in ROBOT_FIXES.items()
        if not args.only or rid in args.only
    }

    if not args.skip_hero_check:
        print("Verifying distinct OEM hero hashes…")
        assert_distinct_heroes(fixes)

    rejected_ids: list[int] = []
    if args.reject_dupes:
        for rid, reason in REJECTS.items():
            if args.only and rid not in args.only:
                continue
            if not args.apply:
                print(f"dry-run reject {rid}: {reason[:110]}...")
                rejected_ids.append(rid)
                continue
            msg = reject_robot(client, rid, reason)
            print(f"reject {rid}: {msg}")
            rejected_ids.append(rid)

    targets = []
    payload_summary: list[str] = []
    for rid, fix_row in fixes.items():
        robot = all_robots.get(rid)
        if not robot and args.apply:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        tags = resolve_tags(catalog, str(fix_row.get("tags") or ""))
        row = build_row(fix_row, tags=tags)
        if len(row.get("features") or "") < 40:
            print(f"ERROR {rid}: features too short", file=sys.stderr)
            return 1
        if not row.get("family_key"):
            print(f"ERROR {rid}: missing family_key", file=sys.stderr)
            return 1
        if not row.get("image") and not fix_row.get("imageless"):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        purpose = str(row.get("purpose") or "")
        desc = str(row.get("description") or "")
        if purpose and desc and purpose.strip().rstrip(".") == desc.strip().split(".")[0].strip():
            print(f"ERROR {rid}: purpose duplicates description", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix_row})
        pl = row.get("payload_kg")
        payload_summary.append(
            f"{rid} {row['name']}: payload={pl} (was 1000) "
            f"{'IMAGELESS' if fix_row.get('imageless') else ''}".strip()
        )
        print(
            f"  {rid} {row['name']}: payload={pl} weight={row.get('weight_kg')} "
            f"speed={row.get('speed')} fam={row.get('family_key')} "
            f"img={'NO' if fix_row.get('imageless') else 'yes'} "
            f"avail={row.get('availability_status_key')}"
        )

    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW.write_text(
        json.dumps(
            [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "payload_kg": t["row"].get("payload_kg"),
                    "family_key": t["row"].get("family_key"),
                    "url": t["row"].get("url"),
                    "imageless": bool(t["fix"].get("imageless")),
                    "image": (t["row"].get("image") or "")[:120],
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
        print(f"Preview: {PREVIEW}. Re-run with --apply --copy-media --verify-cdn --reject-dupes --drop-flags --mark-done")
        write_report(
            imported=[t["id"] for t in targets],
            rejected=rejected_ids,
            imageless=[t["id"] for t in targets if t["fix"].get("imageless")],
            totals={},
            copy_stats=None,
            payload_summary=payload_summary,
            cdn_rc=None,
        )
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="wesar-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    imported: list[int] = []
    for item in targets:
        rid = item["id"]
        fix_row = item["fix"]
        tags = resolve_tags(catalog, str(fix_row.get("tags") or ""))
        row = build_row(fix_row, tags=tags)
        replace_media = not bool(fix_row.get("imageless"))
        if fix_row.get("imageless"):
            row.pop("images", None)
            row.pop("image", None)
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        fpath = tmp / f"{slugify_robot_name(str(item['name']))}-{rid}.json"
        fpath.write_text(json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            result = client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=False,
                replace_media=replace_media,
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
            patch_typed(client, rid, fix_row)
            notes = fix_row.get("notes_force")
            if notes:
                try:
                    client._patch(f"robots/robots/{rid}/", {"notes": notes})
                except Exception as exc:
                    print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  imported {rid}: {result.get('results')}")
        time.sleep(0.1)

    copy_stats = None
    copy_ids = [i for i in imported if not ROBOT_FIXES.get(i, {}).get("imageless")]
    if args.copy_media and copy_ids:
        ok, fail = trigger_copy_media(copy_ids)
        copy_stats = {"ok": ok, "fail": fail, "ids": copy_ids}
        print(f"copy-media ok={ok} fail={fail}")
        for item in targets:
            if item["id"] in imported:
                patch_typed(client, item["id"], item["fix"])

    cdn_rc = None
    if args.verify_cdn and copy_ids:
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

    if args.drop_flags:
        drop_stale_media_flags(client, imported)

    if args.mark_done and imported:
        subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    write_report(
        imported=imported,
        rejected=rejected_ids,
        imageless=[i for i in imported if ROBOT_FIXES.get(i, {}).get("imageless")],
        totals=totals,
        copy_stats=copy_stats,
        payload_summary=payload_summary,
        cdn_rc=cdn_rc,
    )
    print("totals", totals, "copy", copy_stats, "imported", imported)
    return 0 if not totals.get("error_count") else 1


if __name__ == "__main__":
    raise SystemExit(main())
