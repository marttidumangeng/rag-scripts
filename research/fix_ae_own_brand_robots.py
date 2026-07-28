#!/usr/bin/env python3
"""Enrich the AE Robotics (1375) records that really are AE's own products.

Of the 23 robots in AE's to-review queue only 6 carry an AE-side brand on the
vendor page (`Brand: AE` or `Brand: A&R`); the other 17 were third-party lines and
were rejected as duplicates or moved to their real manufacturer by
``fix_ae_reseller_spillover.py``.

Targets here
------------
* 3530 - Cobot Welding Station IMOS-W-I5-350-1000C (Brand: AE). Full configuration
  table available on the PDP. **Corrects a real spec error**: ``payload_kg`` held
  350, which is the *machine weight*, not a payload.
* 3531 / 4819 / 4821 - A&R delta robots AR-600D / AR-500D / AR-1000D.

Rule 11 (family tables) - READ THIS BEFORE TOUCHING DELTA PAYLOADS
------------------------------------------------------------------
The delta PDP is one 4-column table (AR-500D | AR-600D | AR-800D | AR-1000D) reused
on every delta product page. Fetching the same page repeatedly returned **different
column alignments** for the "Rated load" row - `1KG 3KG 3KG 5KG` on one render and
`1KG 1KG 3KG 5KG` on two others. That is precisely the column-shift hazard rule 11
warns about, so AR-600D's payload is *not* reliably parseable from this page. It is
left at its existing stored value (1.0 kg, which matches the majority render) and the
ambiguity is recorded in notes rather than silently "confirmed". AR-500D (first
column) and AR-1000D (last column) are stable across every render and are safe.

Media
-----
* 3530 gets two verified AE-branded photographs of the actual cell.
  ``image_1692176116_AE-4.jpg`` is deliberately NOT used - it shows AE's *palletizing*
  cell, not the welding station (rule 9c: no wrong-product substitution).
* The deltas keep their existing hero. Only one delta image exists and all four SKUs
  share it, and it carries **Warsonco** branding - AE's A&R deltas are rebadged
  Warsonco hardware. That provenance is recorded in notes; it is not re-litigated
  here, and no per-SKU image is invented.

Usage:
    python fix_ae_own_brand_robots.py                  # dry run
    python fix_ae_own_brand_robots.py --apply --copy-media
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()

import requests

from api_client import ResearchApiClient

REPORT = _HERE / "staging" / "reports" / "ae-own-brand.json"
REPORT.parent.mkdir(parents=True, exist_ok=True)

Q = "https://qiniu.digood-assets-fallback.work/5"
DELTA_CATEGORY_URL = "https://www.automationar.com/products/delta-robot.html"

DELTA_SHARED_FEATURES = (
    "Three-DOF spatial parallel (delta) mechanism; available in 3-axis and 4-axis "
    "configurations\n"
    "Drive train mounted entirely in the fixed upper platform, giving a low moving mass "
    "and high dynamic performance\n"
    "Repeatability +/-0.1 mm\n"
    "Suspension (overhead) mounting\n"
    "WSC-GJK2-T4 electrical control system\n"
    "Cycle time 0.4 s/beat over an x=400 mm, y=50 mm pick-and-place move\n"
    "AC servo drive\n"
    "Motion instruction set: PTP, LINE, PICK, PLACE\n"
    "7-inch teach pendant\n"
    "Optional vision positioning module (1.3 MP camera, add-on lens, light source)"
)

DELTA_PURPOSE = (
    "High-speed pick-and-place\n"
    "Packaging and cartoning\n"
    "Food and beverage handling\n"
    "Product sorting on conveyor lines"
)

DELTA_PROVENANCE = (
    "[PROVENANCE 2026-07-26] Brand on the automationar.com product page is \"A&R\" "
    "(AE Robotics' own label) and the model codes are AR-500D/600D/800D/1000D. The only "
    "delta product imagery AE publishes is a single render shared across all four SKUs, "
    "and it carries **Warsonco** (华盛控科技) branding - i.e. the A&R delta line is "
    "rebadged Warsonco hardware. The shared hero is kept because no per-SKU image "
    "exists; it is NOT evidence of this specific model.\n"
    "ACTION FOR TEAM: if per-SKU delta photos matter, request them from AE, or record "
    "Warsonco as the actual manufacturer and treat A&R as a reseller label.\n"
    "---\n"
)

DELTA_TABLE_NOTE = (
    "[SPEC SOURCE 2026-07-26] Specs come from the shared 4-column DELTA table on the "
    "automationar.com delta pages (AR-500D | AR-600D | AR-800D | AR-1000D). Repeated "
    "fetches of that page returned DIFFERENT column alignments for the \"Rated load\" "
    "row (`1KG 3KG 3KG 5KG` once, `1KG 1KG 3KG 5KG` twice), so AR-600D's rated load is "
    "not reliably parseable from this source. AR-600D payload_kg is therefore left at "
    "its stored value and must not be treated as OEM-confirmed. AR-500D (1 kg) and "
    "AR-1000D (5 kg) are stable across every render.\n"
    "---\n"
)

ROBOT_DATA: dict[int, dict[str, Any]] = {
    # ---------------- AE's own cobot welding cell ----------------
    3530: {
        "label": "Cobot Welding Station IMOS-W-I5-350-1000C",
        "patch": {
            # Page states model "IMOS-W-I5-350-1000C"; drop the leading "AUBO" from the
            # display name - AE builds the cell, AUBO only supplies the arm.
            "name": "Cobot Welding Station IMOS-W-I5-350-1000C",
            "model_name": "IMOS-W-I5-350-1000C",
            "variant_code": "IMOS-W-I5-350-1000C",
            "variant_label": "350A / 1000C",
            "family_key": "ae-robotics-co-ltd:cobot-welding-station",
            "family_name": "Cobot Welding Station",
            "family_url": "https://www.automationar.com/products/cobot-welding-station.html",
            "product_url_scope": "exact_variant",
            "description": (
                "The IMOS-W-I5-350-1000C is a self-contained collaborative welding cell "
                "from AE Robotics, pairing an AUBO six-axis cobot with a 350 A MIG/MAG "
                "power source over a 1000 x 1000 mm fixtured welding table. Programs are "
                "created by hand-guiding the arm through the joint rather than writing "
                "code, so a fabricator can set up a part without robot programming "
                "experience, and the whole station arrives on levelling feet ready to be "
                "wheeled into a bay."
            ),
            "purpose": (
                "MIG/MAG/CO2 welding of carbon steel\n"
                "Stainless steel welding\n"
                "Small-batch and job-shop fabrication"
            ),
            "features": (
                "Integrated collaborative welding cell built on an AUBO six-axis cobot\n"
                "Programming-free setup: operator hand-guides (drags) the arm to teach "
                "the weld path\n"
                "350 A welding machine capacity, MAG/MIG process\n"
                "1000 x 1000 mm fixtured welding table, 28 mm station apertures on a "
                "100 mm pitch\n"
                "Welds carbon steel and stainless steel\n"
                "Air-cooled torch; wire diameters 0.8 / 1.0 / 1.2 mm\n"
                "Collision protection fitted as standard; optional gun cleaner\n"
                "Ingress protection IP54\n"
                "Input supply 3-phase 5-wire AC 380 V\n"
                "Fieldbus: Ethernet, Modbus RTU/TCP, PROFINET\n"
                "Station footprint 1280 x 1160 x 1500 mm, mass 350 kg\n"
                "Customisable configuration and quick deployment"
            ),
            # payload_kg previously held 350 - that is the MACHINE WEIGHT, not a payload.
            "payload_kg": None,
            "weight_kg": 350.0,
            "length_mm": 1280.0,
            "width_mm": 1160.0,
            "height_mm": 1500.0,
            "dof": 6,
            "availability_status": 11,   # Available
            "categories": ["Industrial-Robot"],
            "uses": [41, 21],            # arc-welding, assembly
            "industries": [12, 32, 50],  # manufacturing, metalworking, industrial
            "movement_types": [10],      # stationary
            "tags": ["Welding", "Cobot", "Collaborative Robot", "Industrial",
                     "Manufacturing", "Assembly"],
            "mounting_options": "Free-standing cabinet on levelling feet",
            "safety_fencing": (
                "Collaborative operation with standard collision protection; no perimeter "
                "fencing supplied with the cell."
            ),
            "programming_interface": (
                "Programming-free hand-guiding (drag teaching) via the AUBO pendant; "
                "Ethernet, Modbus RTU/TCP and PROFINET interfaces."
            ),
            "deployment_context": (
                "Job shops and small-batch fabricators welding carbon and stainless steel "
                "who need a turnkey cell rather than an integrated robot line."
            ),
            "ecosystem_compatibility": (
                "AUBO six-axis cobot arm and pendant; optional gun cleaner; "
                "Ethernet / Modbus RTU / TCP / PROFINET fieldbus."
            ),
            "information_source_urls": [
                "https://www.automationar.com/product/"
                "aubo-6-axis-cobot-welding-station-make-welding-simple-program.html"
            ],
        },
        # AE-1 = front elevation, AE-3 = three-quarter view. Both verified as THIS cell.
        "media": [f"{Q}/image_1690250361_AE-1.jpg", f"{Q}/1690252567_AE-3.jpg"],
        "videos": ["https://youtu.be/qUD-Y1uSrhM"],
    },
}


def _delta(model: str, reach_x: int, envelope: str, weight: float,
           payload: float | None, extra_feature: str = "") -> dict[str, Any]:
    return {
        "label": f"A&R Delta {model}",
        "note": DELTA_PROVENANCE + DELTA_TABLE_NOTE,
        "media": [],       # keep existing shared hero; nothing new to add
        "patch": {
            "name": f"Delta Robot {model}",
            "model_name": model,
            "variant_code": model,
            "variant_label": model.replace("AR-", ""),
            "family_key": "ae-robotics-co-ltd:ar-delta",
            "family_name": "AR Delta",
            "family_url": DELTA_CATEGORY_URL,
            "product_url_scope": "family",   # the PDP carries the whole 4-SKU table
            "description": (
                f"The A&R {model} is a delta (three-DOF spatial parallel) robot built for "
                f"high-rate pick-and-place over a {reach_x} mm working diameter. Its "
                "motors all sit in the fixed upper platform, so the moving linkage stays "
                "light and the arm can complete a short transfer in around 0.4 seconds - "
                "the reason machines of this shape dominate packaging and food lines. It "
                "mounts overhead above a conveyor and can be ordered in three- or "
                "four-axis form."
            ),
            "purpose": DELTA_PURPOSE,
            "features": (
                f"Rated load {payload:.0f} kg\n" if payload else ""
            ) + (
                f"Working range {envelope}\n"
                f"Robot weight {weight:.0f} kg\n"
                + (extra_feature + "\n" if extra_feature else "")
                + DELTA_SHARED_FEATURES
            ),
            "reach_mm": float(reach_x),
            "weight_kg": weight,
            "repeatability_mm": 0.1,
            "dof": 4,
            "availability_status": 11,
            "categories": ["Industrial-Robot"],
            "uses": [22, 37, 47],          # pick-and-place, packaging, sorting
            "industries": [59, 12, 30],    # food-beverage, manufacturing, fmcg
            "movement_types": [10],        # stationary
            "tags": ["Delta Robot", "Pick-and-Place", "Packaging", "Industrial",
                     "Manufacturing", "food"],
            "mounting_options": "Suspension (overhead / gantry mount)",
            "programming_interface": (
                "7-inch teach pendant with PTP, LINE, PICK and PLACE motion instructions; "
                "WSC-GJK2-T4 electrical control system."
            ),
            "deployment_context": (
                "Mounted above a conveyor on packaging, food and consumer-goods lines "
                "needing sustained high-rate picking."
            ),
            "ecosystem_compatibility": (
                "Optional vision positioning module (1.3 MP camera, add-on lens, light "
                "source); AC servo drive train."
            ),
            "information_source_urls": [
                "https://www.automationar.com/product/"
                "3-4axis-delta-robot-1kg-payload-600mm-working-diameter-for-packing-application.html",
                DELTA_CATEGORY_URL,
            ],
        },
    }


# AR-500D: first column, stable across every render -> payload 1 kg is safe.
ROBOT_DATA[4819] = _delta("AR-500D", 500, "X=500 mm, Y=150 mm", 30.0, 1.0)
# AR-600D: payload column NOT reliably parseable (see DELTA_TABLE_NOTE) -> omit payload,
# leave whatever is stored, and say so in features.
ROBOT_DATA[3531] = _delta(
    "AR-600D", 600, "X=600 mm, Y=200 mm", 67.0, None,
    extra_feature=(
        "Rated load is not stated unambiguously for this SKU on the manufacturer's "
        "shared spec table - see notes"
    ),
)
# AR-1000D: last column, stable -> payload 5 kg is safe.
ROBOT_DATA[4821] = _delta(
    "AR-1000D", 1000, "X=1000 mm, Y=300 mm (circular envelope 1040 mm)", 67.0, 5.0
)

# Intra-AE duplicates - reported only, deliberately NOT auto-rejected.
INTRA_AE_DUPLICATES = [
    (1455, "AE Delta Robot", 3531, "Delta Robot AR-600D",
     "same PDP URL, same specs (1 kg / 600 mm / 67 kg / 0.1 mm) - 1455 is an "
     "unnamed earlier copy of the AR-600D record"),
    (3534, "AE AIR20-A Industrial Robot", 1451, "AE AIR20-A (published)",
     "same PDP URL and identical specs (20 kg / 1702 mm / 260 kg / 0.03 mm); 1451 is "
     "already published with a working hero"),
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF", b"GIF8")


def img_ok(url: str) -> tuple[bool, str]:
    try:
        r = requests.get(url, headers=UA, timeout=45)
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    if not any(r.content.startswith(m) for m in MAGIC):
        return False, "not an image (magic bytes)"
    return True, f"ok {len(r.content)}B"


def resolve_tags(client: ResearchApiClient, names: list[str]) -> tuple[list[str], list[str]]:
    catalog = {(t.get("name") or "").strip() for t in client.list_tags(page_size=500)}
    return [n for n in names if n in catalog], [n for n in names if n not in catalog]


def copy_media(rid: int) -> tuple[bool, str]:
    base = os.environ.get("ADMIN_BASE", "https://ragadmin.robotaigeek.com").rstrip("/")
    url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    try:
        r = requests.post(
            url, headers={"X-Internal-Secret": os.environ.get("INTERNAL_API_SECRET", "")},
            timeout=180,
        )
        return r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    args = ap.parse_args()
    tag = "APPLY" if args.apply else "DRY-RUN"
    client = ResearchApiClient()
    log: dict[str, Any] = {"mode": tag, "robots": [], "duplicates": [], "errors": []}

    print(f"=== {tag}: enrich {len(ROBOT_DATA)} AE/A&R own-brand robots ===\n")

    for rid in sorted(ROBOT_DATA):
        spec = ROBOT_DATA[rid]
        patch = dict(spec["patch"])
        row: dict[str, Any] = {"id": rid, "label": spec["label"]}
        print(f"--- {rid}  {spec['label']}")
        try:
            before = client._get(f"robots/robots/{rid}/")
        except Exception as exc:  # noqa: BLE001
            print(f"    FETCH FAILED: {exc}")
            log["errors"].append({"id": rid, "error": str(exc)})
            continue
        if before.get("status") == "published":
            print("    SKIP: published (rule 9)")
            log["errors"].append({"id": rid, "skip": "published"})
            continue

        if patch.get("tags"):
            kept, missing = resolve_tags(client, patch["tags"])
            if missing:
                print(f"    tags dropped (not in catalog): {missing}")
            patch["tags"] = kept

        if spec.get("note"):
            existing = before.get("notes") or ""
            if "[PROVENANCE 2026-07-26]" not in existing:
                patch["notes"] = spec["note"] + existing
            else:
                print("    provenance note already present")

        good: list[str] = []
        for u in spec.get("media") or []:
            ok, why = img_ok(u)
            print(f"    media {'OK  ' if ok else 'FAIL'} {why:<20} {u[-52:]}")
            if ok:
                good.append(u)

        # report what the record will actually carry
        old_payload = before.get("payload_kg")
        if "payload_kg" in patch and patch["payload_kg"] != old_payload:
            print(f"    payload_kg {old_payload} -> {patch['payload_kg']}"
                  + ("   (was machine weight, not payload)" if rid == 3530 else ""))
        print(f"    purpose: {before.get('purpose')!r} -> "
              f"{len((patch.get('purpose') or '').splitlines())} application line(s)")
        print(f"    family_key={patch.get('family_key')!r}")
        row["patch_keys"] = sorted(patch)

        if not args.apply:
            print()
            log["robots"].append(row)
            continue

        try:
            client._patch(f"robots/robots/{rid}/", patch)
        except Exception as exc:  # noqa: BLE001
            print(f"    PATCH FAILED: {exc}")
            log["errors"].append({"id": rid, "error": f"patch: {exc}"})
            continue

        if good or spec.get("videos"):
            payload: dict[str, Any] = {
                "name": patch.get("name") or before.get("name"),
                "company": (before.get("company_ref") or {}).get("name"),
                "url": patch.get("url") or before.get("url"),
            }
            if good:
                payload["image"] = good[0]
                payload["images"] = good
            if spec.get("videos"):
                payload["video_urls"] = spec["videos"]
            try:
                resp = client.bulk_import_robots(
                    [payload], update_existing=True, patch_existing=True,
                    status="pending_review", skip_company_update=True,
                    replace_media=bool(good), replace_videos=bool(spec.get("videos")),
                )
                counts = {k: v for k, v in resp.items() if k.endswith("_count")}
                print(f"    bulk-import: {counts}")
                row["import"] = counts
                if counts.get("created_count"):
                    print("    !! created a NEW robot - investigate, this should update")
            except Exception as exc:  # noqa: BLE001
                print(f"    IMPORT FAILED: {exc}")
                log["errors"].append({"id": rid, "error": f"import: {exc}"})
            if args.copy_media and good:
                ok, msg = copy_media(rid)
                print(f"    copy-media: {'OK' if ok else 'FAIL'} {msg[:80]}")

        after = client._get(f"robots/robots/{rid}/")
        row["after"] = {
            "name": after.get("name"),
            "payload_kg": after.get("payload_kg"),
            "weight_kg": after.get("weight_kg"),
            "family_key": after.get("family_key"),
            "purpose_lines": len((after.get("purpose") or "").splitlines()),
            "photos": len(after.get("photos") or []),
            "videos": len(after.get("videos") or []),
            "hero": bool(after.get("s3_image") or after.get("image")),
        }
        print(f"    -> {json.dumps(row['after'], ensure_ascii=False)}\n")
        log["robots"].append(row)
        time.sleep(0.4)

    print("=== intra-AE duplicates (REPORTED ONLY, no writes) ===")
    for dup_id, dup_name, keep_id, keep_name, why in INTRA_AE_DUPLICATES:
        print(f"  {dup_id} {dup_name!r}\n      duplicates {keep_id} {keep_name!r}\n      {why}")
        log["duplicates"].append(
            {"duplicate_id": dup_id, "duplicate_name": dup_name,
             "keep_id": keep_id, "keep_name": keep_name, "reason": why}
        )

    REPORT.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nrobots={len(log['robots'])} dupes_reported={len(log['duplicates'])} "
          f"errors={len(log['errors'])}\nwrote {REPORT}")


if __name__ == "__main__":
    main()
