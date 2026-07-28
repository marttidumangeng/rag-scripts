"""Summarize Realman variant gaps (curated, not chrome-noise)."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "staging" / "reports" / "realman-variant-gap-curated.json"

# DB facts (2026-07-19, all published)
HAVE = {
    "RM65 Standard",
    "RM65 Six-Axis Force",
    "RM65",
    "RM75 Standard",
    "RM75 Six-Axis Force",
    "RM75",
    "RML63 Standard",
    "RML63 Six-Axis Force",
    "RML63",
    "ECO65 Standard",
    "ECO65 Six-Axis Force",
    "ECO65",
    "ECO62 Standard",
    "ECO62",
    "ECO63",
    "RX75 Standard",
    "RX75 Vision",
    "RX75",
    "RX71",
    "RealBot-01",
    "RealBot-L2",
    "RealBot-S2",
    "Dual-Arm Lift",
    "Single-Arm Lift",
    "Four-Steer Four-Drive Chassis",
    "Two-Wheel Differential Chassis",
}

# OEM EN PDPs advertise Standard + Six-Axis Force (RX75 also Vision).
# Curated from live page titles + option text (not nav chrome alone).
OEM_ARM_VARIANTS = {
    "RM65": ["Standard", "Six-Axis Force"],
    "RM75": ["Standard", "Six-Axis Force"],
    "RML63": ["Standard", "Six-Axis Force"],
    "ECO65": ["Standard", "Six-Axis Force"],
    "ECO62": ["Standard", "Six-Axis Force"],
    "ECO63": ["Standard", "Six-Axis Force"],
    "RX71": ["Standard", "Six-Axis Force"],
    "RX75": ["Standard", "Six-Axis Force", "Vision"],
}

report = {
    "company_id": 882,
    "status": "all 26 published",
    "missing_named_variants": [],
    "near_duplicate_base_rows": [],
    "out_of_scope_oem_pages": [
        {
            "page": "https://www.realman-robotics.com/en/products/rmg24-gripper.html",
            "why": "End-effector accessory, not a robot platform",
        },
        {
            "page": "https://www.realman-robotics.com/en/products/teleop-kit.html",
            "why": "Teleoperation kit accessory",
        },
        {
            "page": "https://www.realman-robotics.com/en/products/whg-joint-modules.html",
            "why": "Joint module component series",
        },
        {
            "page": "https://www.realman-robotics.com/en/products/whj-joint-modules.html",
            "why": "Joint module component series",
        },
        {
            "page": "https://www.realman-robotics.com/en/products/whj-torque-joint-modules.html",
            "why": "Joint module component series",
        },
    ],
    "url_fixes": [
        {
            "id": 5224,
            "name": "RealBot-01",
            "note": "realbot-01.html 404; live page is realbot-humanoid.html (title RealBot-01)",
            "suggested_url": "https://www.realman-robotics.com/en/products/realbot-humanoid.html",
        }
    ],
    "optional_review": [
        {
            "name": "Dual-Arm Lift Vision",
            "page": "https://www.realman-robotics.com/en/products/dual-arm-lift.html",
            "note": "Page text mentions Vision; unclear if sold as separate SKU — spot-check before inventing a row",
        }
    ],
}

for fam, variants in OEM_ARM_VARIANTS.items():
    for v in variants:
        name = f"{fam} {v}"
        if name not in HAVE:
            # If only bare family exists, still flag missing named variant
            report["missing_named_variants"].append(
                {
                    "name": name,
                    "family": fam,
                    "have_family_rows": sorted(x for x in HAVE if x == fam or x.startswith(fam + " ")),
                    "oem_page": f"https://www.realman-robotics.com/en/products/{fam.lower()}.html",
                }
            )

for fam in ("RM65", "RM75", "RML63", "ECO65", "ECO62", "RX75"):
    base = fam
    std = f"{fam} Standard"
    if base in HAVE and std in HAVE:
        report["near_duplicate_base_rows"].append(
            {
                "keep": std,
                "consider_reject_merge": base,
                "reason": "Bare family name duplicates Standard variant row",
            }
        )

OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("missing_named_variants:")
for m in report["missing_named_variants"]:
    print(" ", m["name"], "| have:", ", ".join(m["have_family_rows"]))
print("\nnear_duplicate_base_rows:")
for d in report["near_duplicate_base_rows"]:
    print(f"  keep {d['keep']} / reject-or-merge {d['consider_reject_merge']}")
print("wrote", OUT)
