"""Trossen (307) soft patch — family + US country + typed Interbotix specs.

CONTEXT (2026-07-20):
  Prior fix_trossen_robots.py left must-clear passing but empty family_*,
  empty manufacturer_countries on 8/9, and payload/reach not persisted.
  PATCH now accepts payload_kg / reach_mm (verified on PincherX 5269).

OEM docs (Interbotix X-Series):
  PX100: 4 DoF / 50 g / 300 mm
  VX300S: 6 DoF / 750 g / 750 mm
  WX250S: 6 DoF / 250 g / 650 mm
  WidowX AI: ~4 kg arm mass (OEM PDP); leave payload blank if not cited

Skip published ALOHA Mobile V2.0 (5265).

Usage:
  python _trossen_soft_patch.py
  python _trossen_soft_patch.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 307
US_ID = 20
AVAILABLE = 11
REPORT = _RESEARCH / "staging" / "reports" / "trossen-soft-patch.json"

# family_url hubs
ALOHA_URL = "https://www.trossenrobotics.com/aloha-stationary"
PX_URL = "https://www.trossenrobotics.com/pincherx100"
VX_URL = "https://www.trossenrobotics.com/viperx-300"
WX_URL = "https://www.trossenrobotics.com/widowx-250"
WXAI_URL = "https://www.trossenrobotics.com/widowx-ai"

PATCHES: list[dict[str, Any]] = [
    {
        "id": 5266,
        "name": "ALOHA Solo",
        "model_name": "ALOHA Solo",
        "variant_code": "Solo",
        "variant_label": "Solo",
        "family_key": "trossen:aloha",
        "family_name": "ALOHA",
        "family_url": ALOHA_URL,
        "product_url_scope": "exact_variant",
        "url": "https://www.trossenrobotics.com/aloha-solo",
        "release_year": 2024,
        "purpose": "Portable teleoperation data collection for robot learning",
        # kit — no single-arm payload typed
    },
    {
        "id": 5267,
        "name": "ALOHA Stationary V2.0",
        "model_name": "ALOHA Stationary V2.0",
        "variant_code": "Stationary-V2",
        "variant_label": "Stationary V2.0",
        "family_key": "trossen:aloha",
        "family_name": "ALOHA",
        "family_url": ALOHA_URL,
        "product_url_scope": "exact_variant",
        "url": "https://www.trossenrobotics.com/aloha-stationary",
        "release_year": 2024,
        "purpose": "Bimanual teleoperation data collection for robot learning",
    },
    {
        "id": 5268,
        "name": "Mobile AI",
        "model_name": "Mobile AI",
        "variant_code": "Mobile-AI",
        "variant_label": "Mobile AI",
        "family_key": "trossen:aloha",
        "family_name": "ALOHA",
        "family_url": "https://www.trossenrobotics.com/mobile-ai",
        "product_url_scope": "exact_variant",
        "url": "https://www.trossenrobotics.com/mobile-ai",
        "purpose": "Mobile bimanual data collection for robot learning",
    },
    {
        "id": 5269,
        "name": "PincherX 100",
        "model_name": "PincherX 100",
        "variant_code": "PX100",
        "variant_label": "100",
        "family_key": "trossen:pincherx",
        "family_name": "PincherX",
        "family_url": PX_URL,
        "product_url_scope": "exact_variant",
        "url": PX_URL,
        "dof": 4,
        "payload_kg": 0.05,
        "reach_mm": 300,
        "purpose": "Compact research and education arm manipulation",
        "features": (
            "Interbotix PincherX-100 (OEM docs.trossenrobotics.com X-Series specs): "
            "4 DoF, working payload 50 g, reach 300 mm, total span 600 mm, "
            "repeatability 5 mm; DYNAMIXEL XL430-W250 servos; U2D2 / ROS access; "
            "education and first-arm research platform. Soft: no public MSRP typed."
        ),
    },
    {
        "id": 5270,
        "name": "ViperX 300 S",
        "model_name": "ViperX 300 S",
        "variant_code": "VX300S",
        "variant_label": "300 S",
        "family_key": "trossen:viperx",
        "family_name": "ViperX",
        "family_url": VX_URL,
        "product_url_scope": "exact_variant",
        "url": VX_URL,
        "dof": 6,
        "payload_kg": 0.75,
        "reach_mm": 750,
        "purpose": "6-DoF research manipulation and teleoperation",
        "features": (
            "Interbotix ViperX-300 6DOF / ViperX 300 S (OEM docs vx300s specs): "
            "6 DoF, working payload 750 g, reach 750 mm, total span 1500 mm, "
            "repeatability 1 mm; DYNAMIXEL XM540/XM430; stationary or mobile mounts. "
            "Soft: no public MSRP typed."
        ),
    },
    {
        "id": 5271,
        "name": "ViperX Aloha Follower Arm V2.0",
        "model_name": "ViperX Aloha Follower V2.0",
        "variant_code": "VX-ALOHA-F",
        "variant_label": "ALOHA Follower V2.0",
        "family_key": "trossen:aloha",
        "family_name": "ALOHA",
        "family_url": ALOHA_URL,
        "product_url_scope": "exact_variant",
        "url": "https://www.trossenrobotics.com/viperx-aloha",
        "dof": 6,
        "payload_kg": 0.75,
        "reach_mm": 750,
        "purpose": "ALOHA follower arm for bimanual teleoperation kits",
        "features": (
            "ALOHA-tuned ViperX follower (OEM viperx-aloha + Interbotix VX300S class): "
            "6 DoF, ~750 g payload, ~750 mm reach / ~1500 mm span class, ~1 mm "
            "repeatability. Upgraded grippers/haptics/joints for Stationary kits. "
            "Soft: kit-level price on OEM; no separate follower MSRP typed."
        ),
    },
    {
        "id": 5272,
        "name": "WidowX 250 S",
        "model_name": "WidowX 250 S",
        "variant_code": "WX250S",
        "variant_label": "250 S",
        "family_key": "trossen:widowx",
        "family_name": "WidowX",
        "family_url": WX_URL,
        "product_url_scope": "exact_variant",
        "url": WX_URL,
        "dof": 6,
        "payload_kg": 0.25,
        "reach_mm": 650,
        "purpose": "6-DoF research manipulation and teleoperation",
        "features": (
            "Interbotix WidowX-250 6DOF / WidowX 250 S (OEM docs wx250s specs): "
            "6 DoF, working payload 250 g, reach 650 mm, total span 1300 mm, "
            "repeatability 1 mm; ROS 2 support; custom 3D-printed end-effectors. "
            "Soft: no public MSRP typed."
        ),
    },
    {
        "id": 5273,
        "name": "WidowX AI",
        "model_name": "WidowX AI",
        "variant_code": "WX-AI",
        "variant_label": "AI",
        "family_key": "trossen:widowx",
        "family_name": "WidowX",
        "family_url": WXAI_URL,
        "product_url_scope": "family",
        "url": WXAI_URL,
        "dof": 6,
        "weight_kg": 4.0,
        "release_year": 2025,
        "purpose": "ML research arm for leader/follower learning kits",
        "features": (
            "WidowX AI 6-DoF manipulator (OEM trossenrobotics.com/widowx-ai): Base / "
            "Leader / Follower SKUs for Mobile AI and ALOHA pipelines; precision grip "
            "with molded silicone pads; OEM cites ~4 kg arm mass class. Soft: no public "
            "typed payload/reach on PDP (left blank); shared AI-ready arm still when "
            "PDP lacks a distinct full-arm hero."
        ),
    },
    {
        "id": 5274,
        "name": "WidowX Aloha Set",
        "model_name": "WidowX Aloha Set",
        "variant_code": "WX-ALOHA-SET",
        "variant_label": "ALOHA Set",
        "family_key": "trossen:aloha",
        "family_name": "ALOHA",
        "family_url": ALOHA_URL,
        "product_url_scope": "exact_variant",
        "url": "https://www.trossenrobotics.com/widowx-aloha-set",
        "dof": 6,
        "payload_kg": 0.25,
        "reach_mm": 650,
        "release_year": 2024,
        "purpose": "Matched WidowX leader pair for ALOHA teleoperation kits",
        "features": (
            "Matched WidowX ALOHA leader-arm set (OEM widowx-aloha-set + WX250S class): "
            "6 DoF, ~250 g payload, ~650 mm reach / ~1300 mm span class; upgraded "
            "grippers/haptics/joints; gravity-compensation compatible. Soft: kit uses "
            "Stationary-context hero where SKU-only still is chrome."
        ),
    },
]


def build_body(spec: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": AVAILABLE,
        "name": spec["name"],
        "model_name": spec["model_name"],
        "variant_code": spec["variant_code"],
        "variant_label": spec["variant_label"],
        "family_key": spec["family_key"],
        "family_name": spec["family_name"],
        "family_url": spec["family_url"],
        "product_url_scope": spec["product_url_scope"],
        "url": spec["url"],
        "purpose": spec["purpose"],
        "source_locale": "en",
        "notes": (
            f"[AI Research] Trossen soft patch 2026-07-20. US; Available; "
            f"family {spec['family_key']}; typed specs from Interbotix docs / OEM PDP."
        ),
    }
    for k in ("dof", "payload_kg", "reach_mm", "weight_kg", "release_year", "features"):
        if spec.get(k) is not None:
            body[k] = spec[k]
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    plan = {
        "company_id": COMPANY_ID,
        "apply": bool(args.apply),
        "patches": [
            {
                "id": s["id"],
                "family_key": s["family_key"],
                "payload_kg": s.get("payload_kg"),
                "reach_mm": s.get("reach_mm"),
                "dof": s.get("dof"),
                "weight_kg": s.get("weight_kg"),
                "release_year": s.get("release_year"),
            }
            for s in PATCHES
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    if not args.apply:
        REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        print(f"Dry-run -> {REPORT}")
        for s in PATCHES:
            print(
                f"  {s['id']} {s['name']}: fam={s['family_key']} "
                f"p={s.get('payload_kg')} r={s.get('reach_mm')} dof={s.get('dof')}"
            )
        return 0

    client = ResearchApiClient()
    results = []
    for spec in PATCHES:
        rid = spec["id"]
        body = build_body(spec)
        try:
            client._patch(f"robots/robots/{rid}/", body)
            # re-PATCH soft typed columns (import wipe pattern)
            soft = {
                "availability_status": AVAILABLE,
                "family_key": spec["family_key"],
                "family_name": spec["family_name"],
                "family_url": spec["family_url"],
                "manufacturer_countries": [US_ID],
                "manufacturer_country_ref": US_ID,
            }
            for k in ("dof", "payload_kg", "reach_mm", "weight_kg", "release_year"):
                if spec.get(k) is not None:
                    soft[k] = spec[k]
            client._patch(f"robots/robots/{rid}/", soft)
            print(f"OK {rid} {spec['name']}")
            results.append({"id": rid, "ok": True})
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {rid}: {e}")
            results.append({"id": rid, "ok": False, "error": str(e)})

    plan["results"] = results
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Report -> {REPORT}")
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
