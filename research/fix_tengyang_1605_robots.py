"""Fix Shandong Tengyang Intelligent Equipment (company 1605) content-queue enrichment.

OEM: http://www.sdtengyang.com
Issues:
- Robot/model/family names incorrectly include marketing titles
  ('KW1300M-3200 Load 300kg, 3200mm Palletizing Robot') — OEM model is KW1300M-3200
- family_key/name were per-SKU marketing slugs instead of series (KW-M / KW-B)
- missing features, purpose, typed specs, manufacturer_country, taxonomy, tags
- status stays pending_review
"""
from __future__ import annotations

import argparse
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

COMPANY_ID = 1605
COMPANY_SLUG = "shandong-tengyang-intelligent-equipment"
COMPANY_NAME = "Shandong Tengyang Intelligent Equipment"
COMPANY_WEBSITE = "http://www.sdtengyang.com"
CN_COUNTRY_ID = 3

# Curated from OEM PDPs (Product Parameters + dedicated model prose).
# KW1007B-740 table lists 4KG (same block as KW1004B) — model code + prose say 7kg; use 7.
ROBOTS: dict[int, dict[str, Any]] = {
    6743: {
        "name": "KW1300M-3200",
        "model_name": "KW1300M-3200",
        "variant_code": "KW1300M-3200",
        "variant_label": "300 kg / 3200 mm",
        "url": f"{COMPANY_WEBSITE}/KW1300M-3200.html",
        "family_key": f"{COMPANY_SLUG}:kw-m",
        "family_name": "KW-M",
        "family_url": f"{COMPANY_WEBSITE}/KW1300M-3200.html",
        "product_url_scope": "exact_variant",
        "payload_kg": 300.0,
        "reach_mm": 3200.0,
        "weight_kg": 1200.0,
        "dof": 4,
        "repeatability_mm": 0.2,
        "ip_rating": "IP54",
        "role": "palletizing",
        "description": (
            "KW1300M-3200 is Shandong Tengyang's large-load four-axis palletizing "
            "robot. The wrist carries up to 300 kg with a 3200 mm working radius, "
            "built around a high-rigidity vertical-joint structure for handling, "
            "palletizing, and loading/unloading."
        ),
        "purpose": (
            "Palletizing\n"
            "Material handling\n"
            "Loading and unloading"
        ),
        "features": (
            "4-DOF vertical-joint palletizing robot (Kowell KW-M). Max "
            "transportable weight 300 kg; reach 3200 mm; position repeatability "
            "±0.2 mm; body weight 1200 kg; protection equivalent to IP54; ground "
            "mount; 12 kVA; ambient 0–45°C / 20–80% RH (no condensation). "
            "High-rigidity structure with high-speed intelligent palletizing "
            "process package; soft PLC and bus interfaces; collision detection. "
            "Target industries: auto parts, photovoltaic, food & beverage, "
            "building materials, logistics/warehousing."
        ),
    },
    6742: {
        "name": "KW1120M-2400",
        "model_name": "KW1120M-2400",
        "variant_code": "KW1120M-2400",
        "variant_label": "120 kg / 2400 mm",
        "url": f"{COMPANY_WEBSITE}/KW1120M-2400.html",
        "family_key": f"{COMPANY_SLUG}:kw-m",
        "family_name": "KW-M",
        "family_url": f"{COMPANY_WEBSITE}/KW1300M-3200.html",
        "product_url_scope": "exact_variant",
        "payload_kg": 120.0,
        "reach_mm": 2400.0,
        "weight_kg": 1020.0,
        "dof": 4,
        "repeatability_mm": 0.2,
        "ip_rating": "IP54",
        "role": "palletizing",
        "description": (
            "KW1120M-2400 is Tengyang's medium-load four-axis palletizing robot "
            "with a 120 kg wrist payload and 2400 mm working radius for handling, "
            "palletizing, and load/unload cells."
        ),
        "purpose": (
            "Palletizing\n"
            "Material handling\n"
            "Loading and unloading"
        ),
        "features": (
            "4-DOF vertical-joint palletizing robot (Kowell KW-M). Max "
            "transportable weight 120 kg; reach 2400 mm; repeatability ±0.2 mm; "
            "body weight 1020 kg; protection equivalent to IP54; ground mount; "
            "11 kVA. Process packages, soft PLC/bus interfaces, collision "
            "detection."
        ),
    },
    6740: {
        "name": "KW1030M-1835",
        "model_name": "KW1030M-1835",
        "variant_code": "KW1030M-1835",
        "variant_label": "30 kg / 1835 mm",
        "url": f"{COMPANY_WEBSITE}/KW1030M-1835.html",
        "family_key": f"{COMPANY_SLUG}:kw-m",
        "family_name": "KW-M",
        "family_url": f"{COMPANY_WEBSITE}/KW1300M-3200.html",
        "product_url_scope": "exact_variant",
        "payload_kg": 30.0,
        "reach_mm": 1835.0,
        "weight_kg": 220.0,
        "dof": 4,
        "repeatability_mm": 0.05,
        "ip_rating": "IP54",
        "role": "palletizing",
        "description": (
            "KW1030M-1835 is Tengyang's small-load four-axis palletizing robot "
            "with a 30 kg wrist payload and 1835 mm working radius."
        ),
        "purpose": (
            "Light palletizing\n"
            "Material handling\n"
            "Loading and unloading"
        ),
        "features": (
            "4-DOF vertical-joint palletizing robot (Kowell KW-M). Max "
            "transportable weight 30 kg; reach 1835 mm; position repeatability "
            "±0.05 mm; body weight 220 kg; protection equivalent to IP54; ground "
            "mount; 3.0 kVA. Process packages, soft PLC/bus interfaces, collision "
            "detection."
        ),
    },
    6741: {
        "name": "KW1080B-2700",
        "model_name": "KW1080B-2700",
        "variant_code": "KW1080B-2700",
        "variant_label": "80 kg / 2700 mm",
        "url": f"{COMPANY_WEBSITE}/KW1080B-2700.html",
        "family_key": f"{COMPANY_SLUG}:kw-b",
        "family_name": "KW-B",
        "family_url": f"{COMPANY_WEBSITE}/KW1080B-2700.html",
        "product_url_scope": "exact_variant",
        "payload_kg": 80.0,
        "reach_mm": 2700.0,
        "weight_kg": 570.0,
        "dof": 6,
        "repeatability_mm": 0.05,
        "ip_rating": "IP54",
        "role": "industrial",
        "description": (
            "KW1080B-2700 is Tengyang's medium-load six-axis industrial robot "
            "with an 80 kg wrist payload and 2700 mm working radius for handling, "
            "palletizing, and general industrial automation."
        ),
        "purpose": (
            "Material handling\n"
            "Palletizing\n"
            "Loading and unloading"
        ),
        "features": (
            "6-DOF vertical-joint industrial robot (Kowell KW-B). Max "
            "transportable weight 80 kg; reach 2700 mm; repeatability ±0.05 mm; "
            "body weight 570 kg; protection equivalent to IP54; 5.0 kVA; ground "
            "or hoisting mount. Process packages, soft PLC/bus interfaces, "
            "collision detection."
        ),
    },
    6739: {
        "name": "KW1007B-740",
        "model_name": "KW1007B-740",
        "variant_code": "KW1007B-740",
        "variant_label": "7 kg / 740 mm",
        "url": f"{COMPANY_WEBSITE}/KW1007B-740.html",
        "family_key": f"{COMPANY_SLUG}:kw-b",
        "family_name": "KW-B",
        "family_url": f"{COMPANY_WEBSITE}/KW1080B-2700.html",
        "product_url_scope": "exact_variant",
        "payload_kg": 7.0,
        "reach_mm": 740.0,
        "weight_kg": 27.0,
        "dof": 6,
        "repeatability_mm": 0.02,
        "ip_rating": "IP67",
        "role": "handling",
        "description": (
            "KW1007B-740 is Tengyang's small-load six-axis handling robot with a "
            "7 kg wrist payload and 740 mm working radius. Floor, stand, or "
            "upside-down mounting."
        ),
        "purpose": (
            "Material handling\n"
            "Loading and unloading\n"
            "Light palletizing"
        ),
        "features": (
            "6-DOF vertical-joint handling robot (Kowell KW-B). Wrist load 7 kg "
            "and reach 740 mm per model designation and product prose (parameter "
            "table on the same page lists 4 kg — appears copy-pasted from "
            "KW1004B; typed payload uses the model/prose 7 kg). Repeatability "
            "±0.02 mm; body weight 27 kg; protection equivalent to IP67; 2.0 kVA; "
            "floor/stand/upside-down mount. Process packages, soft PLC/bus "
            "interfaces, collision detection."
        ),
        "notes_force": (
            "[AI Research] Renamed from marketing title to OEM model KW1007B-740. "
            "payload_kg=7 from model code + 'wrist can carry a load of 7kg' prose; "
            "OEM parameter table on the same page incorrectly shows 4KG (sibling "
            "KW1004B value) — noted, not used."
        ),
    },
    6738: {
        "name": "KW1004B-580",
        "model_name": "KW1004B-580",
        "variant_code": "KW1004B-580",
        "variant_label": "4 kg / 580 mm",
        "url": f"{COMPANY_WEBSITE}/KW1004B-580.html",
        "family_key": f"{COMPANY_SLUG}:kw-b",
        "family_name": "KW-B",
        "family_url": f"{COMPANY_WEBSITE}/KW1080B-2700.html",
        "product_url_scope": "exact_variant",
        "payload_kg": 4.0,
        "reach_mm": 580.0,
        "weight_kg": 27.0,
        "dof": 6,
        "repeatability_mm": 0.02,
        "ip_rating": "IP67",
        "role": "handling",
        "description": (
            "KW1004B-580 is Tengyang's small-load six-axis handling robot with a "
            "4 kg wrist payload and 580 mm working radius. Floor, stand, or "
            "upside-down mounting."
        ),
        "purpose": (
            "Material handling\n"
            "Loading and unloading\n"
            "Light pick-and-place"
        ),
        "features": (
            "6-DOF vertical-joint handling robot (Kowell KW-B). Max transportable "
            "weight 4 kg; reach 580 mm; repeatability ±0.02 mm; body weight 27 kg; "
            "protection equivalent to IP67; 2.0 kVA; floor/stand/upside-down "
            "mount. Process packages, soft PLC/bus interfaces, collision "
            "detection."
        ),
    },
}

TAGS_M = "Industrial|Industrial Arm|Palletizing|4-Axis|Material Handling"
TAGS_B = "Industrial|Industrial Arm|6-Axis|Material Handling"


def resolve_tags(catalog: TagCatalog, pipe: str) -> str:
    out, missing = [], []
    for n in [x.strip() for x in pipe.split("|") if x.strip()]:
        hit = catalog._by_name.get(n.lower())
        if hit:
            out.append(str(hit.get("name") or n))
        else:
            missing.append(n)
    if missing:
        print(f"WARN unresolved tags: {missing}", file=sys.stderr)
    return "|".join(out)


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET") or ""
    if not secret:
        env = _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("INTERNAL_API_SECRET="):
                    secret = line.split("=", 1)[1].strip().strip('"').strip("'")
    api = (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.status_code < 300:
                ok += 1
                print(f"copy-media ok {rid}", flush=True)
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}", flush=True)
        except Exception as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.15)
    return ok, fail


def build_row(fix: dict[str, Any], *, tags: str, image: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
        "name": fix["name"],
        "model_name": fix["model_name"],
        "variant_code": fix["variant_code"],
        "variant_label": fix["variant_label"],
        "url": fix["url"],
        "family_key": fix["family_key"],
        "family_name": fix["family_name"],
        "family_url": fix["family_url"],
        "product_url_scope": fix["product_url_scope"],
        "description": fix["description"],
        "purpose": fix["purpose"],
        "features": fix["features"],
        "payload_kg": fix["payload_kg"],
        "reach_mm": fix["reach_mm"],
        "dof": fix["dof"],
        "repeatability_mm": fix["repeatability_mm"],
        "availability_status_key": "available",
        "movement_type_keys": "stationary|fixed",
        "industry_keys": "manufacturing|industrial|food-beverage|logistics|warehousing",
        "use_keys": "material-handling|palletizing|intralogistics",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": tags,
        "manufacturer_country_code": "CN",
        "information_source_urls": [fix["url"]],
        "programming_interface": (
            "Soft PLC and industry process packages with bus interfaces "
            "(OEM product details)."
        ),
        "deployment_context": (
            "Factory floor industrial arm for handling and palletizing cells."
        ),
        "mounting_options": (
            "Ground"
            if fix["role"] == "palletizing"
            else (
                "Ground, hoisting"
                if fix["role"] == "industrial"
                else "Floor, stand, upside-down"
            )
        ),
        "safety_fencing": (
            "Collision detection (OEM product details). Soft PLC and bus I/O "
            "for cell integration."
        ),
        "notes": fix.get("notes_force")
        or (
            f"[AI Research] Renamed from marketing title to OEM model "
            f"{fix['name']}. Family set to {fix['family_name']} "
            f"({fix['family_key']}). Specs from {fix['url']}."
        ),
        "research_notes": fix["url"],
    }
    if fix.get("weight_kg") is not None:
        row["weight_kg"] = fix["weight_kg"]
    if image:
        row["image"] = image
        row["images"] = [image]
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "payload_kg": fix["payload_kg"],
        "reach_mm": fix["reach_mm"],
        "dof": fix["dof"],
        "repeatability_mm": fix["repeatability_mm"],
        "family_key": fix["family_key"],
        "family_name": fix["family_name"],
        "family_url": fix["family_url"],
        "model_name": fix["model_name"],
        "variant_code": fix["variant_code"],
        "variant_label": fix["variant_label"],
        "product_url_scope": fix["product_url_scope"],
        "purpose": fix["purpose"],
        "programming_interface": (
            "Soft PLC and industry process packages with bus interfaces "
            "(OEM product details)."
        ),
        "deployment_context": (
            "Factory floor industrial arm for handling and palletizing cells."
        ),
        "mounting_options": (
            "Ground"
            if fix["role"] == "palletizing"
            else (
                "Ground, hoisting"
                if fix["role"] == "industrial"
                else "Floor, stand, upside-down"
            )
        ),
        "safety_fencing": (
            "Collision detection (OEM product details). Soft PLC and bus I/O "
            "for cell integration."
        ),
        "availability_status": 11,
        "manufacturer_countries": [CN_COUNTRY_ID],
        "manufacturer_country_ref": CN_COUNTRY_ID,
    }
    if fix.get("weight_kg") is not None:
        body["weight_kg"] = fix["weight_kg"]
    ok = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    print(f"  patched typed {rid}: {ok}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    pending = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    targets = []
    for rid, fix in ROBOTS.items():
        if args.only and rid not in args.only:
            continue
        robot = pending.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending")
            continue
        image = robot.get("s3_image") or robot.get("image") or ""
        tags = resolve_tags(catalog, TAGS_M if fix["role"] == "palletizing" else TAGS_B)
        row = build_row(fix, tags=tags, image=image)
        if len(row["features"]) < 40 or not row["family_key"]:
            print(f"ERROR incomplete {rid}", file=sys.stderr)
            return 1
        targets.append({"id": rid, "fix": fix, "row": row, "image": image})
        print(
            f"  {rid} {fix['name']}: pay={fix['payload_kg']} reach={fix['reach_mm']} "
            f"dof={fix['dof']} fam={fix['family_key']}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "tengyang-1605-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            [
                {
                    "id": t["id"],
                    "old": pending[t["id"]].get("name"),
                    "new": t["fix"]["name"],
                    "family_key": t["fix"]["family_key"],
                    "family_name": t["fix"]["family_name"],
                    "payload_kg": t["fix"]["payload_kg"],
                    "reach_mm": t["fix"]["reach_mm"],
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
        print(f"Preview {preview}. Re-run --apply --verify-cdn --mark-done")
        print(
            "NOTE: Naming WAS wrong — OEM model is KW1300M-3200; "
            "'Load 300kg, 3200mm Palletizing Robot' is page title fluff."
        )
        return 0

    imported = []
    for t in targets:
        rid, fix, row = t["id"], t["fix"], t["row"]
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        bulk["name"] = fix["name"]
        bulk["status"] = "pending_review"
        # Keep existing owned CDN heroes (replace_media=False) — already HTTP 200.
        print(f"Importing {rid} {fix['name']}…", flush=True)
        result = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=False,
            replace_media=False,
            replace_videos=False,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
        )
        created = int(result.get("created_count") or 0)
        err = int(result.get("error_count") or 0)
        print(f"  created={created} updated={result.get('updated_count')} err={err}")
        if created or err:
            print(f"ERROR {rid}: {result}", file=sys.stderr)
            return 1
        patch_typed(client, rid, fix)
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "status": "pending_review",
                    "name": fix["name"],
                    "notes": row["notes"],
                },
            )
        except Exception as exc:
            print(f"  final patch warn {rid}: {exc}", file=sys.stderr)
        imported.append(rid)

    if args.copy_media and imported:
        # Not required when keeping owned CDN; optional force refresh skipped.
        print("skip copy-media (keeping owned CDN heroes; use --copy-media only if re-sourcing)")

    if args.verify_cdn and imported:
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--company-id",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

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

    print(json.dumps({"imported": imported, "preview": str(preview)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
