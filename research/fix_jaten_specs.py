"""Type OEM specs + availability for Jaten (company 1461) pending_review AGVs.

Why: payload/dimensions lived only in free-text `features`; the typed columns were
empty on 12/14. `payload_kg` is NOT a Robot column (stays in features — documented
limitation), but `length_mm`/`width_mm`/`height_mm`/`speed`/`battery_capacity`/
`voltage` ARE, and every record's OEM "Dimension: L…×W…×H…mm" parses into them.

Sources:
  - 5 models still on the live catalog: full OEM spec table scraped from the
    rendered PDP (staging/reports/jaten-live-specs.json) — speed + battery too.
  - 9 delisted models: dimensions taken from their own stored OEM feature string
    (structuring existing OEM data; nothing invented). Speed/battery left blank.

release_year: left NULL on all 14 — no launch citation exists on the PDP, the
Product Specification PDFs, or press. Never guessed.

Gap-fill via bulk-import patch_existing (fills blank columns only, never
overwrites, never creates). No media touched.

Usage:
  python fix_jaten_specs.py            # dry-run
  python fix_jaten_specs.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

COMPANY_ID = 1461
COMPANY_SLUG = "jaten-robot"

# OEM spec table from the live rendered PDPs (jaten-robotics.com/index/Agv/detail.html?id=…).
# speed converted to km/h (Robot.speed is km/h).  "≤0.8 m/s"→2.88, "≤1 m/s"→3.6, "35 m/min"→2.1
LIVE = {
    2911: {"model": "R2SDM1500-335-MG0", "cid": "1001025",
           "speed": 2.88, "battery_capacity": "D48V 45AH", "voltage": "48V"},
    5185: {"model": "SDM300-339-MGD", "cid": "1001026",
           "speed": 3.6, "battery_capacity": "D48V 24AH", "voltage": "48V"},
    5190: {"model": "MN30-164", "cid": "1000003",
           "speed": 2.1, "battery_capacity": "DC24V 10AH (iron-lithium battery)", "voltage": "24V"},
    5191: {"model": "SDM500-D228", "cid": "1000001",
           "speed": 3.6, "battery_capacity": "DC48V 30AH (iron-lithium battery)", "voltage": "48V"},
    2916: {"model": "AGV-31-MC500", "cid": "1000292",
           "speed": 2.1, "battery_capacity": "DC24V 60AH", "voltage": "24V"},
}

# Availability: these are current/listed Jaten products. 5 records lost it during the
# 2026-07-14 enrich; the other 9 already carry "Released".
AVAIL_KEY = "available"

DIM_RE = re.compile(r"L\s*(\d+(?:\.\d+)?)\s*[×xX*]\s*W\s*(\d+(?:\.\d+)?)\s*[×xX*]\s*H\s*(\d+(?:\.\d+)?)\s*mm", re.I)


def parse_dims(text: str) -> tuple[float, float, float] | None:
    m = DIM_RE.search(text or "")
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), float(m.group(3))


def main() -> int:
    ap = argparse.ArgumentParser(description="Type Jaten OEM specs + availability")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(15):
        try:
            robots = client.list_robots_for_company(COMPANY_ID); break
        except Exception as e:
            print(f"list retry {a}: {str(e)[:60]}", file=sys.stderr); time.sleep(6)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr); return 1

    # OEM dims for the live models (authoritative, from the scraped spec table)
    live_specs_path = _RESEARCH_DIR / "staging" / "reports" / "jaten-live-specs.json"
    live_dims: dict[str, tuple[float, float, float]] = {}
    if live_specs_path.is_file():
        for cid, rec in json.loads(live_specs_path.read_text(encoding="utf-8")).items():
            d = parse_dims((rec.get("specs") or {}).get("Dimension", ""))
            if d:
                live_dims[cid] = d

    plan, staging = [], {}
    for r in sorted(robots, key=lambda x: x["id"]):
        rid = int(r["id"])
        if str(r.get("status") or "").lower() != "pending_review":
            continue
        name = r["name"]
        live = LIVE.get(rid)
        src = "features"
        dims = None
        if live and live["cid"] in live_dims:
            dims = live_dims[live["cid"]]
            src = "OEM PDP"
        if not dims:
            dims = parse_dims(r.get("features") or "") or parse_dims(r.get("description") or "")
        row: dict[str, Any] = {
            "id": rid, "name": name, "company_slug": COMPANY_SLUG,
            "availability_status_key": AVAIL_KEY,
            "source_locale": "en",
        }
        if dims:
            row["length_mm"], row["width_mm"], row["height_mm"] = dims
        if live:
            row["speed"] = live["speed"]
            row["battery_capacity"] = live["battery_capacity"]
            row["voltage"] = live["voltage"]

        have_dims = r.get("length_mm") or r.get("width_mm") or r.get("height_mm")
        cur_avail = r.get("availability_status")
        staging[rid] = row
        plan.append({"id": rid, "name": name, "dims": dims, "dim_src": src if dims else "NONE",
                     "speed": row.get("speed"), "batt": row.get("battery_capacity"),
                     "had_dims": bool(have_dims), "had_avail": bool(cur_avail)})
        print(f"  {rid:<5} {name[:22]:<23} dims={dims or '-'} ({src if dims else 'none'})"
              f" speed={row.get('speed') or '-'} batt={(row.get('battery_capacity') or '-')[:24]}"
              f" avail_had={'y' if cur_avail else 'n'}")

    nodims = [p for p in plan if not p["dims"]]
    if nodims:
        print(f"\nWARN: no dims parsed for {[p['id'] for p in nodims]}", file=sys.stderr)
    print(f"\nTargets: {len(plan)} | with dims: {sum(1 for p in plan if p['dims'])} "
          f"| with speed/battery: {sum(1 for p in plan if p['speed'])}")
    preview = _RESEARCH_DIR / "staging" / "reports" / "jaten-specs-preview.json"
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply")
        return 0

    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    all_ok = True
    for p in plan:
        rid = p["id"]
        bulk_row = staging_dict_to_bulk_import_row(staging[rid])
        bulk_row["id"] = rid
        try:
            res = client.bulk_import_robots(
                [bulk_row], update_existing=True, patch_existing=True,
                replace_media=False, status="pending_review", skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr); continue
        if int(res.get("created_count") or 0):
            all_ok = False
            print(f"WARNING {rid}: created NEW robot -> {res}", file=sys.stderr)
        if int(res.get("error_count") or 0):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {res}", file=sys.stderr)
        for k in totals:
            totals[k] += int(res.get(k) or 0)
        print(f"  patched {rid}: {res.get('results')}")

    out = {"ok": all_ok, "targets": len(plan), **totals}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "jaten-specs-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
