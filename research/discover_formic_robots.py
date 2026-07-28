"""Curated Formic Technologies (1450) enrich — all pending Automate NOW solutions.

US company (Chicago / Oakland); country was null. OEM website https://www.formic.co/
(formic.com redirects / not used). Solution pages are RaaS offerings (not single
SKU PDPs with curb-weight tables). Shared site og:image formic-og.jpg is NOT a
per-model hero. Distinct solution images were restored in the follow-up
`fix_briggo_formic_images.py` pass.

Pending robots (8):
  5168 Humanoids & Bimanual Mobile — Announced / early access
  5167 Machine Tending
  5166 Automate NOW Industrial Palletizers
  2874 AMRs for Pallet Handling
  2872 Automated Pallet Wrapping
  2870 Flexible Case Packer
  2868 Top Load Case Packer
  2867 Automate NOW Essential (Cobot) Palletizers

Usage:
  python discover_formic_robots.py
  python discover_formic_robots.py --apply
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

COMPANY_ID = 1450
COMPANY_SLUG = "formic-technologies"
COMPANY_NAME = "Formic Technologies"
US_ID = 20
AVAILABLE = 11
ANNOUNCED = 10
HOME = "https://www.formic.co/"

IMAGE_NOTE = (
    "[AI Research] Hero restored 2026-07-21 from the current model-specific "
    "formic.co solution-page asset; copied to owned CDN and HTTP verified."
)

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 5168,
        "name": "Formic Humanoids & Bimanual Mobile Platforms",
        "model_name": "Humanoids & Bimanual Mobile",
        "variant_code": "humanoids",
        "variant_label": "General-purpose RaaS",
        "url": "https://www.formic.co/solutions/humanoids",
        "family_key": "formic:humanoids",
        "family_name": "Humanoids & Bimanual Mobile",
        "family_url": "https://www.formic.co/solutions/humanoids",
        "product_url_scope": "family",
        "availability_status": ANNOUNCED,
        "purpose": (
            "General-purpose bimanual mobile manipulation\n"
            "Pilot humanoid and multi-step assist tasks on the factory floor"
        ),
        "description": (
            "Formic deploys humanoid and bimanual mobile platforms for "
            "manufacturers under Full Service Automation — fixed monthly price, "
            "no CapEx, with pilots scoped to one task/cell/shift before scale-out."
        ),
        "features": (
            "OEM formic.co/solutions/humanoids: generalist robots as a service; "
            "bimanual mobile robots for bin picking, machine tending, kitting, "
            "and assist work; SLAM navigation without fixed track; task-level "
            "instruction via demonstration; pilots designed/run by Formic "
            "engineers; continuous OTA upgrades; 24/7 monitoring and teleop "
            "intervention; early-access / 2026–2027 humanoid pilot window. Soft: "
            "no public curb weight, DoF, or speed table on solution page."
        ),
        "payload_kg": None,
        "use_keys": "material-handling|machine-tending|picking",
        "industry_keys": "manufacturing|industrial",
        "movement": "wheeled",
        "tags": ["Formic", "Humanoid", "Bimanual", "RaaS", "USA"],
    },
    {
        "id": 5167,
        "name": "Formic Robotic Machine Tending for CNC, Mill & Lathe",
        "model_name": "Machine Tending",
        "variant_code": "machine-tending",
        "variant_label": "CNC / mill / lathe",
        "url": "https://www.formic.co/solutions/machine-tending",
        "family_key": "formic:machine-tending",
        "family_name": "Machine Tending",
        "family_url": "https://www.formic.co/solutions/machine-tending",
        "product_url_scope": "family",
        "availability_status": AVAILABLE,
        "purpose": (
            "Robotic CNC mill and lathe load/unload\n"
            "Lights-out machine tending for metal fab and molding"
        ),
        "description": (
            "Formic's machine-tending cells automate part load/unload for CNC "
            "mills, lathes, EDM, and injection molds under a Full Service monthly "
            "model, recovering spindle time lost to manual cycles."
        ),
        "features": (
            "OEM formic.co/solutions/machine-tending: vision-guided bin/fixture "
            "pick; multi-machine tending (one robot, two–three spindles); "
            "compatible with Fanuc/Mazak/Haas/DMG Mori/Okuma and most CNC/lathe "
            "platforms; reach 1.3–2.6 m (range — not typed); payloads 5–150 kg "
            "EOAT-dependent (range — not typed); M-code / Modbus / EtherNet/IP / "
            "OPC UA integration; scanners, fenced or collaborative safety. Soft: "
            "part weight application-scoped; no single curb-weight SKU."
        ),
        "payload_kg": None,
        "reach_mm": None,
        "use_keys": "machine-tending|material-handling",
        "industry_keys": "manufacturing|industrial|metal",
        "movement": "stationary",
        "tags": ["Formic", "Machine Tending", "CNC", "RaaS", "USA"],
    },
    {
        "id": 5166,
        "name": "Automate NOW Industrial Palletizers",
        "model_name": "Industrial Palletizers",
        "variant_code": "industrial-palletizers",
        "variant_label": "Industrial",
        "url": "https://www.formic.co/solutions/palletizing#industrial-palletizers",
        "family_key": "formic:palletizing",
        "family_name": "Automate NOW Palletizers",
        "family_url": "https://www.formic.co/solutions/palletizing",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "purpose": (
            "Multi-shift industrial case palletizing\n"
            "High-volume end-of-line pallet stacking"
        ),
        "description": (
            "Formic Automate NOW Industrial Palletizers are full-service robotic "
            "palletizing cells for multi-shift CPG lines — heavier cases, taller "
            "stacks, ANSI/RIA-compliant fencing and scanners, no CapEx."
        ),
        "features": (
            "OEM formic.co/solutions/palletizing (Industrial): continuous "
            "multi-shift throughput; heavier cases and taller stacks; four "
            "industrial unit options engineered to the line; full safety fencing "
            "+ area scanners, ANSI/RIA compliant; swap equipment mid-contract at "
            "same flat rate. Soft: prior DB claims (40 lb / 10 cases/min / 95 in) "
            "not re-verified as a public typed table on the live page this "
            "session — left untyped rather than re-asserting."
        ),
        "payload_kg": None,
        "use_keys": "palletizing|packaging|material-handling",
        "industry_keys": "food-beverage|manufacturing|industrial",
        "movement": "stationary",
        "tags": ["Formic", "Palletizer", "Industrial", "RaaS", "USA"],
    },
    {
        "id": 2874,
        "name": "Formic Autonomous Mobile Robots (AMRs) for Pallet Handling",
        "model_name": "AMR Pallet Handling",
        "variant_code": "amrs",
        "variant_label": "Pallet / tote AMR fleet",
        "url": "https://www.formic.co/solutions/amrs",
        "family_key": "formic:amr",
        "family_name": "AMRs for Pallet Handling",
        "family_url": "https://www.formic.co/solutions/amrs",
        "product_url_scope": "family",
        "availability_status": AVAILABLE,
        "purpose": (
            "Autonomous pallet and tote transport on the plant floor\n"
            "Dock-to-staging and line-side replenishment without forklifts"
        ),
        "description": (
            "Formic AMR fleets move pallets and totes between dock, staging, line, "
            "and outbound under Full Service Automation, reducing forklift injury "
            "and product damage while sharing floors with people and trucks."
        ),
        "features": (
            "OEM formic.co/solutions/amrs: SLAM navigation (no tape/wires); "
            "fleets from 2 to 30+ units; payload up to 1,500 kg per unit (typed); "
            "GMA 48×40\" pallet compatibility; opportunity charging; WMS/ERP/MES "
            "integration (SAP, Oracle, Manhattan Associates cited); ANSI/RIA "
            "R15.08 mobile-robot compliant; slows/stops around humans. Soft: no "
            "single curb weight or max speed published on page."
        ),
        "payload_kg": 1500.0,
        "use_keys": "material-handling|logistics|transport",
        "industry_keys": "manufacturing|logistics|food-beverage",
        "movement": "wheeled",
        "tags": ["Formic", "AMR", "Pallet", "RaaS", "USA"],
    },
    {
        "id": 2872,
        "name": "Formic Automated Pallet Wrapping",
        "model_name": "Pallet Wrapping",
        "variant_code": "pallet-wrapping",
        "variant_label": "Stretch-wrap cell",
        "url": "https://www.formic.co/solutions/pallet-wrapping",
        "family_key": "formic:pallet-wrapping",
        "family_name": "Automated Pallet Wrapping",
        "family_url": "https://www.formic.co/solutions/pallet-wrapping",
        "product_url_scope": "family",
        "availability_status": AVAILABLE,
        "purpose": (
            "Automated stretch wrapping of finished pallets\n"
            "Inline wrap, label, and stage from palletizer to dock"
        ),
        "description": (
            "Formic stretch-wrap cells wrap, label, and stage finished pallets "
            "downstream of the palletizer so loads arrive at the dock "
            "shipping-ready without operator walks."
        ),
        "features": (
            "OEM formic.co/solutions/pallet-wrapping: programmable wrap profile "
            "by SKU; film pre-stretch 60–250%, 1–6 layers; pallet sizes 36×36\" to "
            "48×48\"; stack height up to 96\" (2438 mm typed as height envelope); "
            "throughput up to 60 pallets/hour (profile-dependent — not robot "
            "speed km/h); inline print-and-apply BOL labeling option; rotary "
            "turntable / arm / robotic mobile wrapper configs; light curtains + "
            "area scanners, ANSI/RIA R15.06. Soft: no curb weight on page."
        ),
        "payload_kg": None,
        "height_mm": 2438,  # stack height up to 96"
        "use_keys": "packaging|palletizing|material-handling",
        "industry_keys": "manufacturing|food-beverage|logistics",
        "movement": "stationary",
        "tags": ["Formic", "Pallet Wrapping", "Stretch Wrap", "RaaS", "USA"],
    },
    {
        "id": 2870,
        "name": "Formic Flexible Case Packer",
        "model_name": "Flexible Case Packer",
        "variant_code": "flexible-case-packer",
        "variant_label": "Flexible",
        "url": "https://www.formic.co/formic-case-packing#flexible-case-packer",
        "family_key": "formic:case-packing",
        "family_name": "Case Packing",
        "family_url": "https://www.formic.co/formic-case-packing",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "purpose": (
            "Vision-guided case packing for high-mix SKUs\n"
            "Fast changeover packing on seasonal and short-run lines"
        ),
        "description": (
            "Formic's Flexible Case Packer is a pre-configured vision-guided "
            "packer that reconfigures across variable case counts, mixed SKUs, "
            "and frequent changeovers without re-engineering the cell."
        ),
        "features": (
            "OEM formic.co/formic-case-packing#flexible-case-packer: reconfigures "
            "fast for new SKUs, counts, and case patterns; vision-guided "
            "pick-and-place across mixed formats; built for high-mix, seasonal, "
            "and short-run lines; Full Service monthly fee includes design, "
            "robots, install, and 24/7 support. Soft: no public unit-weight or "
            "footprint table distinct from Top Load sibling."
        ),
        "payload_kg": None,
        "use_keys": "packaging|picking|material-handling",
        "industry_keys": "food-beverage|manufacturing",
        "movement": "stationary",
        "tags": ["Formic", "Case Packer", "Flexible", "RaaS", "USA"],
    },
    {
        "id": 2868,
        "name": "Formic Top Load Case Packer",
        "model_name": "Top Load Case Packer",
        "variant_code": "top-load-case-packer",
        "variant_label": "Top Load",
        "url": "https://www.formic.co/formic-case-packing",
        "family_key": "formic:case-packing",
        "family_name": "Case Packing",
        "family_url": "https://www.formic.co/formic-case-packing",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "purpose": (
            "Top-load case packing of rigid primary packages\n"
            "High-rate jar, can, bottle, and carton packing into cases"
        ),
        "description": (
            "Formic's Top Load Case Packer packs rigid primary packaging into "
            "cases or trays — jars, cartons, cans, bottles, and similar formats — "
            "in a compact cell under Full Service Automation."
        ),
        "features": (
            "OEM formic.co/formic-case-packing (Top Load): packs jars, cartons, "
            "canisters, cans, cups, bottles, tubs, bowls, clamshells & more; unit "
            "weights up to 20 lb (9.07 kg typed as payload_kg); pack rates up to "
            "100 units/min (cycle rate — not robot speed km/h); compact footprint "
            "8'×8'×7' (2438×2438×2134 mm typed). Soft: MSRP not published (RaaS)."
        ),
        "payload_kg": 9.07,
        "length_mm": 2438,
        "width_mm": 2438,
        "height_mm": 2134,
        "use_keys": "packaging|picking|material-handling",
        "industry_keys": "food-beverage|manufacturing",
        "movement": "stationary",
        "tags": ["Formic", "Case Packer", "Top Load", "RaaS", "USA"],
    },
    {
        "id": 2867,
        "name": "Automate NOW Essential Palletizers (Cobot Palletizer)",
        "model_name": "Essential Cobot Palletizer",
        "variant_code": "cobot-palletizers",
        "variant_label": "Cobot / Essential",
        "url": "https://www.formic.co/solutions/palletizing",
        "family_key": "formic:palletizing",
        "family_name": "Automate NOW Palletizers",
        "family_url": "https://www.formic.co/solutions/palletizing",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "purpose": (
            "Compact cobot case palletizing for single-shift lines\n"
            "Small-footprint end-of-line stacking for lighter cases"
        ),
        "description": (
            "Formic Automate NOW Essential cobot palletizers fit tight floors for "
            "food, beverage, and CPG single-shift lines with lighter cases — "
            "Full Service monthly pricing with mid-contract equipment swaps."
        ),
        "features": (
            "OEM formic.co/solutions/palletizing (Cobot): small footprint for "
            "tight floors; food/beverage/CPG single-shift lines; lighter cases "
            "and moderate rates; six Automate NOW system options with flat "
            "monthly rate and mid-contract swaps; 24/7 support and 100% "
            "maintenance included. Soft: prior DB 35 lb / 6 cases/min / 70 in "
            "stack claims not re-cited as a live public typed table this "
            "session — left untyped."
        ),
        "payload_kg": None,
        "use_keys": "palletizing|packaging|material-handling",
        "industry_keys": "food-beverage|manufacturing",
        "movement": "stationary",
        "tags": ["Formic", "Palletizer", "Cobot", "RaaS", "USA"],
    },
]


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {"uses": {}, "industries": {}, "movement": {}}
    for group, path in (
        ("uses", "robots/uses/"),
        ("industries", "robots/industries/"),
        ("movement", "robots/movement-types/"),
    ):
        try:
            rows = client._get(path) or []
            if isinstance(rows, dict):
                rows = rows.get("results") or rows.get("data") or []
            for row in rows:
                key = (row.get("key") or row.get("slug") or "").lower()
                if key and row.get("id"):
                    out[group][key] = int(row["id"])
        except Exception as e:  # noqa: BLE001
            print("tax warn", group, e)
    return out


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"formic-en-force-{rid}-20260720-{loc}",
                "translated_fields": {
                    "description": row.get("description") or "",
                    "features": row.get("features") or "",
                    "purpose": row.get("purpose") or "",
                    "name": row.get("name") or "",
                },
            }
            for loc in ("zh-CN", "zh-TW")
        ]
    }
    try:
        client._post("robots/translations/sync/", sync)
    except Exception as e:  # noqa: BLE001
        print(f"  en-force warn {rid}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    def map_keys(group: str, keys: str) -> list[int]:
        out = []
        for k in (keys or "").split("|"):
            k = k.strip().lower()
            if not k:
                continue
            kid = tax[group].get(k)
            if kid:
                out.append(kid)
            else:
                print(f"  warn missing {group} key={k}")
        return out

    if args.apply:
        try:
            client._patch(
                f"companies/{COMPANY_ID}/",
                {
                    "website": HOME,
                    "country_id": US_ID,
                    "manufacturer_countries": [US_ID],
                },
            )
            print("company patched", HOME, "US")
        except Exception as e:  # noqa: BLE001
            try:
                client._patch(f"companies/{COMPANY_ID}/", {"website": HOME})
                print("company website only", e)
            except Exception as e2:  # noqa: BLE001
                print("company patch warn", e, e2)

    plan: list[dict[str, Any]] = []
    for spec in PRODUCTS:
        notes = (
            f"[AI Research] Formic enrich 2026-07-20: US; website formic.co; "
            f"family {spec['family_key']}; avail={spec['availability_status']}.\n"
            + IMAGE_NOTE
        )
        row = {
            "id": spec["id"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "url": spec["url"],
            "family_key": spec["family_key"],
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "notes": notes,
        }
        slug = spec["variant_code"]
        path = staging / f"{slug}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name)
        plan.append({"id": spec["id"], "url": spec["url"], "family": spec["family_key"]})

        if not args.apply:
            continue

        body: dict[str, Any] = {
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": spec["availability_status"],
            "status": "pending_review",
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "url": spec["url"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "notes": notes,
            "source_locale": "en",
            "uses": map_keys("uses", spec["use_keys"]),
            "industries": map_keys("industries", spec["industry_keys"]),
            "movement_types": map_keys("movement", spec.get("movement") or "stationary"),
            "information_source_urls": [spec["url"], HOME],
            "tags": spec.get("tags") or [],
        }
        for k in (
            "payload_kg",
            "length_mm",
            "width_mm",
            "height_mm",
            "reach_mm",
            "weight_kg",
            "speed",
        ):
            if spec.get(k) is not None:
                body[k] = spec[k]
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patched", spec["id"], spec["family_key"])
        except Exception as e:  # noqa: BLE001
            for drop in ("uses", "industries", "movement_types", "tags"):
                body.pop(drop, None)
            try:
                client._patch(f"robots/robots/{spec['id']}/", body)
                print("patched", spec["id"], "(minimal)", e)
            except Exception as e2:  # noqa: BLE001
                print("FAIL", spec["id"], e2)
        force_en(client, spec["id"], row)

    report = _RESEARCH / "staging" / "reports" / "formic-discover.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"apply": args.apply, "robots": plan}, indent=2),
        encoding="utf-8",
    )
    print("Report ->", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
