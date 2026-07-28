"""Soft enrich Boston Dynamics (18) — Stretch, Atlas, Spot with Arm.

Must-clear already passes; this pass sets US country, family metadata,
Available, OEM-cited typed specs, and fixes Spot with Arm purpose fluff.

Usage:
  python discover_boston_dynamics_robots.py
  python discover_boston_dynamics_robots.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 18
US_ID = 20
AVAILABLE = 11

PATCHES: list[dict[str, Any]] = [
    {
        "id": 1760,
        "name": "Stretch",
        "family_key": "boston-dynamics:stretch",
        "family_name": "Stretch",
        "family_url": "https://bostondynamics.com/products/stretch/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "payload_kg": 22.68,
        "speed": 7.0,
        "purpose": "Automated trailer unloading and warehouse case handling",
        "features_append_note": (
            "OEM bostondynamics.com/products/stretch/: mobile case-handling platform "
            "handles packages up to 50 lb (≈22.7 kg); hundreds of cases/hour; "
            "fast deploy without heavy infrastructure; continuous multi-shift battery. "
            "Soft: no public OEM robot weight table."
        ),
        "sources": [
            {
                "url": "https://bostondynamics.com/products/stretch/",
                "title": "Boston Dynamics Stretch product page",
            }
        ],
    },
    {
        "id": 1761,
        "name": "Atlas (Boston Dynamics)",
        "family_key": "boston-dynamics:atlas",
        "family_name": "Atlas",
        "family_url": "https://bostondynamics.com/products/atlas/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "height_mm": 1900.0,
        "speed": 9.0,
        "purpose": "Industrial humanoid for demanding material handling tasks",
        "features_append_note": (
            "OEM bostondynamics.com/products/atlas/: next-gen electric humanoid for "
            "demanding industrial tasks in human-centric environments. Soft: Boston "
            "Dynamics does not publish a full public typed spec sheet for Atlas on "
            "the marketing PDP — height/speed retained from prior research pass."
        ),
        "sources": [
            {
                "url": "https://bostondynamics.com/products/atlas/",
                "title": "Boston Dynamics Atlas product page",
            }
        ],
    },
    {
        "id": 1833,
        "name": "Spot with Arm",
        "family_key": "boston-dynamics:spot",
        "family_name": "Spot",
        "family_url": "https://bostondynamics.com/products/spot/",
        "product_url_scope": "family",
        "variant_label": "with Arm",
        "availability_status": AVAILABLE,
        "weight_kg": 33.8,
        "payload_kg": 14.0,
        "height_mm": 700.0,
        "length_mm": 1100.0,
        "width_mm": 500.0,
        "speed": 5.76,
        "purpose": "Mobile inspection and manipulation with Spot Arm payload",
        "features": (
            "OEM bostondynamics.com/products/spot/ specifications (base robot + "
            "battery): 33.8 kg net weight; 14 kg payload capacity on flexible payload "
            "platform; Spot Arm enables grasp/manipulation. Dimensions walking: "
            "length ~1100 mm, width 500 mm, max height 700 mm; max speed 1.6 m/s "
            "(5.76 km/h); ±30° slope; IP54; Wi-Fi + Ethernet. 360° perception, "
            "autonomous charging, self-righting. 5-photo gallery includes arm config."
        ),
        "sources": [
            {
                "url": "https://bostondynamics.com/products/spot/",
                "title": "Boston Dynamics Spot specifications",
            },
            {
                "url": "https://bostondynamics.com/products/spot/arm/",
                "title": "Boston Dynamics Spot Arm",
            },
        ],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    client = ResearchApiClient()
    report: list[dict[str, Any]] = []

    for spec in PATCHES:
        rid = spec["id"]
        current = client._get(f"robots/robots/{rid}/")
        body: dict[str, Any] = {
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": spec.get("availability_status", AVAILABLE),
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec.get("product_url_scope", "exact_variant"),
            "purpose": spec.get("purpose") or current.get("purpose"),
        }
        if spec.get("variant_label"):
            body["variant_label"] = spec["variant_label"]
        for k in (
            "payload_kg",
            "weight_kg",
            "height_mm",
            "length_mm",
            "width_mm",
            "speed",
        ):
            if spec.get(k) is not None:
                body[k] = spec[k]
        if spec.get("features"):
            body["features"] = spec["features"]
        elif spec.get("features_append_note"):
            old = (current.get("features") or "").strip()
            note = spec["features_append_note"]
            if note not in old:
                body["features"] = f"{old}\n\n{note}".strip() if old else note

        entry = {"id": rid, "name": spec["name"], "patch": body, "dry_run": not args.apply}
        if args.apply:
            client._patch(f"robots/robots/{rid}/", body)
            after = client._get(f"robots/robots/{rid}/")
            entry["after"] = {
                "country": after.get("manufacturer_countries"),
                "family_key": after.get("family_key"),
                "availability": after.get("availability_status"),
                "payload_kg": after.get("payload_kg"),
                "weight_kg": after.get("weight_kg"),
                "height_mm": after.get("height_mm"),
                "speed": after.get("speed"),
                "purpose": after.get("purpose"),
            }
            print(f"patched {rid} {spec['name']}")
        else:
            print(f"dry-run {rid} {spec['name']}: {list(body.keys())}")
        report.append(entry)

    out = _RESEARCH_DIR / "staging" / "reports" / "boston-dynamics-discover.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
