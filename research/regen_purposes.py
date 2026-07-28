"""Regenerate `purpose` for robots whose stored purpose duplicates their description.

Runs the SAME logic the fixed auto-research pipeline now uses, scoped to the purpose field
so it costs one Gemini classify call per robot instead of a full re-enrichment:

    classifier task phrase  ->  taxonomy fallback  ->  blank

with `purpose_duplicates_description` guarding every step, so a regenerated purpose can
never come back as a copy of the description again.

Only robots that currently FAIL the duplicate check are touched; everything else is left
alone. Published/approved rows are live content, so they need --include-published.

Usage:
  python regen_purposes.py --company 1461                       # dry-run
  python regen_purposes.py --company 1461 --apply
  python regen_purposes.py --company 773 --apply --include-published
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
from robot_auto_research import _classify_robot, _purpose_from_taxonomy
from validate_staging import purpose_duplicates_description

EDITABLE = {"pending_review", "draft"}


def _m2m_keys(values) -> str:
    if not isinstance(values, list):
        return ""
    keys = []
    for v in values:
        k = v.get("key") if isinstance(v, dict) else v
        if k:
            keys.append(str(k))
    return "|".join(keys)


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate duplicated purposes")
    ap.add_argument("--company", type=int)
    ap.add_argument("--ids-file", help="JSON file with a list of robot ids to target directly")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-published", action="store_true")
    ap.add_argument("--status", action="append",
                    help="restrict to these statuses (repeatable), e.g. --status published. "
                         "Naming 'published'/'approved' is itself the explicit opt-in to edit live rows.")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    # An explicit --status list replaces the default Draft/To-Review-only guard: asking for
    # published by name IS the opt-in, so it must not also require --include-published.
    if args.status:
        editable = {s.strip().lower() for s in args.status}
    else:
        editable = set(EDITABLE)

    client = ResearchApiClient()
    robots: list | None = None
    if args.ids_file:
        # Direct id targeting: the DB-wide scan reports ids, and the affected rows span
        # many companies, so company-scoped fetching would mean resolving ids first.
        wanted = json.loads(Path(args.ids_file).read_text(encoding="utf-8"))
        robots = []
        for rid in wanted:
            row = None
            for attempt in range(5):
                try:
                    row = client._get(f"robots/robots/{rid}/")
                    break
                except Exception as exc:
                    print(f"  fetch {rid} retry {attempt}: {str(exc)[:50]}", file=sys.stderr)
                    time.sleep(2 ** attempt)
            if row:
                robots.append(row)
        print(f"fetched {len(robots)}/{len(wanted)} targeted robots")
    else:
        if not args.company:
            print("ERROR: pass --company or --ids-file", file=sys.stderr)
            return 1
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

    targets, skipped_live = [], 0
    for robot in sorted(robots, key=lambda r: int(r["id"])):
        description = (robot.get("description") or "").strip()
        purpose = (robot.get("purpose") or "").strip()
        if not purpose_duplicates_description(purpose, description):
            continue
        status = str(robot.get("status") or "").lower()
        if status not in editable and not (args.include_published and not args.status):
            skipped_live += 1
            continue
        targets.append(robot)
    if args.limit:
        targets = targets[: args.limit]

    print(f"duplicated purposes to regenerate: {len(targets)} (live rows skipped: {skipped_live})")
    plan, blanked = [], 0
    for robot in targets:
        rid = int(robot["id"])
        name = robot.get("name") or ""
        description = (robot.get("description") or "").strip()
        # Feed the classifier the robot's own prose; it must return a TASK phrase, and the
        # guard below rejects anything that comes back as a slice of that prose.
        text = "\n".join(p for p in (description, (robot.get("features") or "").strip()) if p)
        new = ""
        try:
            new = (_classify_robot(name, text) or {}).get("purpose") or ""
        except Exception as exc:
            print(f"  classify failed {rid}: {str(exc)[:50]}", file=sys.stderr)
        if new and purpose_duplicates_description(new, description):
            new = ""
        if not new:
            new = _purpose_from_taxonomy(_m2m_keys(robot.get("uses")), "")
            if new and purpose_duplicates_description(new, description):
                new = ""
        if not new:
            blanked += 1
        plan.append((rid, name, str(robot.get("status") or ""), new))
        print(f"  {rid:<6}{name[:24]:<25} -> {new or '(blank)'!r}")
        time.sleep(0.2)

    print(f"\nregenerated: {len(plan) - blanked} | blanked (no honest task found): {blanked}")
    if not args.apply:
        print("Dry-run. Re-run with --apply.")
        return 0

    ok = fail = 0
    for rid, name, status, new in plan:
        try:
            client._patch(f"robots/robots/{rid}/", {"purpose": new})
            ok += 1
        except Exception as exc:
            fail += 1
            print(f"  FAIL {rid}: {str(exc)[:70]}", file=sys.stderr)
        time.sleep(0.15)
    print(json.dumps({"ok": fail == 0, "updated": ok, "failed": fail, "blanked": blanked}, indent=2))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
