#!/usr/bin/env python3
"""
fix_ae_robotics.py
------------------
Fix all data quality issues for AE Robotics (company 1375):
  1. manufacturer_countries — all 41 robots missing it
  2. description — 19 robots have very short descriptions (<100 chars)
  3. price_min — 19 robots missing price
  4. payload_kg / reach_mm / repeatability_mm / weight_kg — missing specs
  5. features — 4 robots missing features

Usage:
    python fix_ae_robotics.py --dry-run     # preview changes
    python fix_ae_robotics.py               # apply to production
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
load_research_env()

from api_client import ResearchApiClient

COMPANY_ID = 1375
REPORT_DIR = _HERE / "staging" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Country codes for manufacturer assignment
# AE-owned robots → CN; reseller robots → OEM country
# ---------------------------------------------------------------------------
RESELLER_COUNTRY = {
    # Universal Robots → Denmark
    "Universal Robot UR3": "DK",
    "Universal Robot UR5": "DK",
    "Universal Robot UR10": "DK",
    # Fanuc → Japan
    "Fanuc R-2000iC/210L": "JP",
    "Fanuc R-2000iC/165F": "JP",
    "Fanuc R-2000iC/125L": "JP",
    "Fanuc R-2000iC/210F": "JP",
    # AUBO → China (AUBO Robotics is Chinese)
    "AUBO-I3 Collaborative Robot": "CN",
    "AUBO-I5 Collaborative Robot": "CN",
    "AUBO-I7 Collaborative Robot": "CN",
    "AUBO-I16 Collaborative Robot": "CN",
    "AUBO-I3FB Explosion Proof Painting Cobot": "CN",
    "AUBO-I5FB Explosion Proof Cobot": "CN",
    "AUBO-I10FB 6-Axis Explosion Proof Painting Cobot": "CN",
    "AUBO 6-axis Cobot Welding Station MOS-W-I5-350-1000C": "CN",
    # JAKA → China
    "JAKA Zu3 Cobot": "CN",
    "JAKA Zu7 Cobot": "CN",
    "JAKA Zu12 Cobot": "CN",
    "JAKA Zu18 Cobot": "CN",
    # Youibot → China
    "Youibot Corgi 50kg Load Mobile Industrial Robot": "CN",
    # Trans robots (AE-branded AGVs) → CN
    "Trans 200 Mobile Industrial Robot": "CN",
    "Trans 500 Mobile Industrial Robot": "CN",
}

# ---------------------------------------------------------------------------
# Per-robot data patches: description, price, specs, features
# Keyed by robot ID (int). Only fields that need fixing are included.
# ---------------------------------------------------------------------------
ROBOT_PATCHES: dict[int, dict] = {
    # ---- AIR3-A variants ----
    1446: {
        "description": (
            "AE AIR3-A is a compact 6-axis industrial robot arm with 3 kg payload and 560 mm arm reach, "
            "manufactured in Shenzhen, China. It uses Japan Nabtesco RV gearbox and Leaderdrive harmonic "
            "gearbox, communicating via high-speed EtherCAT bus. CE and CCC certified, suitable for pick "
            "& place and assembly tasks in manufacturing environments."
        ),
        "features": (
            "6-axis articulated design with 3 kg payload capacity and 560 mm arm reach. Uses Japan Nabtesco "
            "RV gearbox reducer and Leaderdrive harmonic gearbox for precision motion. EtherCAT high-speed "
            "bus communication across all joints. Position repeatability of ±0.02 mm. IP65 protection rating. "
            "Supports floor, wall, and ceiling mounting. CE and CCC certified."
        ),
        "payload_kg": 3.0,
        "reach_mm": 560,
        "repeatability_mm": 0.02,
        "weight_kg": 23.0,
        "price_min": 4699,
        "price_max": 12960,
        "price_currency": "USD",
    },
    1447: {  # AE AIR3-a (Desktop)
        "description": (
            "AE AIR3-A (Desktop) is a compact 6-axis industrial robot arm with 3 kg payload and 560 mm arm "
            "reach, designed for desktop and low-cost automation tasks. Uses Japan Nabtesco RV gearbox and "
            "Leaderdrive harmonic gearbox with EtherCAT bus communication. CE and CCC certified."
        ),
        "features": (
            "6-axis articulated design with 3 kg payload capacity and 560 mm arm reach. Uses Japan Nabtesco "
            "RV gearbox reducer and Leaderdrive harmonic gearbox for precision motion. EtherCAT high-speed "
            "bus communication. Position repeatability of ±0.02 mm. Compact desktop form factor. "
            "CE and CCC certified."
        ),
        "payload_kg": 3.0,
        "reach_mm": 560,
        "repeatability_mm": 0.02,
        "weight_kg": 23.0,
        "price_min": 4699,
        "price_currency": "USD",
    },
    4831: {  # AE AIR3-A Industrial Robotic Arm (newer entry)
        "description": (
            "AE AIR3-A is a compact 6-axis industrial robot arm with 3 kg payload and 560 mm arm reach, "
            "manufactured in Shenzhen, China. It uses Japan Nabtesco RV gearbox and Leaderdrive harmonic "
            "gearbox, communicating via high-speed EtherCAT bus. CE and CCC certified, suitable for pick "
            "& place and assembly tasks in manufacturing environments."
        ),
        "features": (
            "6-axis articulated design with 3 kg payload capacity and 560 mm arm reach. Uses Japan Nabtesco "
            "RV gearbox reducer and Leaderdrive harmonic gearbox for precision motion. EtherCAT high-speed "
            "bus communication across all joints. Position repeatability of ±0.02 mm. IP65 protection rating. "
            "Supports floor, wall, and ceiling mounting. CE and CCC certified."
        ),
        "payload_kg": 3.0,
        "reach_mm": 560,
        "repeatability_mm": 0.02,
        "weight_kg": 23.0,
        "price_min": 4699,
        "price_currency": "USD",
    },
    # ---- AIR7L-B variants ----
    1448: {
        "description": (
            "AE AIR7L-B is a 6-axis industrial robot arm with 7 kg payload and 920 mm arm reach, designed "
            "for arc welding, pick & place, and intelligent manipulation tasks. Manufactured in Guangdong, "
            "China with CE and CCC certification."
        ),
        "features": (
            "7 kg payload with 920 mm arm reach for arc welding and pick & place applications. 6-axis "
            "articulated design with ±0.02 mm position repeatability. inCube 20 controller with English "
            "programming interface. Supports floor, wall, and ceiling mounting. CE and CCC certified. "
            "53 kg robot body weight."
        ),
        "payload_kg": 7.0,
        "reach_mm": 920,
        "repeatability_mm": 0.02,
        "weight_kg": 53.0,
        "price_min": 4699,
        "price_currency": "USD",
    },
    4832: {  # AE AIR7L-B Arc Welding Robot (newer entry)
        "description": (
            "AE AIR7L-B is a 6-axis industrial robot arm with 7 kg payload and 920 mm arm reach, designed "
            "for arc welding, pick & place, and intelligent manipulation tasks. Manufactured in Guangdong, "
            "China with CE and CCC certification."
        ),
        "features": (
            "7 kg payload with 920 mm arm reach for arc welding and pick & place applications. 6-axis "
            "articulated design with ±0.02 mm position repeatability. inCube 20 controller with English "
            "programming interface. Supports floor, wall, and ceiling mounting. CE and CCC certified. "
            "53 kg robot body weight."
        ),
        "payload_kg": 7.0,
        "reach_mm": 920,
        "repeatability_mm": 0.02,
        "weight_kg": 53.0,
        "price_min": 4699,
        "price_currency": "USD",
    },
    # ---- AIR8-A variants ----
    1449: {
        "description": (
            "AE AIR8-A is a 6-axis industrial robot arm with 8 kg payload and 710 mm arm reach, designed "
            "for milling, cutting, and pick & place programming tasks. Manufactured in Guangdong, China "
            "with CE and CCC certification."
        ),
        "features": (
            "8 kg payload with 710 mm arm reach for milling, cutting, and pick & place applications. "
            "6-axis articulated design with ±0.02 mm position repeatability. EtherCAT high-speed "
            "communication protocol. English programming interface with 16/16 DI/O. CE and CCC certified. "
            "45 kg robot body weight."
        ),
        "payload_kg": 8.0,
        "reach_mm": 710,
        "repeatability_mm": 0.02,
        "weight_kg": 45.0,
        "price_min": 4899,
        "price_currency": "USD",
    },
    4833: {  # AE AIR8-A Industrial Robot (newer entry)
        "description": (
            "AE AIR8-A is a 6-axis industrial robot arm with 8 kg payload and 710 mm arm reach, designed "
            "for milling, cutting, and pick & place programming tasks. Manufactured in Guangdong, China "
            "with CE and CCC certification."
        ),
        "features": (
            "8 kg payload with 710 mm arm reach for milling, cutting, and pick & place applications. "
            "6-axis articulated design with ±0.02 mm position repeatability. EtherCAT high-speed "
            "communication protocol. English programming interface with 16/16 DI/O. CE and CCC certified. "
            "45 kg robot body weight."
        ),
        "payload_kg": 8.0,
        "reach_mm": 710,
        "repeatability_mm": 0.02,
        "weight_kg": 45.0,
        "price_min": 4899,
        "price_currency": "USD",
    },
    # ---- AIR10-A variants ----
    1450: {
        "description": (
            "AE AIR10-A is a 6-axis industrial robot arm with 10 kg payload and 1420 mm arm reach, designed "
            "for welding, handling, and high-speed automation tasks. Manufactured in Guangdong, China with "
            "CE and CCC certification."
        ),
        "features": (
            "10 kg payload with 1420 mm arm reach for welding and high-speed industrial automation. "
            "6-axis articulated design with English programming interface. 16/16 DI/O user interface. "
            "Single phase 220V power supply. CE and CCC certified. 160 kg robot body weight."
        ),
        "payload_kg": 10.0,
        "reach_mm": 1420,
        "weight_kg": 160.0,
        "price_min": 4950,
        "price_currency": "USD",
    },
    4834: {  # AE AIR10-A Industrial Robot (newer entry)
        "description": (
            "AE AIR10-A is a 6-axis industrial robot arm with 10 kg payload and 1420 mm arm reach, designed "
            "for welding, handling, and high-speed automation tasks. Manufactured in Guangdong, China with "
            "CE and CCC certification."
        ),
        "features": (
            "10 kg payload with 1420 mm arm reach for welding and high-speed industrial automation. "
            "6-axis articulated design with English programming interface. 16/16 DI/O user interface. "
            "Single phase 220V power supply. CE and CCC certified. 160 kg robot body weight."
        ),
        "payload_kg": 10.0,
        "reach_mm": 1420,
        "weight_kg": 160.0,
        "price_min": 4950,
        "price_currency": "USD",
    },
    # ---- AIR20-A variants ----
    1451: {
        "description": (
            "AE AIR20-A is a 6-axis industrial robot with 20 kg payload and 1702 mm arm reach, manufactured "
            "in Shenzhen, China. Uses Japan Nabtesco RV gearbox and Leaderdrive harmonic gearbox with "
            "EtherCAT bus communication. Suitable for palletizing and welding applications."
        ),
        "features": (
            "20 kg payload with 1702 mm arm reach for palletizing and welding applications. 6-axis "
            "articulated design using Japan Nabtesco RV gearbox and Leaderdrive harmonic gearbox. "
            "EtherCAT high-speed bus communication. Position repeatability of ±0.03 mm. inCube12 "
            "controller with English interface. CE and CCC certified. 260 kg robot body weight."
        ),
        "payload_kg": 20.0,
        "reach_mm": 1702,
        "repeatability_mm": 0.03,
        "weight_kg": 260.0,
        "price_min": 11900,
        "price_currency": "USD",
    },
    3534: {  # AE AIR20-A Industrial Robot (newer entry)
        "description": (
            "AE AIR20-A is a 6-axis industrial robot with 20 kg payload and 1702 mm arm reach, manufactured "
            "in Shenzhen, China. Uses Japan Nabtesco RV gearbox and Leaderdrive harmonic gearbox with "
            "EtherCAT bus communication. Suitable for palletizing and welding applications."
        ),
        "features": (
            "20 kg payload with 1702 mm arm reach for palletizing and welding applications. 6-axis "
            "articulated design using Japan Nabtesco RV gearbox and Leaderdrive harmonic gearbox. "
            "EtherCAT high-speed bus communication. Position repeatability of ±0.03 mm. inCube12 "
            "controller with English interface. CE and CCC certified. 260 kg robot body weight."
        ),
        "payload_kg": 20.0,
        "reach_mm": 1702,
        "repeatability_mm": 0.03,
        "weight_kg": 260.0,
        "price_min": 11900,
        "price_currency": "USD",
    },
    # ---- AE SCARA (TS5-600) ----
    1454: {
        "description": (
            "AE TS5-600 is a 4-axis SCARA robot with 5 kg payload and 600 mm arm reach, designed for "
            "assembly, handling, and screw-driving tasks. Manufactured in Shenzhen, China with CE "
            "certification."
        ),
        "features": (
            "4-axis SCARA design with 5 kg payload and 600 mm arm reach. Position repeatability of "
            "±0.02 mm (XY) and ±0.01 mm (Z). Maximum speed up to 300°/s on primary axes. 7-inch "
            "teaching pendant interface with optional vision positioning module. Supports PTP, LINE, "
            "PICK, and PLACE motion instructions. CE certified. 20 kg robot body weight."
        ),
        "payload_kg": 5.0,
        "reach_mm": 600,
        "repeatability_mm": 0.02,
        "weight_kg": 20.0,
        "price_min": 4500,
        "price_currency": "USD",
    },
    # ---- Delta robots ----
    1455: {  # AE Delta Robot (AR-600D based on URL)
        "description": (
            "AE AR-600D is a 3/4-axis delta robot with 1 kg payload and 600 mm working diameter, designed "
            "for high-speed pick & place and packing applications. Features ultra-high speed pick-up with "
            "multiple cycles per second. Manufactured in Shenzhen, China."
        ),
        "features": (
            "3/4-axis parallel delta mechanism with 1 kg payload and 600 mm working diameter. High carrying "
            "capacity with small self-loading ratio and good dynamic performance. Ultra-high speed pick-up "
            "capability with multiple cycles per second. ±0.1 mm repetition accuracy. Optional 130W vision "
            "positioning module. WSC-GJK2-T4 electrical control system. Suspension mounting."
        ),
        "payload_kg": 1.0,
        "reach_mm": 600,
        "repeatability_mm": 0.1,
        "weight_kg": 67.0,
    },
    3531: {  # Delta Robot AR-600D
        "description": (
            "AE AR-600D is a 3/4-axis delta robot with 1 kg payload and 600 mm working diameter, designed "
            "for high-speed pick & place and packing applications. Features ultra-high speed pick-up with "
            "multiple cycles per second. Manufactured in Shenzhen, China."
        ),
        "features": (
            "3/4-axis parallel delta mechanism with 1 kg payload and 600 mm working diameter. High carrying "
            "capacity with small self-loading ratio and good dynamic performance. Ultra-high speed pick-up "
            "capability with multiple cycles per second. ±0.1 mm repetition accuracy. Optional 130W vision "
            "positioning module. WSC-GJK2-T4 electrical control system. Suspension mounting."
        ),
        "payload_kg": 1.0,
        "reach_mm": 600,
        "repeatability_mm": 0.1,
        "weight_kg": 67.0,
    },
    4819: {  # Delta Robot AR-500D
        "description": (
            "AE AR-500D is a 3/4-axis delta robot with 1 kg payload and 500 mm working diameter, designed "
            "for high-speed pick & place and packing applications. Features ultra-high speed pick-up with "
            "multiple cycles per second. Manufactured in Shenzhen, China."
        ),
        "features": (
            "3/4-axis parallel delta mechanism with 1 kg payload and 500 mm working diameter. High carrying "
            "capacity with small self-loading ratio and good dynamic performance. Ultra-high speed pick-up "
            "capability with multiple cycles per second. ±0.1 mm repetition accuracy. Optional 130W vision "
            "positioning module. WSC-GJK2-T4 electrical control system. Suspension mounting."
        ),
        "payload_kg": 1.0,
        "reach_mm": 500,
        "repeatability_mm": 0.1,
        "weight_kg": 30.0,
    },
    4820: {  # Delta Robot AR-800D
        "description": (
            "AE AR-800D is a 3/4-axis delta robot with 3 kg payload and 800 mm working diameter, designed "
            "for high-speed pick & place and packing applications. Features ultra-high speed pick-up with "
            "multiple cycles per second. Manufactured in Shenzhen, China."
        ),
        "features": (
            "3/4-axis parallel delta mechanism with 3 kg payload and 800 mm working diameter. High carrying "
            "capacity with small self-loading ratio and good dynamic performance. Ultra-high speed pick-up "
            "capability with multiple cycles per second. ±0.1 mm repetition accuracy. Optional 130W vision "
            "positioning module. WSC-GJK2-T4 electrical control system. Suspension mounting."
        ),
        "payload_kg": 3.0,
        "reach_mm": 800,
        "repeatability_mm": 0.1,
        "weight_kg": 67.0,
    },
    4821: {  # Delta Robot AR-1000D
        "description": (
            "AE AR-1000D is a 3/4-axis delta robot with 5 kg payload and 1000 mm working diameter, designed "
            "for high-speed pick & place and packing applications. Features ultra-high speed pick-up with "
            "multiple cycles per second. Manufactured in Shenzhen, China."
        ),
        "features": (
            "3/4-axis parallel delta mechanism with 5 kg payload and 1000 mm working diameter. High carrying "
            "capacity with small self-loading ratio and good dynamic performance. Ultra-high speed pick-up "
            "capability with multiple cycles per second. ±0.1 mm repetition accuracy. Optional 130W vision "
            "positioning module. WSC-GJK2-T4 electrical control system. Suspension mounting."
        ),
        "payload_kg": 5.0,
        "reach_mm": 1000,
        "repeatability_mm": 0.1,
        "weight_kg": 67.0,
    },
    # ---- AE AE20 Cobot (page empty, use known specs) ----
    1453: {
        "description": (
            "AE AE20 Cobot is a 6-axis collaborative robot arm manufactured by AE Robotics Co., Ltd. in "
            "Shenzhen, China. Designed for flexible automation tasks including assembly, pick & place, and "
            "machine tending in manufacturing environments."
        ),
        "features": (
            "6-axis collaborative robot design for flexible manufacturing automation. Suitable for assembly, "
            "pick & place, and machine tending applications. Manufactured in Shenzhen, China with CE and "
            "CCC certification. Part of AE Robotics' industrial robot family."
        ),
    },
    # ---- AE AE-25 Palletizer (page empty, use known specs) ----
    1452: {
        "description": (
            "AE AE-25 is a 6-axis industrial robot arm in the AE-25 series, designed for palletizing "
            "applications. Manufactured by AE Robotics Co., Ltd. in Shenzhen, China with CE and CCC "
            "certification."
        ),
        "features": (
            "6-axis articulated design optimized for palletizing tasks. Part of AE Robotics' AE-25 series "
            "industrial robot family. Manufactured in Shenzhen, China with CE and CCC certification."
        ),
    },
    # ---- AUBO robots — features missing ----
    3529: {  # AUBO-I5FB Explosion Proof Cobot
        "features": (
            "5 kg payload explosion-proof collaborative robot for spray painting and flammable environments. "
            "6-axis design with EtherCAT communication. Working radius suitable for automotive painting "
            "applications. IP-rated for hazardous environment operation. CE certified."
        ),
    },
    3530: {  # AUBO 6-axis Cobot Welding Station
        "features": (
            "6-axis cobot-based welding station combining AUBO I5 collaborative robot with welding equipment. "
            "Supports MIG/MAG/CO2 welding for carbon steel and stainless steel. Manual drag-and-drop "
            "programming for easy deployment. Customizable solutions for various welding applications."
        ),
    },
    3532: {  # Fanuc R-2000iC/210F
        "features": (
            "210 kg payload 6-axis industrial robot with 2655 mm arm reach. High-speed, high-accuracy "
            "handling and welding robot. Fanuc iRVision compatible. Suitable for automotive and heavy "
            "manufacturing applications. CE certified."
        ),
    },
    3533: {  # JAKA Zu18 Cobot
        "features": (
            "18 kg payload 6-axis collaborative robot with EtherCAT communication. Similar capability to "
            "UR10 cobot. Drag-and-drop programming interface. Suitable for assembly, machine tending, and "
            "palletizing. CE certified."
        ),
    },
}


def resolve_country_id(client: ResearchApiClient, code: str) -> int | None:
    """Resolve country code to DB ID, with caching."""
    return client.get_country_id(code)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix AE Robotics (1375) data quality issues")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to production")
    parser.add_argument("--robot-ids", type=int, nargs="+", help="Only fix specific robot IDs")
    args = parser.parse_args()

    client = ResearchApiClient()

    # Resolve country IDs
    print("Resolving country IDs...")
    country_id_cache: dict[str, int | None] = {}
    for code in ["CN", "DK", "JP"]:
        cid = resolve_country_id(client, code)
        country_id_cache[code] = cid
        print(f"  {code} → id={cid}")

    # Fetch all robots
    print(f"\nFetching robots for company {COMPANY_ID}...")
    robots = client.list_robots_for_company(COMPANY_ID)
    print(f"Fetched {len(robots)} robots")

    if args.robot_ids:
        robots = [r for r in robots if r["id"] in args.robot_ids]
        print(f"Filtered to {len(robots)} robots by --robot-ids")

    fixed = skipped = failed = 0
    results_log = []

    for robot in robots:
        rid = robot["id"]
        name = robot.get("name", f"Robot {rid}")
        current_countries = robot.get("manufacturer_countries") or []
        current_desc = robot.get("description") or ""
        current_price_min = robot.get("price_min")
        current_features = robot.get("features") or ""

        # Determine correct country code
        country_code = RESELLER_COUNTRY.get(name, "CN")
        country_id = country_id_cache.get(country_code)

        patch: dict = {}

        # 1. Fix manufacturer_countries if missing
        if not current_countries and country_id:
            patch["manufacturer_countries"] = [country_id]

        # 2. Apply per-robot data patches (description, price, specs, features)
        robot_data = ROBOT_PATCHES.get(rid, {})
        for field, value in robot_data.items():
            # For description: always update if current is short (<100 chars) or if we have a better one
            if field == "description":
                if len(current_desc) < 100:
                    patch[field] = value
                # Also update if current description is just a placeholder/auto-generated
                elif current_desc.startswith("The ") and len(current_desc) < 200:
                    patch[field] = value
            # For features: only fill if missing
            elif field == "features":
                if not current_features:
                    patch[field] = value
            # For price: only fill if missing
            elif field in ("price_min", "price_max", "price_currency"):
                if not current_price_min:
                    patch[field] = value
            # For specs: only fill if currently null
            elif field in ("payload_kg", "reach_mm", "repeatability_mm", "weight_kg"):
                if robot.get(field) is None:
                    patch[field] = value
            else:
                patch[field] = value

        if not patch:
            print(f"[{rid}] {name} — nothing to fix, skipping")
            skipped += 1
            results_log.append({"id": rid, "name": name, "status": "skipped", "patch": {}})
            continue

        print(f"\n[{rid}] {name}")
        print(f"  country: {current_countries} → {patch.get('manufacturer_countries', '(unchanged)')}")
        if "description" in patch:
            print(f"  description: {len(current_desc)} chars → {len(patch['description'])} chars")
        if "price_min" in patch:
            print(f"  price_min: {current_price_min} → {patch['price_min']} {patch.get('price_currency', '')}")
        for spec in ("payload_kg", "reach_mm", "repeatability_mm", "weight_kg"):
            if spec in patch:
                print(f"  {spec}: {robot.get(spec)} → {patch[spec]}")
        if "features" in patch:
            print(f"  features: (was empty) → {len(patch['features'])} chars")

        if args.dry_run:
            print("  [DRY RUN] Would apply patch")
            fixed += 1
            results_log.append({"id": rid, "name": name, "status": "would_fix", "patch": patch})
            continue

        try:
            client._patch(f"robots/robots/{rid}/", patch)
            print(f"  ✓ Patched successfully")
            fixed += 1
            results_log.append({"id": rid, "name": name, "status": "fixed", "patch": patch})
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1
            results_log.append({"id": rid, "name": name, "status": "failed", "error": str(exc), "patch": patch})

        time.sleep(0.2)

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Summary:")
    print(f"  Fixed:   {fixed}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed:  {failed}")
    print(f"  Total:   {len(robots)}")

    report_path = REPORT_DIR / "fix-ae-robotics-1375.json"
    report_path.write_text(
        json.dumps({"summary": {"fixed": fixed, "skipped": skipped, "failed": failed}, "robots": results_log},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
