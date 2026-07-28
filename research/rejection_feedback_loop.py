"""Closed feedback loop over CRM-rejected robots.

    rejected (+ reason)  ->  diagnose  ->  TARGETED remedy  ->  re-verify  ->  resubmit
                                   |                                    |
                                   +-- terminal / exhausted ------------+--> escalate

The point is that it LEARNS: every attempt is appended to `Robot.auto_fix_attempts`
server-side, and `plan_remedies` reads that ledger back, so a remedy that already
returned NO_OP is never run again for that robot. Without the ledger the loop would
re-research the same hopeless robots nightly forever — which is the waste this whole
exercise exists to remove.

Terminal categories (`not_real`, `duplicate`) are never enriched: re-researching a
fabricated model just recreates it. They are escalated for human deletion/merge.

  python -u rejection_feedback_loop.py --dry-run
  python -u rejection_feedback_loop.py --company-id 107 --apply
  python -u rejection_feedback_loop.py --max-robots 25 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from remedies import (  # noqa: E402
    FIXED,
    RemedyContext,
    categories_for_robot,
    flags_from_categories,
    is_terminal,
    plan_remedies,
)
from slug_utils import resolve_company_slug  # noqa: E402

REPORT_PATH = _RESEARCH_DIR / "staging" / "reports" / "rejection-loop-report.json"

# Ledger states (mirror robots.models.AutoFixStatus)
QUEUED, IN_PROGRESS, RESUBMITTED, ESCALATED = "queued", "in_progress", "resubmitted", "escalated"


def _p(*a: Any) -> None:
    try:
        print(*a, flush=True)
    except UnicodeEncodeError:
        print(" ".join(str(x) for x in a).encode("ascii", "replace").decode(), flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ledger_entry(action: str, outcome: str, detail: str = "", **extra: Any) -> dict[str, Any]:
    return {"at": _now(), "action": action, "outcome": outcome, "detail": detail[:500], **extra}


def _get_retry(client: ResearchApiClient, path: str, params: dict[str, Any], *, tries: int = 5) -> dict[str, Any]:
    """GET with backoff. Prod drops large serialized pages mid-transfer
    (ChunkedEncodingError / 5xx), and an unattended loop must not die on one."""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            return client._get(path, params=params)
        except Exception as exc:  # noqa: BLE001
            last = exc
            wait = 2 ** attempt
            _p(f"  intake retry {attempt + 1}/{tries} ({type(exc).__name__}) — sleeping {wait}s")
            time.sleep(wait)
    raise last  # type: ignore[misc]


def write_back(
    client: ResearchApiClient,
    robot_id: int,
    *,
    attempts: list[dict[str, Any]],
    auto_fix_status: str,
    resubmit: bool,
    dry_run: bool,
) -> bool:
    """Persist the ledger (and optionally resubmit) — the LEARNING step.

    Without this the loop is amnesiac: `plan_remedies` reads `auto_fix_attempts`
    to decide what NOT to retry, so an unwritten ledger means every hopeless
    remedy is attempted again on the next run.
    """
    payload: dict[str, Any] = {
        "auto_fix_attempts": attempts,
        "auto_fix_status": auto_fix_status,
    }
    if resubmit:
        payload["status"] = "pending_review"
    if dry_run:
        return True
    try:
        client._patch(f"robots/robots/{robot_id}/", payload)
    except Exception as exc:  # noqa: BLE001
        _p(f"      ledger write FAILED: {type(exc).__name__}: {exc}")
        return False
    # Confirm it landed — auto_fix_attempts is the loop's memory; a silent drop
    # would quietly restore the infinite-retry behaviour.
    try:
        fresh = client._get(f"robots/robots/{robot_id}/")
        if len(fresh.get("auto_fix_attempts") or []) != len(attempts):
            _p("      ledger write did NOT persist (attempt count mismatch)")
            return False
    except Exception:
        pass
    return True


def process_robot(robot: dict[str, Any], ctx: RemedyContext, *, dry_run: bool) -> dict[str, Any]:
    rid = int(robot.get("id") or 0)
    name = str(robot.get("name") or "")
    attempts = list(robot.get("auto_fix_attempts") or [])
    categories, source = categories_for_robot(robot)
    row: dict[str, Any] = {
        "id": rid, "name": name, "categories": categories, "category_source": source,
        "results": [], "final_status": None,
    }
    _p(f"[{rid}] {name[:44]}")
    _p(f"      categories={categories} ({source})  prior_attempts={len(attempts)}")

    # --- terminal: never enrich, hand to a human for deletion/merge ---
    if is_terminal(categories):
        attempts.append(_ledger_entry("triage", "terminal",
                                      f"terminal categories {categories} — must not be enriched",
                                      categories=categories))
        ok = write_back(ctx.client, rid, attempts=attempts, auto_fix_status=ESCALATED,
                        resubmit=False, dry_run=dry_run)
        row["final_status"] = ESCALATED
        row["ledger_written"] = ok
        _p(f"      TERMINAL -> escalated for human deletion/merge (ledger_written={ok})")
        return row

    plan = plan_remedies(
        quality_flags=robot.get("quality_flags"),
        rejection_categories=categories,
        attempts=attempts,
    )
    if not plan:
        attempts.append(_ledger_entry("triage", "exhausted",
                                      "no remedy applies, or every applicable remedy is ledger-blocked"))
        ok = write_back(ctx.client, rid, attempts=attempts, auto_fix_status=ESCALATED,
                        resubmit=False, dry_run=dry_run)
        row["final_status"] = ESCALATED
        row["ledger_written"] = ok
        _p(f"      NO PLAN -> escalated (ledger_written={ok})")
        return row

    # The reviewer's stated objection is what must be cleared before this robot goes
    # back in the queue. Fixing some unrelated flag and resubmitting sends it back
    # with the original complaint intact — the reviewer rejects it again and the loop
    # becomes reject/resubmit ping-pong. So: run the reason's own remedies FIRST, and
    # gate resubmission on one of THEM succeeding. Other flags are still repaired
    # opportunistically, they just don't earn a resubmit on their own.
    reason_flags = set(flags_from_categories(categories))
    if reason_flags:
        plan.sort(key=lambda item: item[0] not in reason_flags)
    _p(f"      plan={[f for f, _ in plan]}  reason_flags={sorted(reason_flags) or '-'}")

    changed = False
    reason_cleared = False
    for flag, remedy in plan:
        try:
            res = remedy(robot, ctx)
        except Exception as exc:  # noqa: BLE001
            attempts.append(_ledger_entry(flag, "failed", f"{type(exc).__name__}: {exc}"))
            _p(f"      - {flag:26} EXCEPTION {exc}")
            continue
        attempts.append(res.to_attempt())
        row["results"].append(res.to_attempt())
        _p(f"      - {flag:26} {res.outcome:8} {','.join(res.changed_fields)} {res.detail[:60]}")
        if res.outcome == FIXED and res.changed_fields:
            changed = True
            if flag in reason_flags:
                reason_cleared = True
            break  # re-run QA before attempting the next flag

    # Resubmission ALWAYS requires having cleared the reviewer's own objection.
    # When the reason maps to no remedy (`other`, or an unclassifiable free-text
    # reason) we do not know what they wanted, so an opportunistic fix to some
    # unrelated flag is not evidence the complaint was addressed — resubmitting on
    # that basis is how the loop turns into reject/resubmit ping-pong. Measured on
    # the first full VM run: 3 robots all classified `other`, 2 were resubmitted off
    # unrelated fixes with the original objection untouched. Escalate instead: if we
    # cannot tell what the reviewer meant, a human should look, not the loop.
    # Opportunistic fixes are still applied and still recorded in the ledger.
    resubmit = reason_cleared
    row["reason_cleared"] = reason_cleared
    if changed and not resubmit:
        if reason_flags:
            _p("      fixed an unrelated flag but NOT the rejection reason -> escalating, not resubmitting")
        else:
            _p("      fixed something, but the rejection reason has no remedy "
               "(unclassifiable) -> escalating for a human, not resubmitting")
    final = RESUBMITTED if resubmit else ESCALATED
    changed = resubmit
    ok = write_back(ctx.client, rid, attempts=attempts, auto_fix_status=final,
                    resubmit=changed, dry_run=dry_run)
    row["final_status"] = final
    row["ledger_written"] = ok
    _p(f"      -> {final} (resubmit={changed}, ledger_written={ok})")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="Closed rejection feedback loop")
    ap.add_argument("--company-id", type=int, default=0, help="Limit to one company")
    ap.add_argument("--robot-ids", default="", help="Comma-separated robot IDs")
    ap.add_argument("--max-robots", type=int, default=10)
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry-run)")
    ap.add_argument("--include-unqueued", action="store_true",
                    help="Also process rejected robots whose auto_fix_status is not 'queued' "
                         "(needed for the legacy backlog, which predates the field)")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    dry_run = not args.apply

    client = ResearchApiClient()
    _p(f"=== Rejection feedback loop ({'APPLY' if args.apply else 'DRY-RUN'}) ===")

    # Intake. Explicit ids are fetched directly — filtering them out of a paginated
    # scan silently returns nothing when the id sits beyond the fetched pages.
    if args.robot_ids.strip():
        robots = []
        for rid in [x.strip() for x in args.robot_ids.split(",") if x.strip().isdigit()]:
            try:
                robots.append(client._get(f"robots/robots/{rid}/"))
            except Exception as exc:  # noqa: BLE001
                _p(f"  skip {rid}: {type(exc).__name__}: {exc}")
    elif args.company_id:
        robots = [r for r in client.list_robots_for_company(args.company_id)
                  if str(r.get("status") or "").lower() == "rejected"]
    else:
        robots, page = [], 1
        # Stop paginating once we have enough to fill the cap — the rejected backlog
        # is 545 rows and each page is heavy to serialize.
        while page <= 12 and len(robots) < max(args.max_robots * 3, 50):
            data = _get_retry(client, "robots/robots/",
                              {"status": "rejected", "page": page, "page_size": 25})
            robots.extend(data.get("results") or [])
            if not data.get("next"):
                break
            page += 1
    if not args.include_unqueued:
        robots = [r for r in robots if str(r.get("auto_fix_status") or "") in (QUEUED, "", "none")]
    # Never re-touch something already handed to a human.
    robots = [r for r in robots if str(r.get("auto_fix_status") or "") != ESCALATED]
    robots.sort(key=lambda r: (r.get("reviewed_at") or "", r.get("id") or 0))
    _p(f"rejected robots to process: {len(robots)} (cap {args.max_robots})\n")

    rows: list[dict[str, Any]] = []
    outcomes: Counter = Counter()
    ctx_cache: dict[int, RemedyContext] = {}
    for robot in robots[: args.max_robots]:
        cref = robot.get("company_ref") if isinstance(robot.get("company_ref"), dict) else {}
        cid = cref.get("id") or robot.get("company_id")
        if cid and cid not in ctx_cache:
            try:
                co = client.get_company(cid)
            except Exception:
                co = {}
            ctx_cache[cid] = RemedyContext(
                company_id=int(cid),
                company_name=str(co.get("name") or ""),
                company_slug=resolve_company_slug(str(co.get("name") or ""), co.get("slug")),
                company_website=str(co.get("website") or "").strip(),
                client=client,
                dry_run=dry_run,
            )
        ctx = ctx_cache.get(cid) if cid else RemedyContext(company_id=0, client=client, dry_run=dry_run)
        try:
            row = process_robot(robot, ctx, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            _p(f"      ROBOT FAILED: {exc}\n{traceback.format_exc()[-300:]}")
            row = {"id": robot.get("id"), "error": str(exc), "final_status": "error"}
        rows.append(row)
        outcomes[row.get("final_status") or "error"] += 1
        time.sleep(0.2)

    _p("\n=== SUMMARY ===")
    for k, v in outcomes.most_common():
        _p(f"  {k:12} {v}")
    ledger_ok = sum(1 for r in rows if r.get("ledger_written"))
    _p(f"  ledger written: {ledger_ok}/{len(rows)}")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    _p(f"report -> {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
