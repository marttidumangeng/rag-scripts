#!/usr/bin/env python3
"""Fix iRobot (342) To Review verification chips.

Targets the pending_review rows with AI-verify issues:
  - content_contradiction / image_mismatch / unverifiable

Plan:
  3704 Combo i5 — shop copy was Plus 415X; lifestyle hero wrong → OEM i517020 catalog
                 + Combo i5 description/purpose/features
  5208 105 Combo + AutoEmpty — swap to OEM y351420 catalog hero; Available
  4734 105X Combo — swap to OEM Y354020 catalog hero; Available
  3157 Roomba i4 — purpose junk → task phrase (hero already OEM-correct)
  2031 Roomba j9 — PDP 404, photo looks j7, desc copies j9+ auto-empty;
                 reject duplicate of published j9+ (2029)

Usage:
  python _fix_irobot_verify_flags.py
  python _fix_irobot_verify_flags.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from map_to_bulk_import import staging_dict_to_bulk_import_row  # noqa: E402
from validate_staging import purpose_duplicates_description  # noqa: E402

COMPANY_ID = 342
COMPANY_SLUG = "irobot-now-part-of-amazon-robotics"
COMPANY_NAME = "iRobot (part of Amazon Robotics)"
CN_US = 20
AVAILABLE = 11
DISCONTINUED = 4
REPORT = _HERE / "staging" / "reports" / "irobot-verify-fix.json"

# Official master-catalog product shots (SKU in path)
OEM = {
    3704: "https://www.irobot.com/on/demandware.static/-/Sites-master-catalog-irobot/default/dw7b16aec4/images/large/combo/i517020_01.jpg",
    5208: "https://www.irobot.com/on/demandware.static/-/Sites-master-catalog-irobot/default/dw18b3543c/images/large/combo/y351420_0.jpg",
    4734: "https://www.irobot.com/on/demandware.static/-/Sites-master-catalog-irobot/default/dwfb618b35/images/large/combo/Y354020_00.jpg",
    # 3157 hero already byte-identical to OEM i415020 — no media replace
}

FIXES: dict[int, dict[str, Any]] = {
    3704: {
        "name": "Roomba Combo i5 Robot Vacuum and Mop",
        "model_name": "Roomba Combo i5",
        "url": "https://www.irobot.com/en_US/roomba-combo-i5-robot-vacuum-and-mop/I517020.html",
        "description": (
            "The Roomba Combo i5 is a 2-in-1 robot vacuum and mop with powerful suction "
            "and a swappable Combo Bin microfiber pad. It cleans in neat rows room by room "
            "using Imprint Smart Mapping so you can schedule or target specific rooms."
        ),
        "purpose": "Vacuuming and mopping hard floors and carpet in homes",
        "features": (
            "Roomba Combo i5 (OEM iRobot PDP I517020): 2-in-1 vacuum and mop with "
            "swappable Combo Bin; Dirt Detect focuses on dirtier areas with the vacuum bin; "
            "microfiber pad for wet mopping footprints and dust on hard floors; "
            "Imprint Smart Mapping for room-by-room cleaning via the iRobot Home App; "
            "works with Alexa, Siri, and Google Assistant. Non-plus SKU — no Clean Base "
            "auto-empty in this configuration."
        ),
        "availability_status_key": "available",
        "manufacturer_country_code": "US",
        "family_key": "irobot-now-part-of-amazon-robotics:roomba-i-series",
        "family_name": "Roomba i Series",
        "family_url": "https://www.irobot.com/en_US/roomba-combo-i5-robot-vacuum-and-mop/I517020.html",
        "product_url_scope": "exact_variant",
        "variant_code": "i5",
        "variant_label": "Combo i5",
        "weight_kg": 2.92,
        "release_year": 2023,
        "image": OEM[3704],
        "replace_media": True,
    },
    5208: {
        "name": "Roomba 105 Combo Robot + AutoEmpty dock",
        "model_name": "Roomba 105 Combo + AutoEmpty",
        "url": "https://www.irobot.com/en_US/roomba-105-combo-robot-plus-autoempty-dock/Y351420.html",
        "description": (
            "The Roomba 105 Combo Robot + AutoEmpty Dock vacuums and mops wet and dry messes, "
            "with Power-Lifting suction and a self-emptying dock that holds debris for weeks "
            "so you empty less often."
        ),
        "purpose": "Vacuuming and mopping hard floors and carpet with auto-empty dock",
        "features": (
            "Roomba 105 Combo + AutoEmpty (OEM Y351420): combo vacuum and mop for wet and "
            "dry tasks; AutoEmpty dock self-empties the bin for extended hands-free runs; "
            "Power-Lifting suction class cleaning; LiDAR-assisted navigation on the 100-series "
            "Combo body. Cite: iRobot.com PDP Y351420."
        ),
        "availability_status_key": "available",
        "manufacturer_country_code": "US",
        "family_key": "irobot-now-part-of-amazon-robotics:roomba-100200-series",
        "family_name": "Roomba 100/200 Series",
        "family_url": "https://www.irobot.com/en_US/roomba-105-combo-robot-plus-autoempty-dock/Y351420.html",
        "product_url_scope": "exact_variant",
        "variant_code": "105-Combo-AE",
        "variant_label": "105 Combo + AutoEmpty",
        "weight_kg": 2.93,
        "release_year": 2025,
        "image": OEM[5208],
        "replace_media": True,
    },
    4734: {
        "name": "iRobot Roomba 105X Combo Robot Vacuum & Mop",
        "model_name": "Roomba 105X Combo",
        "url": (
            "https://www.irobot.com/en_US/irobot-roomba-105x-combo-robot-vacuum-and-mop"
            "-plus-autoempty-dock/Y352020.html"
        ),
        "description": (
            "The Roomba 105X Combo Robot + AutoEmpty Dock vacuums only, mops only, or "
            "combo-cleans wet and dry messes, then self-empties at the dock so floors stay "
            "clean with less daily upkeep."
        ),
        "purpose": "Vacuuming and mopping hard floors and carpet with auto-empty dock",
        "features": (
            "Roomba 105X Combo + AutoEmpty (OEM Y352020): pick vacuum-only, mop-only, or "
            "combo mode; AutoEmpty dock self-empties debris; Power-Lifting suction class; "
            "100-series Combo body with LiDAR turret. Cite: iRobot.com PDP Y352020."
        ),
        "availability_status_key": "available",
        "manufacturer_country_code": "US",
        "family_key": "irobot-now-part-of-amazon-robotics:roomba-100200-series",
        "family_name": "Roomba 100/200 Series",
        "family_url": (
            "https://www.irobot.com/en_US/irobot-roomba-105x-combo-robot-vacuum-and-mop"
            "-plus-autoempty-dock/Y352020.html"
        ),
        "product_url_scope": "exact_variant",
        "variant_code": "105X-Combo-AE",
        "variant_label": "105X Combo + AutoEmpty",
        "weight_kg": 2.93,
        "image": OEM[4734],
        "replace_media": True,
    },
    3157: {
        "name": "iRobot Roomba i4",
        "model_name": "Roomba i4",
        "url": "https://www.irobot.com/en_US/roomba_i4/I415020.html",
        "description": (
            "Wi-Fi connected Roomba i4 robot vacuum that learns your home and cleans when "
            "and where you want, including targeted areas near furniture."
        ),
        "purpose": "Autonomous vacuuming of hard floors and carpet in homes",
        "features": (
            "Roomba i4 (OEM I415020): Wi-Fi connected robot vacuum; learns the home layout "
            "for scheduled and on-demand cleans; cleans hard floors and carpet. "
            "Cite: iRobot.com Roomba i4 PDP."
        ),
        "availability_status_key": "available",
        "manufacturer_country_code": "US",
        "family_key": "irobot-now-part-of-amazon-robotics:roomba-i-series",
        "family_name": "Roomba i Series",
        "family_url": "https://www.irobot.com/en_US/roomba_i4/I415020.html",
        "product_url_scope": "exact_variant",
        "variant_code": "i4",
        "variant_label": "i4",
        "weight_kg": 3.37,
        "release_year": 2021,
        "replace_media": False,
    },
}

REJECT = {
    2031: (
        "duplicate: keep published Roomba j9+ (2029); non-plus j9 PDP J915020 returns 404 "
        "(unverifiable), hero was j7 lifestyle, description copied j9+ auto-empty claims"
    ),
}


def _admin_base() -> str:
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    return api.replace("/api/v1", "")


def _internal_secret() -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if secret:
        return secret
    env_file = _HERE.parents[1] / "robotaigeek-server" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def trigger_copy_media(robot_ids: list[int]) -> dict[str, Any]:
    secret = _internal_secret()
    base = _admin_base()
    if not secret or not base:
        return {"ok": False, "error": "INTERNAL_API_SECRET or admin base missing"}
    ok = fail = 0
    errors = []
    for rid in robot_ids:
        url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                errors.append({"id": rid, "status": resp.status_code, "body": resp.text[:200]})
        except requests.RequestException as exc:
            fail += 1
            errors.append({"id": rid, "error": str(exc)})
        time.sleep(0.2)
    return {"ok": fail == 0, "copied_ok": ok, "copied_fail": fail, "errors": errors}


def build_row(rid: int, fix: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": rid,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "industry_keys": "consumer|home",
        "use_keys": "cleaning",
        "movement_type_keys": "wheeled",
        "category_slugs": "service-robots",
        "sub_category_slug": "domestic-household",
        "tags": "Robot Vacuum|Consumer|Home|WiFi",
        "sources": [{"url": fix["url"], "type": "website", "title": fix["name"]}],
        "research_notes": (
            "iRobot verify-flag fix 2026-07-20: corrected description/purpose vs OEM PDP; "
            "replaced mismatched heroes with master-catalog SKU shots where needed."
        ),
    }
    for k, v in fix.items():
        if k == "replace_media":
            continue
        row[k] = v
    # citation for release_year
    if fix.get("release_year"):
        row["research_notes"] += f" release_year={fix['release_year']}: OEM/catalog year retained from prior enrich."
    dup = purpose_duplicates_description(row["purpose"], row["description"])
    if dup:
        raise SystemExit(f"purpose duplicates description on {rid}: {dup}")
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    plan = {
        "company_id": COMPANY_ID,
        "apply": bool(args.apply),
        "fixes": {str(k): {kk: vv for kk, vv in v.items() if kk != "image" or True} for k, v in FIXES.items()},
        "reject": REJECT,
    }
    # compact preview
    preview = []
    for rid, fix in FIXES.items():
        preview.append(
            {
                "id": rid,
                "name": fix["name"],
                "purpose": fix["purpose"],
                "replace_media": fix.get("replace_media"),
                "image": fix.get("image", "")[:80],
            }
        )
    plan["preview"] = preview
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"preview": preview, "reject": REJECT}, indent=2, ensure_ascii=False))
    print(f"plan -> {REPORT}")

    if not args.apply:
        print("dry-run only; pass --apply")
        return 0

    client = ResearchApiClient()

    # Reject j9 (needs ADMIN_SESSION_ID). Else clear contradiction + wrong j7 hero.
    media_ids: list[int] = []
    for rid, reason in REJECT.items():
        rejected = False
        try:
            from moderate_robots import apply_reject  # type: ignore

            results = apply_reject([rid], reason)
            rejected = bool(results and results[0].get("ok"))
            print(f"  reject API {rid}: {results}")
        except Exception as exc:  # noqa: BLE001
            print(f"  reject API fail {rid}: {exc}")
        if rejected:
            continue
        image_todo = (
            "[IMAGE TO-DO — no hero, deliberate]\n"
            "OEM PDP https://www.irobot.com/en_US/roomba-j9-robot-vacuum/J915020.html returns 404.\n"
            "Prior hero was a j7-class lifestyle still (bronze plate + family entryway) — removed.\n"
            "Do NOT use j9+ Clean Base catalog shot for this non-plus SKU.\n"
            "ACTION FOR TEAM: reject as duplicate of published j9+ (2029), or source a "
            "licensed j9-without-dock product still from iRobot media kit.\n"
            "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
            "---\n"
            f"[AI Research] 2026-07-20 verify fix. {reason}"
        )
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "availability_status": DISCONTINUED,
                    "url": "https://www.irobot.com/en_US/roomba-j9plus",
                    "description": (
                        "Discontinued Roomba j9 robot vacuum (non-plus). j-series platform "
                        "with Dirt Detective room prioritization; this SKU shipped without "
                        "the Clean Base auto-empty dock (unlike Roomba j9+)."
                    ),
                    "purpose": "Autonomous vacuuming of hard floors and carpet in homes",
                    "features": (
                        "Roomba j9 (discontinued non-plus): PrecisionVision obstacle "
                        "avoidance; Dirt Detective prioritizes dirtier rooms; no Clean Base "
                        "in this SKU. OEM product page J915020 returns 404 as of 2026-07-20."
                    ),
                    "notes": image_todo,
                    "image": "",
                    "family_key": "irobot-now-part-of-amazon-robotics:roomba-j-series",
                    "family_name": "Roomba j Series",
                    "family_url": "https://www.irobot.com/en_US/roomba-j9plus",
                    "product_url_scope": "family",
                },
            )
            # Wipe mismatched gallery (j7 lifestyle) via empty replace_media import
            wipe = staging_dict_to_bulk_import_row(
                {
                    "id": rid,
                    "name": "iRobot Roomba j9",
                    "company_slug": COMPANY_SLUG,
                    "company_name": COMPANY_NAME,
                    "model_name": "Roomba j9",
                    "url": "https://www.irobot.com/en_US/roomba-j9plus",
                    "description": (
                        "Discontinued Roomba j9 robot vacuum (non-plus). j-series platform "
                        "with Dirt Detective; shipped without Clean Base (unlike j9+)."
                    ),
                    "purpose": "Autonomous vacuuming of hard floors and carpet in homes",
                    "features": (
                        "Roomba j9 discontinued non-plus: PrecisionVision; Dirt Detective; "
                        "no Clean Base. PDP J915020 404."
                    ),
                    "availability_status_key": "discontinued",
                    "manufacturer_country_code": "US",
                    "family_key": "irobot-now-part-of-amazon-robotics:roomba-j-series",
                    "family_name": "Roomba j Series",
                    "family_url": "https://www.irobot.com/en_US/roomba-j9plus",
                    "product_url_scope": "family",
                    "research_notes": image_todo.replace("\n", " | "),
                    "sources": [
                        {
                            "url": "https://www.irobot.com/en_US/roomba-j9plus",
                            "type": "website",
                            "title": "Roomba j9 Series",
                        }
                    ],
                }
            )
            client.bulk_import_robots(
                [wipe],
                update_existing=True,
                patch_existing=False,
                status="pending_review",
                skip_company_update=True,
                created_by_id=1,
                replace_media=True,
            )
            print(f"  j9 content+gallery cleared {rid} (reject in UI → keep 2029)")
        except Exception as exc2:  # noqa: BLE001
            print(f"  j9 FALLBACK FAIL {rid}: {exc2}")

    for rid, fix in FIXES.items():
        row = build_row(rid, fix)
        bulk = staging_dict_to_bulk_import_row(row)
        try:
            resp = client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=False,
                status="pending_review",
                skip_company_update=True,
                created_by_id=1,
                replace_media=bool(fix.get("replace_media")),
            )
            print(
                f"  import {rid}: updated={resp.get('updated_count')} "
                f"err={resp.get('error_count')} {resp.get('errors')}"
            )
            if fix.get("replace_media") and fix.get("image"):
                media_ids.append(rid)
        except Exception as exc:  # noqa: BLE001
            print(f"  IMPORT FAIL {rid}: {exc}")
        time.sleep(0.3)

        soft = {
            "purpose": fix["purpose"],
            "description": fix["description"],
            "availability_status": AVAILABLE,
            "manufacturer_countries": [CN_US],
            "manufacturer_country_ref": CN_US,
            "family_key": fix["family_key"],
            "family_name": fix["family_name"],
            "family_url": fix["family_url"],
            "url": fix["url"],
        }
        if fix.get("weight_kg") is not None:
            soft["weight_kg"] = fix["weight_kg"]
        if fix.get("release_year") is not None:
            soft["release_year"] = fix["release_year"]
        try:
            client._patch(f"robots/robots/{rid}/", soft)
            print(f"  soft-patched {rid}")
        except Exception as exc:  # noqa: BLE001
            print(f"  SOFT FAIL {rid}: {exc}")

    if media_ids:
        print(f"copy-media {media_ids}…")
        print(json.dumps(trigger_copy_media(media_ids), indent=2)[:800])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
