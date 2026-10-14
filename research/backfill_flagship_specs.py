"""Backfill missing specs on 4 famous-but-thin LIVE robots (Martti-directed, 2026-09-17).

WHY: the /compare and /alternatives sitemap seeding ranks robots by data
richness (prod heat_score is all zero), so the highest-search-demand robots —
Atlas, Unitree H1, UR10e, Digit — miss the seeded URL lists because their rows
are thin. Martti explicitly asked to enrich these four now.

RULES APPLIED
-------------
* Fill-empty-only: a field is written ONLY when the prod row has it empty.
  Nothing existing is overwritten (import-new-only spirit).
* Manufacturer sources only (no robolist/third-party numbers):
    Atlas  https://bostondynamics.com/products/atlas/
    H1     https://www.unitree.com/h1
    UR10e  https://www.universal-robots.com/media/1807466/ur10e_e-series_datasheets_web.pdf
    Digit  https://www.agilityrobotics.com/solutions/digit-5  (marked
           "preliminary estimates" by Agility — noted in notes)
* Unpublished values stay empty: Atlas speed/price, H1 payload/runtime,
  Digit weight/DOF/speed. Not invented.
* release_year needs a grounded citation (project_release_year_citation_gate):
  Atlas release_year=2024 cites Boston Dynamics' own electric-Atlas
  announcement of 2024-04-17; the citation line is APPENDED to notes.
* Plain partial PATCH /robots/robots/{id}/ — wipe-safe for scalar fields
  (reference_bulk_import_media_backfill); bulk-import would divert typed
  specs into notes.
* speed column convention is km/h (SpecificationsTab renders "N km/h"):
  H1's official 3.3 m/s -> 11.88 km/h.

Usage:  python backfill_flagship_specs.py           (dry run)
        python backfill_flagship_specs.py --apply   (PATCH + verify)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient  # noqa: E402

EXPECTED_ROBOTS = 4

# field -> value to write IF the field is currently empty.
PLAN: dict[int, dict] = {
    35: {  # Atlas (Boston Dynamics) — https://bostondynamics.com/products/atlas/
        "fields": {
            "reach_mm": 2300,            # "2.3 m (7.5 ft)"
            "battery_life": "4 hours",
            "release_year": 2024,
            "environment": "IP67; operating temperature -20°C to 40°C",
        },
        "notes_append": (
            "release_year=2024: Boston Dynamics introduced the electric Atlas on 2024-04-17 "
            "(https://bostondynamics.com/news/introducing-electric-atlas/). "
            "Specs (reach 2.3m, 4h battery, IP67) from https://bostondynamics.com/products/atlas/"
        ),
    },
    40: {  # Unitree H1 — https://www.unitree.com/h1
        "fields": {
            "dof": 18,                    # (4 per arm + 5 per leg) x 2
            "speed": 11.88,               # official 3.3 m/s walking speed
            "battery_life": "864Wh battery (15Ah, 67.2V)",
            "actuation_mechanism": (
                "Electric joint motors; max torque: knee 360 N·m, hip 220 N·m, "
                "ankle 59 N·m, arm 75 N·m"
            ),
        },
        "notes_append": (
            "Specs (18 DOF, 3.3 m/s = 11.88 km/h, 864Wh, joint torques) from "
            "https://www.unitree.com/h1"
        ),
    },
    3543: {  # UR10e — official e-Series datasheet
        "fields": {
            "repeatability_mm": 0.05,     # +/-0.05 mm per ISO 9283
            "environment": "IP54",
        },
        "notes_append": (
            "Repeatability ±0.05mm (ISO 9283) and IP54 from the official UR10e datasheet "
            "(https://www.universal-robots.com/media/1807466/ur10e_e-series_datasheets_web.pdf)"
        ),
    },
    11: {  # Digit (Agility Robotics) — current official Digit page
        "fields": {
            "payload_kg": 23,             # "23kg/50lbs"
            "reach_mm": 2200,             # "2.2m/7.2ft"
            "battery_life": "10:1 run-to-charge ratio; up to 20 hours of work per 24-hour period",
        },
        "notes_append": (
            "Specs (payload 23kg, reach 2.2m, 10:1 run-to-charge) from "
            "https://www.agilityrobotics.com/solutions/digit-5 — Agility marks these as "
            "preliminary estimates subject to change"
        ),
    },
}


def is_empty(value) -> bool:
    return value is None or value == "" or (isinstance(value, list) and not value)


def main() -> None:
    apply = "--apply" in sys.argv
    client = ResearchApiClient()
    assert len(PLAN) == EXPECTED_ROBOTS, f"scope check failed: {len(PLAN)} != {EXPECTED_ROBOTS}"

    payloads: dict[int, dict] = {}
    for robot_id, plan in PLAN.items():
        row = client._get(f"robots/robots/{robot_id}/")
        name = row.get("name")
        payload: dict = {}
        for field, value in plan["fields"].items():
            current = row.get(field)
            if is_empty(current):
                payload[field] = value
            else:
                print(f"  SKIP {name}.{field}: already set to {current!r}")
        if plan.get("notes_append"):
            existing_notes = str(row.get("notes") or "").strip()
            if plan["notes_append"] not in existing_notes:
                payload["notes"] = (existing_notes + "\n" if existing_notes else "") + plan["notes_append"]
        if payload:
            payloads[robot_id] = payload
        print(f"{name} (id {robot_id}): will write {sorted(k for k in payload if k != 'notes')}"
              + (" + notes citation" if "notes" in payload else ""))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to PATCH.")
        return

    print("\nApplying...")
    for robot_id, payload in payloads.items():
        client._patch(f"robots/robots/{robot_id}/", payload)

    print("Verifying...")
    failures = 0
    for robot_id, payload in payloads.items():
        after = client._get(f"robots/robots/{robot_id}/")
        for field, expected in payload.items():
            got = after.get(field)
            ok = (str(got).strip() == str(expected).strip()) if field != "notes" else (
                PLAN[robot_id]["notes_append"] in str(got or "")
            )
            if field in ("payload_kg", "reach_mm", "dof", "speed", "repeatability_mm", "release_year"):
                ok = got is not None and abs(float(got) - float(expected)) < 0.001
            status = "OK " if ok else "FAIL"
            if not ok:
                failures += 1
            print(f"  {status} {after.get('name')}.{field} = {got!r}")
    print(f"\n{'ALL VERIFIED' if failures == 0 else f'{failures} FIELD(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
