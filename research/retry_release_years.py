"""Retry search-grounded release-year lookups for a company's content queue.

The enrichment pass (robot_auto_research.py) fail-opens on lookup errors —
a rate-limit blip during a run silently nulls the whole batch. This script
re-runs lookup_release_year for every *pending_review* robot whose DB year is
blank (published/approved robots are never touched), with retries, and writes
a report of hits + citations for review.

Apply is deliberately two-step: run once to review the evidence, then re-run
with --apply --ids <id...> to import only the vetted hits. The apply run reads
the SAVED report (it never re-runs lookups, whose results could differ from
what was reviewed). Import goes through bulk-import patch mode, so the
server's citation gate carries the 'release_year=YYYY: ...' line into the
robot's notes for audit and never overwrites non-blank fields.

Usage:
    python retry_release_years.py --company-id 307                 # report only
    python retry_release_years.py --company-id 307 --apply --ids 5273 5266
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from release_year_lookup import citation_line, lookup_release_year

# Evidence phrases that signal a real launch/announcement statement; anything
# else (family membership, datasheet issue dates, copyright years) slips past
# the lookup prompt often enough that it gets flagged for closer review.
_LAUNCH_WORDS = ("announc", "launch", "unveil", "introduc", "release", "debut",
                 "available", "deliver", "ship")


def _evidence_flag(evidence: str) -> str:
    low = evidence.lower()
    return "" if any(w in low for w in _LAUNCH_WORDS) else "NO-LAUNCH-WORD"


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry grounded release-year lookups")
    parser.add_argument("--company-id", type=int, required=True)
    parser.add_argument("--attempts", type=int, default=3,
                        help="lookup attempts per robot (lookup fail-opens, so retry)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ids", type=int, nargs="*",
                        help="robot ids to apply (required with --apply)")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = client.list_robots_for_company(args.company_id)
    targets = [
        r for r in robots
        if str(r.get("status") or "").lower() == "pending_review"
        and not r.get("release_year")
    ]
    skipped = [r for r in robots
               if str(r.get("status") or "").lower() != "pending_review"]
    if skipped:
        print(f"skipping {len(skipped)} non-pending robot(s): "
              + ", ".join(f"{r['id']}({r.get('status')})" for r in skipped))
    if not targets:
        print("nothing to do: no pending_review robots with blank release_year")
        return 0

    # list endpoint serializes company as a plain name string
    company_name = str(targets[0].get("company") or "").strip()
    if not company_name:
        print("ERROR: could not resolve company name from robot list", file=sys.stderr)
        return 1
    report_path = _RESEARCH_DIR / "staging" / "reports" / (
        f"release-year-retry-{args.company_id}.json")

    if not args.apply:
        hits: dict[int, dict[str, Any]] = {}
        for r in targets:
            rid = int(r["id"])
            name = str(r.get("name") or "")
            model = str(r.get("model_name") or "")
            hit = None
            for attempt in range(1, args.attempts + 1):
                hit = lookup_release_year(name, company_name, model_name=model)
                if hit:
                    break
                time.sleep(2 * attempt)
            if hit:
                flag = _evidence_flag(hit["evidence"])
                hits[rid] = hit
                print(f"  {rid} {name}: {hit['year']} [{hit['confidence']}]"
                      + (f" [{flag}]" if flag else ""))
                print(f"      {hit['evidence']}")
                print(f"      {hit['source_url']}")
            else:
                print(f"  {rid} {name}: no grounded year after {args.attempts} attempt(s)")

        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(
            {str(rid): {**hit, "robot_name": next(
                str(r.get("name") or "") for r in targets if int(r["id"]) == rid)}
             for rid, hit in hits.items()},
            indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nreport: {report_path}")
        print("dry run — review evidence, then re-run with --apply --ids <id...>")
        return 0

    # --apply: use the SAVED report the reviewer vetted. Re-running the lookups
    # here could return a different year/source than the one that was approved.
    if not args.ids:
        print("ERROR: --apply requires --ids with the vetted robot ids", file=sys.stderr)
        return 1
    if not report_path.is_file():
        print(f"ERROR: no report at {report_path} — run without --apply first",
              file=sys.stderr)
        return 1
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    hits = {int(rid): hit for rid, hit in saved.items()}
    age_h = (time.time() - report_path.stat().st_mtime) / 3600
    print(f"applying report {report_path.name} "
          f"(written {age_h:.1f}h ago, {len(hits)} hit(s))")

    by_id = {int(r["id"]): r for r in targets}
    ok = fail = 0
    for rid in args.ids:
        hit = hits.get(rid)
        robot = by_id.get(rid)
        if not hit or not robot:
            print(f"SKIP {rid}: no lookup hit / not a target", file=sys.stderr)
            fail += 1
            continue
        row = staging_dict_to_bulk_import_row({
            "name": robot.get("name") or "",
            "model_name": robot.get("model_name") or "",
            "company_name": company_name,
            "release_year": hit["year"],
            "research_notes": citation_line(hit),
        })
        row["id"] = rid
        try:
            result = client.bulk_import_robots(
                [row],
                update_existing=True,
                patch_existing=True,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            fail += 1
            continue
        if int(result.get("error_count") or 0):
            print(f"IMPORT FAIL {rid}: {result}", file=sys.stderr)
            fail += 1
        else:
            ok += 1
            print(f"  patched {rid}: release_year={hit['year']}")
    print(f"\napplied ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
