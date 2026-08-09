"""Promotion gate: draft -> pending_review, only for FINISHED robots.

THE PROBLEM THIS SOLVES (Martti, 2026-08-05): "The quality of robots in the
content queue is bad... or else we'll just constantly burn api tokens with
very little result." The pipeline was import-first-fix-later: discovery
dropped half-built rows straight into pending_review, so the Content Queue —
the human front door — showed every skeleton and every marginal extraction
while remediation slowly caught up.

Under the draft-first pipeline, discovery imports land as status='draft'
(invisible to the queue), enrichment/remediation complete them in the draft
lane, and THIS script is the only path into pending_review. A draft promotes
when BOTH gates pass:

  1. Required-set gate (free, client-side): none of the blocking gaps from
     triage_content_queue.robot_gaps — image, features, tags, url, specs,
     country, category, company — plus a non-empty description. ('no_videos'
     is deliberately NOT blocking: videos are enrichment polish, not a
     review-readiness requirement.)
  2. Verification gate (server-side Gemini, spends the SERVER key not the
     research ledger): batched ai-verify job; promote only robots whose
     stamped verification_confidence >= --min-score (default 70, the same
     threshold the exec moderation tools use for score-gated approval).

Drafts that fail gate 1 stay in the lane remediation already works. Drafts
that fail gate 2 repeatedly (>= --max-verify-attempts, tracked in
staging/state/promotion_attempts.json) are reported as stuck — human
decides; the gate never auto-rejects.

Only robots created by the research pipeline (created_by == --created-by-id)
are considered: human drafts (e.g. zh translations in progress) must never
be auto-promoted.

Usage:
  python -u promote_drafts.py                # dry-run report
  python -u promote_drafts.py --apply
  python -u promote_drafts.py --apply --max-verify 40
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_client import ResearchApiClient
from triage_content_queue import robot_gaps

_RESEARCH_DIR = Path(__file__).resolve().parent
ATTEMPTS_PATH = _RESEARCH_DIR / "staging" / "state" / "promotion_attempts.json"

# Gaps that block promotion. Everything robot_gaps() can emit EXCEPT
# no_videos — see module docstring.
BLOCKING_GAPS = {
    "no_image", "no_features", "no_tags", "no_url",
    "no_specs", "no_country", "no_category", "no_company",
}

VERIFY_POLL_SECONDS = 15
VERIFY_TIMEOUT_SECONDS = 1200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_attempts() -> dict[str, Any]:
    try:
        return json.loads(ATTEMPTS_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — missing/corrupt = fresh ledger
        return {}


def _save_attempts(data: dict[str, Any]) -> None:
    ATTEMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ATTEMPTS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def list_research_drafts(client: ResearchApiClient, *, created_by_id: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        last_exc: Exception | None = None
        data = None
        for attempt in range(4):
            try:
                data = client._get(
                    "robots/robots/",
                    params={"status": "draft", "page": page, "page_size": 50},
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(2 ** attempt)
        if data is None:
            raise last_exc  # type: ignore[misc]
        for r in data.get("results") or []:
            if r.get("created_by") == created_by_id:
                results.append(r)
        if not data.get("next"):
            break
        page += 1
        time.sleep(0.1)
    return results


def blocking_gaps_of(robot: dict[str, Any]) -> list[str]:
    gaps = [g for g in robot_gaps(robot) if g in BLOCKING_GAPS]
    if not str(robot.get("description") or "").strip():
        gaps.append("no_description")
    return gaps


def run_verify_job(client: ResearchApiClient, robot_ids: list[int]) -> dict[str, Any]:
    """Start one batched verify job and wait for it. Returns the final job dict."""
    job = client.ai_verify_start(robot_ids)
    job_id = job.get("job_id")
    if not job_id:
        return job
    t0 = time.time()
    while time.time() - t0 < VERIFY_TIMEOUT_SECONDS:
        job = client.ai_verify_status(job_id)
        if job.get("finished_at") or job.get("status") in ("succeeded", "failed", "error", "done"):
            break
        time.sleep(VERIFY_POLL_SECONDS)
    return job


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--apply", action="store_true", help="ACTUALLY WRITE (default: dry-run)")
    ap.add_argument("--min-score", type=int, default=70)
    ap.add_argument("--max-verify", type=int, default=40,
                    help="Max drafts sent to (paid) AI verification per run")
    ap.add_argument("--max-verify-attempts", type=int, default=3,
                    help="Verify failures before a draft is reported as stuck")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    drafts = list_research_drafts(client, created_by_id=args.created_by_id)
    print(f"research drafts: {len(drafts)}")

    attempts = _load_attempts()
    incomplete: list[tuple[int, list[str]]] = []
    stuck: list[int] = []
    candidates: list[dict[str, Any]] = []
    for r in drafts:
        rid = int(r["id"])
        gaps = blocking_gaps_of(r)
        if gaps:
            incomplete.append((rid, gaps))
            continue
        rec = attempts.get(str(rid)) or {}
        if rec.get("verify_failures", 0) >= args.max_verify_attempts:
            stuck.append(rid)
            continue
        candidates.append(r)

    print(f"incomplete (stay draft, remediation's job): {len(incomplete)}")
    print(f"complete, awaiting verification: {len(candidates)}")
    if stuck:
        print(f"STUCK (>= {args.max_verify_attempts} verify failures, needs a human): {stuck}")

    # Already-verified candidates skip the paid re-verify; fresh ones get one.
    to_promote: list[int] = []
    to_verify: list[int] = []
    for r in candidates:
        score = r.get("verification_confidence")
        # A stale checked_at with a NULL score means an edit invalidated the
        # score (Robot.save clears confidence, keeps the timestamp) — treat as
        # unscored, never as "checked". See verify_pending for the full note.
        checked = r.get("verification_checked_at") and score is not None
        if checked and isinstance(score, (int, float)):
            if score >= args.min_score:
                to_promote.append(int(r["id"]))
            else:
                to_verify.append(int(r["id"]))  # re-verify: remediation may have improved it
        else:
            to_verify.append(int(r["id"]))
    to_verify = to_verify[: args.max_verify]

    if not args.apply:
        print(f"[dry-run] would verify {len(to_verify)}: {to_verify}")
        print(f"[dry-run] would promote (already scored >= {args.min_score}): {to_promote}")
        return

    if to_verify:
        print(f"verifying {len(to_verify)} draft(s) server-side…")
        job = run_verify_job(client, to_verify)
        print(f"verify job: status={job.get('status')} verified={job.get('verified')} "
              f"skipped={job.get('skipped')} errors={job.get('errors')}")
        for rid in to_verify:
            try:
                r = client._get(f"robots/robots/{rid}/")
            except Exception as exc:  # noqa: BLE001
                print(f"  {rid}: re-read failed ({exc}); leaving draft")
                continue
            score = r.get("verification_confidence")
            if isinstance(score, (int, float)) and score >= args.min_score:
                to_promote.append(rid)
            else:
                rec = attempts.setdefault(str(rid), {})
                rec["verify_failures"] = rec.get("verify_failures", 0) + 1
                rec["last_score"] = score
                rec["at"] = _now()
                print(f"  {rid}: score={score} < {args.min_score} — stays draft "
                      f"(failure {rec['verify_failures']}/{args.max_verify_attempts})")
        _save_attempts(attempts)

    promoted = 0
    for rid in to_promote:
        try:
            client.set_robot_status(rid, "pending_review")
            promoted += 1
            attempts.pop(str(rid), None)
            print(f"  PROMOTED {rid} -> pending_review")
        except Exception as exc:  # noqa: BLE001
            print(f"  {rid}: promote failed ({exc})")
    _save_attempts(attempts)

    print(json.dumps({
        "drafts": len(drafts),
        "incomplete": len(incomplete),
        "verified_now": len(to_verify),
        "promoted": promoted,
        "stuck": stuck,
    }))


if __name__ == "__main__":
    main()
