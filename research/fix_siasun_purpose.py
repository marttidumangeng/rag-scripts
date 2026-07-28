#!/usr/bin/env python3
"""Rewrite SIASUN (1424) purpose fields that merely copy description.

Root cause: enrich_siasun_soft / fix_siasun_robots set purpose = description.
Stakeholder rule 0z: purpose is a short primary-task phrase (not the first
sentence of description). Prefer OEM task language from the product name /
application area.

Usage:
  python fix_siasun_purpose.py
  python fix_siasun_purpose.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
from api_client import ResearchApiClient
from validate_staging import purpose_duplicates_description

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 1424


def purpose_from_name(name: str, description: str = "") -> str:
    """Derive a short task statement from the OEM product name (+ light desc cues)."""
    n = (name or "").strip()
    nu = n.upper()
    d = (description or "").lower()

    # --- Automotive assembly mobiles (name is the application) ---
    exact = {
        "Commercial Vehicle Assembly Mobile Robot": "Commercial vehicle chassis and cab final assembly",
        "Instrument Panel Line Assisted Assembly Mobile Robot": "Instrument panel assisted assembly",
        "Axle Final Line Assisted Assembly Mobile Robot": "Axle end-of-line assisted assembly",
        "Axle Base Line Assisted Assembly Mobile Robot": "Axle base-line assisted assembly",
        "Central Gear Assisted Assembly Mobile Robot": "Assisted assembly of central gear units",
        "Transmission Assisted Assembly Mobile Robot": "Assisted assembly of vehicle transmissions",
        "Engine Assisted Assembly Mobile Robot": "Assisted assembly of vehicle engines",
        "Front-End Module Assisted Assembly Mobile Robot": "Assisted assembly of front-end modules",
        "Interior & Finishing Line Assisted Assembly Mobile Robot": "Interior and finishing-line assisted assembly",
        "Four-Lift Automotive Assembly Mobile Robot": "Multi-station automotive assembly with four lifts",
        "Triple-Lift Automotive Assembly Mobile Robot": "High-position automotive assembly with triple lifts",
        "Dual-Lift Automotive Assembly Mobile Robot": "Chassis and axle assembly with dual lifts",
        "Single-Lift Automotive Assembly Mobile Robot": "Automotive assembly lifting and docking",
        "Cantilever Shaft Conveyor Mobile Robot": "Cantilever-shaft conveyor material transfer",
        "Roller Conveyor Mobile Robot": "Roller-conveyor material transfer",
        "V-Groove Dual-Lift Conveyor Mobile Robot": "V-groove dual-lift conveyor transfer",
        "Mobile Manipulator Robot": "Mobile manipulation for industrial workcells",
    }
    if n in exact:
        return exact[n]

    if re.fullmatch(r"\d+T Heavy-Duty Mobile Robot", n, re.I):
        return "Heavy-duty industrial material transport"

    # --- Collaborative (GCR) ---
    if re.match(r"^GCR\d", nu):
        return "Collaborative assembly and machine tending"

    # --- SCARA (SA / SN) ---
    if re.match(r"^SA\d", nu) or re.match(r"^SN\d", nu):
        return "High-speed assembly and pick-and-place"

    # --- Industrial arms (SR) ---
    if re.match(r"^SR\d", nu):
        if any(k in d for k in ("weld", "arc")):
            return "Industrial welding and material handling"
        if "pallet" in d:
            return "Industrial palletizing and material handling"
        return "Industrial material handling and manufacturing"

    # --- Named AGV / AMR SKUs ---
    if re.match(r"^P-T\d", nu):
        return "Tugger AGV material transport"
    if re.match(r"^QD\d", nu):
        return "Warehouse AGV material handling"
    if re.match(r"^HANDLING B", nu) or re.match(r"^B\d+S", nu):
        return "Forklift AGV material handling"
    if re.match(r"^D\d", nu):
        return "Differential-drive AGV material handling"
    if re.match(r"^G-\d", nu):
        return "Industrial AGV material transport"
    if re.match(r"^FP\d", nu):
        return "Forklift AGV pallet handling"

    # Fallback: strip brand words from name into a task-ish phrase
    cleaned = re.sub(r"(?i)\b(SIASUN|Robot|Series)\b", "", n)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -/")
    if cleaned and len(cleaned) <= 100:
        return cleaned
    return "Industrial automation"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.ids:
        want = set(args.ids)
        robots = [r for r in robots if int(r["id"]) in want]
    print(f"pending={len(robots)}")

    plan = []
    still_dup = []
    for r in robots:
        rid = int(r["id"])
        # list payload often has purpose/description; refresh if needed
        desc = (r.get("description") or "").strip()
        old = (r.get("purpose") or "").strip()
        kind = purpose_duplicates_description(old, desc)
        junk = (not old) or old.upper() in ("SIASUN", "SIASUN.") or len(old) < 12
        if not kind and not junk and old and len(old) <= 120:
            # already a short non-dup purpose
            continue
        if not kind and not junk:
            continue
        new = purpose_from_name(r.get("name") or "", desc)
        # strip trailing period / brand leftovers
        new = new.rstrip(". ").strip()
        new = re.sub(r"(?i)\bSIASUN\b", "", new).strip()
        if len(new) > 120:
            new = new[:117].rstrip() + "…"
        dup2 = purpose_duplicates_description(new, desc)
        if dup2:
            still_dup.append((rid, r.get("name"), new, dup2))
            # force a safer short form
            new = purpose_from_name(r.get("name") or "", "")
            new = new.rstrip(". ")
            dup2 = purpose_duplicates_description(new, desc)
        plan.append(
            {
                "id": rid,
                "name": r.get("name"),
                "old_kind": kind or "rewrite",
                "old": old[:100],
                "new": new,
                "still_dup": dup2 or "",
            }
        )

    print(f"to_patch={len(plan)} still_flagged_after={sum(1 for p in plan if p['still_dup'])}")
    for p in plan[:12]:
        print(f"  {p['id']} {p['name'][:40]}")
        print(f"    -> {p['new']!r}  (was {p['old_kind']})")
    if still_dup:
        print("WARN still dup after derive:")
        for row in still_dup[:10]:
            print(" ", row)

    out = _HERE / "staging" / "reports" / "siasun-purpose-fix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"apply": args.apply, "plan": plan}, indent=2), encoding="utf-8")
    print("wrote", out)

    if not args.apply:
        print("dry-run only; pass --apply to PATCH")
        return 0

    ok = err = 0
    for p in plan:
        try:
            client._patch(f"robots/robots/{p['id']}/", {"purpose": p["new"]})
            ok += 1
            print(f"  patched {p['id']} -> {p['new']}")
        except Exception as e:
            err += 1
            print(f"  ERROR {p['id']}: {e}")
        time.sleep(0.08)
    print(f"done ok={ok} err={err}")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
