"""Completeness pass for Mujin (company 810) — 2026-07-28.

Re-enriches the 10 pending_review robots: English display names, purpose,
availability, JP country, cleaned taxonomy, citeable cell/AGV specs in
features (not misfiled as arm payload), soft leftovers for RCP / Pallet
Changer, CDN verify.

Prior passes: fix_mujin_robots.py (2026-07-11 media+EN copy; 2026-07-21
curated-full family/availability). This script is the completeness gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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

COMPANY_ID = 810
COMPANY_SLUG = "mujin"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

PAMPHLETS = "https://www.mujin.co.jp/download/pamphlets/"
EUROPE_MIXED = "https://mujin-europe.com/applications/mixed-case-fulfillment"
TEPCO = "https://www.mujin.co.jp/example/tepco-logistics/"
PALLET_DL = "https://www.mujin.co.jp/download/pallet/"

DEAD_SEARCH = (
    "DEAD SEARCH 2026-07-28: Checked exact OEM solution pages, pamphlet index, "
    "exposed PDF/download links, and Mujin Europe application pages. Mujin ships "
    "complete cells without naming the integrated third-party arm model, so "
    "payload_kg/reach_mm/weight_kg/dof/speed are left blank for arm cells. "
    "Published case/hour, handled-work mass/size, and work-envelope figures are "
    "kept in features only (not arm typed columns). AGV page lists multi-SKU "
    "payload/dims/speed columns (MJNAGV03/08/10/15) that disagree — no single "
    "typed payload/dims/speed written (rule 11)."
)

# id → curated completeness patch
ROBOTS: dict[int, dict[str, Any]] = {
    3753: {
        "name": "Mujin Single-SKU Palletizer",
        "en_name": "Mujin Single-SKU Palletizer",
        "url": "https://www.mujin.co.jp/solution/distribution/singlesku-palletize/",
        "family_key": "mujin:single-sku-palletizer",
        "family_name": "Single-SKU Palletizer",
        "scope": "exact_variant",
        "kind": "palletize",
        "purpose": "Uniform-case palletizing\nOutbound pallet build",
        "description": (
            "Mujin Single-SKU Palletizer is a MujinOS-powered case palletizing cell "
            "for uniform-SKU outbound shipping in warehouses and distribution centers."
        ),
        "features": (
            "Official MujinOS product page for Single-SKU / uniform-case palletizing. "
            "Uses Mujin intelligent control for real-time motion planning around "
            "conveyors and pallets. Typical cell: industrial arm + gripper transferring "
            "cases from conveyor to pallet (optionally coordinated with mobile robots "
            "for pallet move-out). OEM page does not publish a fixed case/hour or "
            "handled-work mass table for this MujinOS SKU (unlike MujinRobot Palletizer)."
        ),
        "movement_types": ["stationary"],
        "uses": ["palletizing", "handling", "intralogistics", "warehouse"],
        "industries": ["industrial", "fmcg", "logistics"],
        "sub": "logistics-warehouse",
        "tags": [
            "palletizing", "Warehouse Automation", "Logistics", "Industrial",
            "Intralogistics", "Industrial Arm", "Industrial Robot",
            "Factory Automation", "Pallet Handling",
        ],
        "oem_hero": "https://www.mujin.co.jp/wp-content/uploads/2025/12/robot_arm.jpg",
        "keep_videos": True,
        "sources": [
            "https://www.mujin.co.jp/solution/distribution/singlesku-palletize/",
            PAMPHLETS,
        ],
    },
    3754: {
        "name": "Mujin AGV",
        "en_name": "Mujin AGV",
        "url": "https://www.mujin.co.jp/solution/mobilerobot/agv/",
        "family_key": "mujin:agv",
        "family_name": "Mujin AGV",
        "scope": "family",
        "kind": "agv",
        "purpose": "Pallet and material transport\nAutomated load transfer\nQR-guided fleet conveyance",
        "description": (
            "Mujin QR-code / inertial-guided AGV family for factory and warehouse "
            "material transport with scalable multi-vehicle fleets."
        ),
        "features": (
            "Official Mujin AGV page (QR grid + inertial guidance). Citeable family "
            "models and max payload: MJNAGV03CEP-MB 300 kg; MJNAGV08-MB / MJNAGV08CE-MB "
            "800 kg; MJNAGV10-MB 1,000 kg; MJNAGV15-MB / MJNAGV15CEP-MB 1,500 kg. "
            "Shared across variants: lift height 56 mm; stop accuracy ±10 mm after "
            "position correction; runtime 6–8 h from full charge; LiFePO4 battery; "
            "fleet scale cited up to about 100 units. Empty/loaded top speeds differ "
            "by SKU (e.g. 2.1/1.5 m/s on MJNAGV08-MB; 1.5/1.0 m/s on CEP table). "
            "Outer dims and curb weight also differ by model — not written as a single "
            "typed payload/dims/speed on this family shell. Modular tops (roller "
            "conveyor) shown for load transfer."
        ),
        "movement": "wheeled",
        "uses": "material-handling|handling|intralogistics|warehouse",
        "industries": "industrial|logistics|fmcg",
        "sub": "logistics-warehouse",
        "tags": (
            "AMR|AGV|Warehouse Automation|Logistics|Autonomous Mobile Robot|"
            "Intralogistics|Industrial|Mobile Robot"
        ),
        "oem_hero": "https://www.mujin.co.jp/wp-content/uploads/2026/03/agv_0326.png",
        "keep_videos": True,
        "sources": [
            "https://www.mujin.co.jp/solution/mobilerobot/agv/",
            PAMPHLETS,
        ],
    },
    3755: {
        "name": "MujinRCP",
        "en_name": "MujinRCP",
        "url": TEPCO,
        "family_key": "mujin:rcp",
        "family_name": "MujinRCP",
        "scope": "exact_variant",
        "kind": "sol",
        "purpose": (
            "Multi-SKU case picking for store-ready orders\n"
            "Power-infrastructure logistics handling\n"
            "AGV-sequenced mixed-SKU pallet build"
        ),
        "description": (
            "MujinRCP (Robotic Case Picking) is Mujin's goods-to-robot mixed-SKU case "
            "picking and pallet-build solution, documented on the TEPCO Logistics "
            "deployment page and Mujin Europe mixed-case fulfillment materials."
        ),
        "features": (
            "No dedicated /solution/ PDP on mujin.co.jp — primary JP citation is the "
            "TEPCO Logistics case page. System integrates order-based stack "
            "planning, AGV sequencing, and robot case picking / mixed-load palletizing "
            "for multi-variety power-infrastructure materials. Mujin Europe positions "
            "the same capability as Robotic Case Picking / Mixed-Case Fulfillment "
            "(order pallets built autonomously by MujinOS). Official Mujin Europe "
            "product video cites about 300–400 cases/hour per robot station for the "
            "RCP cell class — recorded in features, not as an arm payload column. "
            "Treat as solution reference until a standalone JP PDP appears."
        ),
        "movement": "stationary",
        "uses": "picking|palletizing|handling|intralogistics|warehouse",
        "industries": "industrial|logistics|energy",
        "sub": "logistics-warehouse",
        "tags": (
            "Warehouse Automation|Logistics|Industrial|Intralogistics|"
            "Industrial Robot|Factory Automation|Pallet Handling|Pick-and-Place|picking"
        ),
        "oem_hero": "https://www.mujin.co.jp/wp-content/uploads/2026/06/tpclg.png",
        # Keep TEPCO case video; add Europe RCP clip (official Mujin)
        "videos": [
            "https://www.youtube.com/watch?v=SMPin1JuTM0",
            "https://www.youtube.com/watch?v=XVd1q2kYOVg",
        ],
        "hold": (
            "No standalone OEM solution PDP or typed arm/cell datasheet on mujin.co.jp; "
            "TEPCO case + Mujin Europe mixed-case page / RCP video only."
        ),
        "sources": [TEPCO, EUROPE_MIXED, PAMPHLETS],
    },
    3756: {
        "name": "MujinRobot Depalletizer (Space-saving Mixed-load)",
        "en_name": "MujinRobot Depalletizer (Space-saving Mixed-load)",
        "url": "https://www.mujin.co.jp/solution/distribution/depalletize/",
        "family_key": "mujin:depalletizer",
        "family_name": "MujinRobot Depalletizer",
        "scope": "family",
        "kind": "depal",
        "purpose": (
            "Space-saving mixed-SKU case depalletizing\n"
            "Inbound mixed-load unloading to conveyor"
        ),
        "description": (
            "MujinRobot Depalletizer configured for space-saving mixed-SKU case "
            "unloading in dense distribution-center footprints."
        ),
        "features": (
            "Same official MujinRobot Depalletizer solution page as the standard "
            "family twin (3757). OEM cites up to 1,000 cs/h single-SKU and up to "
            "600 cs/h mixed-SKU. Standard-spec table: handled-work mass max 25 kg; "
            "standard hand work size up to 600×600×600 mm (min 225×150×80 mm); "
            "recognition range up to 1250×1250×2000 mm including pallet. This CRM "
            "row keeps the mixed-load / compact-layout positioning with a distinct "
            "installation hero; it is not a separately typed arm SKU. Cell workload "
            "figures are not written as arm payload/reach."
        ),
        "movement": "stationary",
        "uses": "palletizing|handling|intralogistics|warehouse|picking",
        "industries": "industrial|fmcg|logistics",
        "sub": "logistics-warehouse",
        "tags": (
            "palletizing|Warehouse Automation|Logistics|Industrial|Intralogistics|"
            "Industrial Arm|Industrial Robot|Factory Automation|Pallet Handling|Pick-and-Place"
        ),
        "oem_hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/g01min.jpg",
        "keep_videos": True,
        "sources": [
            "https://www.mujin.co.jp/solution/distribution/depalletize/",
            PAMPHLETS,
        ],
        "variant_note": (
            "Genuine layout/application variant of mujin:depalletizer (mixed-SKU / "
            "space-saving positioning). Shares OEM PDP with 3757; distinct hero + purpose."
        ),
    },
    3757: {
        "name": "MujinRobot Depalletizer",
        "en_name": "MujinRobot Depalletizer",
        "url": "https://www.mujin.co.jp/solution/distribution/depalletize/",
        "family_key": "mujin:depalletizer",
        "family_name": "MujinRobot Depalletizer",
        "scope": "family",
        "kind": "depal",
        "purpose": "Single-SKU case depalletizing\nMixed-SKU case depalletizing\nInbound unloading to conveyor",
        "description": (
            "MujinRobot Depalletizer is a vision-guided case unloading cell for "
            "single-SKU and mixed-SKU pallets in logistics inbound."
        ),
        "features": (
            "Official MujinRobot Depalletizer solution. Throughput: up to 1,000 cs/h "
            "(single-SKU) and up to 600 cs/h (mixed-SKU). Standard-spec table: max "
            "handled-work mass 25 kg; standard hand work envelope up to 600×600×600 mm "
            "(min 225×150×80 mm); recognition range up to 1250×1250×2000 mm including "
            "pallet; indoor install; floor load ≥1.5 t/m². Built with Mujin intelligent "
            "control / 3D vision. Integrated arm model is not named — cell limits stay "
            "in features, not arm typed columns."
        ),
        "movement": "stationary",
        "uses": "palletizing|handling|intralogistics|warehouse|picking",
        "industries": "industrial|fmcg|logistics",
        "sub": "logistics-warehouse",
        "tags": (
            "palletizing|Warehouse Automation|Logistics|Industrial|Intralogistics|"
            "Industrial Arm|Industrial Robot|Factory Automation|Pallet Handling|Pick-and-Place"
        ),
        "oem_hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/k01.jpg",
        "keep_videos": True,
        "sources": [
            "https://www.mujin.co.jp/solution/distribution/depalletize/",
            PAMPHLETS,
        ],
    },
    3758: {
        "name": "MujinRobot Pallet Changer",
        "en_name": "MujinRobot Pallet Changer",
        "url": PALLET_DL,
        "family_key": "mujin:pallet-changer",
        "family_name": "MujinRobot Pallet Changer",
        "scope": "exact_variant",
        "kind": "sol",
        "purpose": (
            "Case restacking between different pallet sizes\n"
            "AGV-coordinated pallet transfer"
        ),
        "description": (
            "MujinRobot Pallet Changer automates restacking cases between different "
            "pallet sizes, optionally with AGV collaboration for pallet transport."
        ),
        "features": (
            "Official Mujin intro/download landing for Pallet Changer "
            "(/download/pallet/) — no dedicated /solution/ PDP. Uses Mujin 3D vision "
            "for case recognition and restacks onto different pallet sizes; marketing "
            "materials highlight AGV collaboration to automate pallet conveyance after "
            "restack. Aimed at replacing heavy manual pallet-transfer labor. No "
            "citeable typed system dimensions, payload, or throughput on the download "
            "page or pamphlet index. Prior TruckBot YouTube attachment removed "
            "(wrong product)."
        ),
        "movement": "stationary",
        "uses": "palletizing|handling|intralogistics|warehouse",
        "industries": "industrial|logistics|fmcg",
        "sub": "logistics-warehouse",
        "tags": (
            "Warehouse Automation|Logistics|Industrial|Intralogistics|"
            "Industrial Robot|Factory Automation|Pallet Handling"
        ),
        "oem_hero": "https://www.mujin.co.jp/wp-content/uploads/2025/03/pallet01.png",
        "videos": [],  # clear wrong TruckBot; no exact-model OEM clip found
        "hold": (
            "Download hub only; marketing collage hero is the only OEM visual; no "
            "solution PDP or typed specs. Wrong TruckBot YouTube (6941) still "
            "attached — empty video_urls does not clear; staff must soft-delete via "
            "content-queue videos admin_view."
        ),
        "sources": [PALLET_DL, PAMPHLETS],
    },
    3759: {
        "name": "MujinRobot Palletizer",
        "en_name": "MujinRobot Palletizer",
        "url": "https://www.mujin.co.jp/solution/distribution/palletize/",
        "family_key": "mujin:palletizer",
        "family_name": "MujinRobot Palletizer",
        "scope": "exact_variant",
        "kind": "palletize",
        "purpose": "Mixed-load palletizing\nHeavy-case palletizing\nOutbound shipping pallet build",
        "description": (
            "MujinRobot Palletizer is a high-rate case palletizing robot cell for "
            "warehouse outbound shipping."
        ),
        "features": (
            "Official MujinRobot Palletizer page. Throughput up to 500 cs/h. "
            "Standard-spec table: max handled-work mass 25 kg; standard hand work "
            "size up to 650×650×600 mm (min 225×150×100 mm); recognition range up to "
            "1250×1250×1800 mm including pallet; indoor; floor load ≥1.5 t/m². "
            "Mujin intelligent control / real-time planning. Arm model unnamed — cell "
            "limits in features only."
        ),
        "movement": "stationary",
        "uses": "palletizing|handling|intralogistics|warehouse",
        "industries": "industrial|fmcg|logistics",
        "sub": "logistics-warehouse",
        "tags": (
            "palletizing|Warehouse Automation|Logistics|Industrial|Intralogistics|"
            "Industrial Arm|Industrial Robot|Factory Automation|Pallet Handling"
        ),
        "oem_hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/h01.jpg",
        "keep_videos": True,
        "sources": [
            "https://www.mujin.co.jp/solution/distribution/palletize/",
            PAMPHLETS,
        ],
    },
    3760: {
        "name": "MujinRobot Piece Picker",
        "en_name": "MujinRobot Piece Picker",
        "url": "https://www.mujin.co.jp/solution/distribution/picking/",
        "family_key": "mujin:piece-picker",
        "family_name": "MujinRobot Piece Picker",
        "scope": "exact_variant",
        "kind": "pick",
        "purpose": "High-mix piece picking\nSorter and tote induction\nEach-picking from totes",
        "description": (
            "MujinRobot Piece Picker is a high-rate, high-mix piece-picking robot for "
            "distribution centers."
        ),
        "features": (
            "Official MujinRobot Piece Picker page. Throughput up to 1,000 pcs/h. "
            "Standard-spec table: max handled-work mass 2.0 kg; work size up to "
            "350×300×300 mm (min 30×30×20 mm); max tote inner dims 550×380×380 mm; "
            "indoor; floor load ≥1.0 t/m². Vision-guided piece handling into "
            "totes/sorters. Arm model unnamed — cell limits in features only."
        ),
        "movement": "stationary",
        "uses": "picking|pick-and-place|handling|intralogistics|warehouse",
        "industries": "industrial|fmcg|logistics",
        "sub": "logistics-warehouse",
        "tags": (
            "picking|Pick-and-Place|Warehouse Automation|Logistics|Industrial|"
            "Intralogistics|Industrial Arm|Industrial Robot|Factory Automation"
        ),
        "oem_hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/l01.jpg",
        "keep_videos": True,
        "sources": [
            "https://www.mujin.co.jp/solution/distribution/picking/",
            PAMPHLETS,
        ],
    },
    3762: {
        "name": "PickWorker",
        "en_name": "PickWorker",
        "url": "https://www.mujin.co.jp/solution/fa/picking/",
        "family_key": "mujin:pickworker",
        "family_name": "PickWorker",
        "scope": "exact_variant",
        "kind": "bin",
        "purpose": "Random bin picking\nMachine and assembly line feeding\nTeach-less 3D parts supply",
        "description": (
            "PickWorker is Mujin's teach-less 3D bin-picking package for factory parts "
            "supply and machine tending."
        ),
        "features": (
            "Official PickWorker FA package page. Automates random bin picking without "
            "traditional teach programming; covers system components through "
            "integration support. Targets bulk parts feed to machining or assembly. "
            "OEM page does not expose a fixed payload/reach/speed table for a named "
            "arm SKU."
        ),
        "movement": "stationary",
        "uses": "picking|pick-and-place|handling|machine-tending",
        "industries": "industrial|manufacturing|automotive",
        "sub": "manufacturing-industrial",
        "tags": (
            "picking|Pick-and-Place|Factory Automation|Industrial|Industrial Arm|"
            "Industrial Robot|Manufacturing"
        ),
        "oem_hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/i01min.jpg",
        "keep_videos": True,
        "sources": [
            "https://www.mujin.co.jp/solution/fa/picking/",
            PAMPHLETS,
        ],
    },
    3763: {
        "name": "Returnable-Container Depalletize/Palletize Robot",
        "en_name": "Returnable-Container Depalletize/Palletize Robot",
        "url": "https://www.mujin.co.jp/solution/fa/containerdepalletize/",
        "family_key": "mujin:returnable-container",
        "family_name": "Returnable-Container Handling",
        "scope": "exact_variant",
        "kind": "depal",
        "purpose": (
            "Returnable-container depalletizing\n"
            "Returnable-container palletizing\n"
            "Mixed tote stack handling"
        ),
        "description": (
            "Mujin returnable-container (tote) depalletize/palletize robot for mixed "
            "factory logistics containers."
        ),
        "features": (
            "Official FA container depalletize/palletize page. Mujin stacking "
            "algorithms with a variable hand claimed to support 50+ returnable "
            "container types, including mixed stacks. Standard-spec table: cycle about "
            "13 s/cs (varies with work); work size max 670×335×241 mm (min "
            "335×168×103 mm); stack envelope 1100×1100×1500 mm; max work mass 20 kg; "
            "fixed camera mount height 2000 mm above max stack. Aimed at automotive / "
            "factory parts-supply logistics. Arm model unnamed — cell limits in "
            "features only."
        ),
        "movement": "stationary",
        "uses": "palletizing|handling|intralogistics|picking",
        "industries": "industrial|automotive|manufacturing",
        "sub": "manufacturing-industrial",
        "tags": (
            "palletizing|Pick-and-Place|Factory Automation|Industrial|Industrial Arm|"
            "Industrial Robot|Intralogistics|Logistics|Pallet Handling|Warehouse Automation"
        ),
        "oem_hero": "https://www.mujin.co.jp/wp-content/uploads/2023/10/cdp_tp.jpg",
        "keep_videos": True,
        "sources": [
            "https://www.mujin.co.jp/solution/fa/containerdepalletize/",
            PAMPHLETS,
        ],
    },
}


def _notes(cur: dict[str, Any]) -> str:
    parts = [f"[CURATED FULL 2026-07-28] {DEAD_SEARCH}"]
    if cur.get("variant_note"):
        parts.append(f"VARIANT: {cur['variant_note']}")
    if cur.get("hold"):
        parts.append(f"HOLD: {cur['hold']}")
    return " ".join(parts)


def _as_list(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    return [p.strip() for p in re.split(r"[|,]", str(val)) if p.strip()]


def build_patch(cur: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    # Serializer accepts movement_types / uses / industries / tags (lists or
    # key lookups). Bulk-import-only *_keys fields are ignored on PATCH.
    movement = cur.get("movement_types") or cur.get("movement") or "stationary"
    uses = cur.get("uses") or []
    industries = cur.get("industries") or []
    tags = cur.get("tags") or []
    patch: dict[str, Any] = {
        "name": cur["name"],
        "model_name": cur["en_name"],
        "variant_code": cur["en_name"],
        "variant_label": cur["name"],
        "description": cur["description"],
        "purpose": cur["purpose"],
        "features": cur["features"],
        "url": cur["url"],
        "family_key": cur["family_key"],
        "family_name": cur["family_name"],
        "family_url": cur["url"],
        "product_url_scope": cur["scope"],
        "availability_status": 11,
        "manufacturer_country_code": "JP",
        "movement_types": _as_list(movement),
        "uses": _as_list(uses),
        "industries": _as_list(industries),
        "category_slugs": "industrial-robots",
        "sub_category_slug": cur["sub"],
        "tags": _as_list(tags),
        "information_source_urls": list(dict.fromkeys(cur["sources"])),
        "dof": None,
        "payload_kg": None,
        "reach_mm": None,
        "weight_kg": None,
        "speed": None,
        "status": "pending_review",
        "notes": _notes(cur),
    }
    # Re-source OEM hero for copy-media when CDN path is owned (refresh path)
    if cur.get("oem_hero"):
        patch["image"] = cur["oem_hero"]
    # Empty video_urls does NOT clear existing videos (serializer requires len>0).
    # Non-empty lists replace. Soft-delete of wrong clips needs staff admin_view.
    if cur.get("videos"):
        patch["video_urls"] = cur["videos"]
    # Guard: no JP/mojibake in EN fields
    blob = f"{patch['description']} {patch['features']} {patch['purpose']} {patch['name']}"
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", blob) or "ã" in blob or "å" in blob[:200]:
        raise ValueError(f"non-English content in EN fields for {cur['name']}")
    return patch


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("WARN: missing INTERNAL_API_SECRET or API base for copy-media")
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
                print(f"copy-media ok {rid}")
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code} {resp.text[:200]}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.15)
    return ok, fail


def verify_cdn(client: ResearchApiClient, ids: list[int]) -> dict[str, Any]:
    results = []
    hashes: dict[str, list[int]] = {}
    for rid in ids:
        r = client._get(f"robots/robots/{rid}/")
        img = r.get("s3_image") or r.get("image") or ""
        item: dict[str, Any] = {"id": rid, "name": r.get("name"), "url": img}
        if not img:
            item["ok"] = False
            item["reason"] = "no_image"
            results.append(item)
            continue
        try:
            resp = requests.get(img, headers=HEADERS, timeout=40)
            body = resp.content
            magic_ok = (
                body[:3] == b"\xff\xd8\xff"
                or body[:8] == b"\x89PNG\r\n\x1a\n"
                or (body[:4] == b"RIFF" and b"WEBP" in body[8:16])
            )
            h = hashlib.md5(body).hexdigest()
            item.update(
                {
                    "http": resp.status_code,
                    "nbytes": len(body),
                    "md5": h,
                    "is_image": magic_ok,
                    "ok": resp.status_code == 200 and magic_ok and len(body) > 5000,
                }
            )
            hashes.setdefault(h, []).append(rid)
        except requests.RequestException as exc:
            item.update({"ok": False, "error": str(exc)})
        results.append(item)
    dups = {h: ids_ for h, ids_ in hashes.items() if len(ids_) > 1}
    return {
        "ok_count": sum(1 for x in results if x.get("ok")),
        "total": len(results),
        "dup_hashes": dups,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mujin 810 completeness pass")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--only", nargs="*", type=int)
    args = parser.parse_args()

    client = ResearchApiClient()
    existing = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if int(r["id"]) in ROBOTS
    }
    targets = sorted(ROBOTS)
    if args.only:
        targets = [i for i in targets if i in set(args.only)]

    plan = []
    for rid in targets:
        cur = ROBOTS[rid]
        robot = existing.get(rid)
        if not robot:
            print(f"MISSING {rid}", file=sys.stderr)
            continue
        patch = build_patch(cur, robot)
        plan.append(
            {
                "id": rid,
                "old_name": robot.get("name"),
                "new_name": patch["name"],
                "outcome": "held" if cur.get("hold") else "enriched",
                "hold": cur.get("hold") or "",
                "family_key": patch["family_key"],
                "purpose": patch["purpose"],
                "avail": patch["availability_status"],
                "movement": patch["movement_types"],
                "feat_len": len(patch["features"]),
                "videos": patch.get("video_urls"),
            }
        )
        print(
            f"{rid} {robot.get('name')!r} → {patch['name']!r} "
            f"[{plan[-1]['outcome']}] feat={plan[-1]['feat_len']}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "mujin-810-completeness-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Preview: {preview}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply --copy-media --verify-cdn")
        return 0

    patched: list[int] = []
    for rid in targets:
        cur = ROBOTS[rid]
        robot = existing.get(rid)
        if not robot:
            continue
        patch = build_patch(cur, robot)
        # Field-at-a-time for fragile keys
        fragile = {
            "availability_status",
            "manufacturer_country_code",
            "movement_types",
            "uses",
            "industries",
            "category_slugs",
            "sub_category_slug",
            "tags",
            "video_urls",
            "image",
            "dof",
            "payload_kg",
            "reach_mm",
            "weight_kg",
            "speed",
        }
        core = {k: v for k, v in patch.items() if k not in fragile}
        try:
            client._patch(f"robots/robots/{rid}/", core)
            for k in fragile:
                if k not in patch:
                    continue
                try:
                    client._patch(f"robots/robots/{rid}/", {k: patch[k]})
                except Exception as exc:
                    print(f"  soft-fail {rid}.{k}: {exc}", file=sys.stderr)
            patched.append(rid)
            print(f"patched {rid} {patch['name']}")
        except Exception as exc:
            print(f"PATCH FAIL {rid}: {exc}", file=sys.stderr)

    copy_stats = None
    if args.copy_media and patched:
        # Only re-copy robots we set oem_hero on
        media_ids = [rid for rid in patched if ROBOTS[rid].get("oem_hero")]
        ok, fail = trigger_copy_media(media_ids)
        copy_stats = {"requested": len(media_ids), "ok": ok, "fail": fail}

    cdn = None
    if args.verify_cdn and patched:
        cdn = verify_cdn(client, patched)
        cdn_path = _RESEARCH_DIR / "staging" / "reports" / "mujin-810-cdn-verify.json"
        cdn_path.write_text(json.dumps(cdn, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"CDN verify: {cdn['ok_count']}/{cdn['total']} dups={cdn['dup_hashes']}")
        print(f"CDN report: {cdn_path}")

    summary = {
        "company_id": COMPANY_ID,
        "patched": patched,
        "enriched": [p["id"] for p in plan if p["outcome"] == "enriched"],
        "held": [p["id"] for p in plan if p["outcome"] == "held"],
        "rejected": [],
        "copy_media": copy_stats,
        "cdn": {
            "ok_count": (cdn or {}).get("ok_count"),
            "total": (cdn or {}).get("total"),
            "dup_hashes": (cdn or {}).get("dup_hashes"),
        }
        if cdn
        else None,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
