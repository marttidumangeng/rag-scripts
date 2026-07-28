"""Repair robots whose `purpose` merely repeats their `description`.

Root cause (fixed 2026-07-20): robot_auto_research.py set
`purpose = description.split(".")[0][:200]`, so any robot enriched through that path got a
purpose that was the description's first sentence — and an *exact* copy whenever the
description was a single sentence under 200 chars. Measured over 12 sampled companies:
193 robots (IIT 9/11, Kawasaki 56/56, Estun 92/264, AeroVironment 25/34, Unitree 6, Jaten 5).

This script only repairs stored rows. Prevention lives in:
  - validate_staging.purpose_duplicates_description()  (blocks new staged rows)
  - robots.quality.purpose_duplicates_description()    (queue warning on stored rows)

SAFETY: defaults to Draft / To Review only. Published + Approved rows are live content and
are skipped unless --include-published is passed explicitly (stakeholder rule: research
tooling must not auto-edit live robots).

Resolution order per robot:
  1. curated purpose from PURPOSES (hand-written, preferred)
  2. --blank  -> clear the purpose (missing_purpose warning beats a duplicated purpose)
  3. otherwise: report only, change nothing

Usage:
  python fix_purpose_dupes.py --company 50                      # dry-run report
  python fix_purpose_dupes.py --company 50 --apply              # fix Draft/To Review only
  python fix_purpose_dupes.py --company 50 --apply --include-published
  python fix_purpose_dupes.py --company 220 --blank --apply     # clear dupes wholesale
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_RD = Path(__file__).resolve().parent
if str(_RD) not in sys.path:
    sys.path.insert(0, str(_RD))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from validate_staging import purpose_duplicates_description

EDITABLE = {"pending_review", "draft"}

# Curated task statements. Keyed by robot id — written from each robot's own description.
PURPOSES: dict[int, str] = {
    # IIT (company 50)
    2968: "Rough-terrain legged locomotion research",
    2969: "Mobile manipulation on legs in terrain wheeled vehicles cannot cross",
    2970: "Distributed environmental sensing with biodegradable seed robots",
    2971: "Soil exploration and monitoring via root-like growth",
    2972: "Lower-limb walking assistance for people with mobility impairments",
    3689: "Outdoor rough-terrain legged mobility for industrial inspection",
    3690: "Growth-based locomotion through confined, unstructured spaces",
    5206: "High-strength rough-terrain quadruped locomotion research",
    5207: "Compact lightweight quadruped locomotion research",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Fix purpose==description duplicates")
    ap.add_argument("--company", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--blank", action="store_true", help="clear duplicated purposes with no curated replacement")
    ap.add_argument("--include-published", action="store_true",
                    help="ALSO edit published/approved rows (live content — explicit opt-in)")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for attempt in range(12):
        try:
            robots = client.list_robots_for_company(args.company)
            break
        except Exception as exc:
            print(f"list retry {attempt}: {str(exc)[:60]}", file=sys.stderr)
            time.sleep(5)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr)
        return 1

    plan, skipped_live, no_replacement = [], [], []
    for robot in sorted(robots, key=lambda r: int(r["id"])):
        rid = int(robot["id"])
        status = str(robot.get("status") or "").lower()
        description = (robot.get("description") or "").strip()
        purpose = (robot.get("purpose") or "").strip()
        kind = purpose_duplicates_description(purpose, description)
        if not kind:
            continue

        editable = status in EDITABLE or args.include_published
        replacement = PURPOSES.get(rid, "" if args.blank else None)
        if replacement is None:
            no_replacement.append((rid, robot.get("name"), status, kind))
            continue
        if not editable:
            skipped_live.append((rid, robot.get("name"), status, kind))
            continue
        plan.append((rid, robot.get("name"), status, kind, replacement))
        print(f"  {rid:<6}{str(robot.get('name'))[:22]:<23} [{status:<14}] {kind:<15} -> {replacement or '(blank)'!r}")

    print(f"\nto fix: {len(plan)} | live rows skipped: {len(skipped_live)} | no replacement: {len(no_replacement)}")
    for rid, name, status, kind in skipped_live:
        print(f"   SKIP-LIVE {rid} {str(name)[:24]} [{status}] {kind} — pass --include-published to edit")
    for rid, name, status, kind in no_replacement:
        print(f"   NO-FIX    {rid} {str(name)[:24]} [{status}] {kind} — add to PURPOSES or use --blank")

    if not plan:
        print("Nothing to apply.")
        return 0
    if not args.apply:
        print("\nDry-run. Re-run with --apply.")
        return 0

    ok = fail = 0
    for rid, name, status, kind, replacement in plan:
        try:
            client._patch(f"robots/robots/{rid}/", {"purpose": replacement})
            ok += 1
            print(f"  ok {rid} {name}")
        except Exception as exc:
            fail += 1
            print(f"  FAIL {rid}: {str(exc)[:70]}", file=sys.stderr)
        time.sleep(0.15)
    print(json.dumps({"ok": fail == 0, "fixed": ok, "failed": fail}, indent=2))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
