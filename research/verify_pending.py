"""Per-cycle verification sweep: score UNSCORED robots already in To Review.

WHY (Martti, 2026-08-07): "Discovery and Enrichment already use the Gemini
API key right? …it should also be scoring it already like the AI Verify.
Doing AI verify alone takes so long, I don't think I can ask our admin to
use that." Reviewers should never have to run AI Verify by hand.

The promotion gate (promote_drafts.py) already scores every DRAFT before it
enters the queue — so new pipeline arrivals come pre-scored. But two paths
still produce unscored pending robots:
  * remediation/content PATCHes reset verification (score must reflect the
    text it was computed on), and
  * human/company submissions enter pending_review directly.

This sweep runs each enrichment cycle and sends a capped batch of unscored
pending robots through the same server-side ai-verify job the admin button
uses (spends the SERVER key). Scores land on the robot; the admin queue
shows them; the reviewer approves from the top.

Usage:
  python -u verify_pending.py            # dry-run: count + sample
  python -u verify_pending.py --apply --max-verify 40
"""
from __future__ import annotations

import argparse
import time

from api_client import ResearchApiClient

POLL_SECONDS = 20
JOB_TIMEOUT_SECONDS = 1500


def _has_error_flag(robot: dict) -> bool:
    return any(
        isinstance(f, dict) and f.get("severity") == "error"
        for f in (robot.get("quality_flags") or [])
    )


def unscored_pending_ids(client: ResearchApiClient) -> tuple[list[int], int]:
    """Return (verify-worthy ids, count skipped for error flags).

    A robot with an error-severity quality flag CANNOT be approved no matter
    what it scores — paying Gemini to confirm that is pure waste (Martti,
    2026-08-07: "Why would you spend on obviously failing robot items?").
    Those stay with remediation; once the flags clear, a later sweep scores
    them. Warn-only flags (few_photos, no video) don't block approval, so
    those robots ARE worth scoring.
    """
    ids: list[int] = []
    skipped_error = 0
    page = 1
    while True:
        last_exc: Exception | None = None
        data = None
        for attempt in range(4):
            try:
                data = client._get(
                    "robots/robots/",
                    params={"status": "pending_review", "page": page, "page_size": 50},
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(2 ** attempt)
        if data is None:
            raise last_exc  # type: ignore[misc]
        for r in data.get("results") or []:
            # "Needs a score" is confidence IS NULL, NOT checked_at IS NULL.
            # Robot.save() nulls verification_confidence when an
            # AI_VERIFICATION_INPUT_FIELD changes (name/url/description/
            # purpose/features/company) but LEAVES verification_checked_at at
            # its old timestamp. Selecting on checked_at therefore skipped
            # every robot whose score a remediation edit had invalidated —
            # 125 pending robots were stranded that way (found 2026-08-08):
            # unscored, unsweepable, and invisible to the approvable filter.
            if r.get("verification_confidence") is not None:
                continue
            if _has_error_flag(r):
                skipped_error += 1
                continue
            ids.append(int(r["id"]))
        if not data.get("next"):
            break
        page += 1
        time.sleep(0.1)
    return ids, skipped_error


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--apply", action="store_true", help="ACTUALLY VERIFY (default: dry-run)")
    ap.add_argument("--max-verify", type=int, default=40)
    args = ap.parse_args()

    client = ResearchApiClient()
    ids, skipped_error = unscored_pending_ids(client)
    print(f"unscored pending robots worth scoring: {len(ids)} "
          f"(+{skipped_error} skipped: error flags, remediation's job first)")
    batch = ids[: args.max_verify]
    if not batch:
        return
    if not args.apply:
        print(f"[dry-run] would verify {len(batch)}: {batch[:20]}{'…' if len(batch) > 20 else ''}")
        return

    # One server-side job per JOB_SIZE robots: a job's worker is a daemon
    # thread in one web pod, so smaller jobs bound what a pod recycle can lose.
    JOB_SIZE = 40
    for start in range(0, len(batch), JOB_SIZE):
        chunk = batch[start:start + JOB_SIZE]
        # Retry once on a stall. Measured 2026-08-07: 4 of 16 jobs in one run
        # were killed by pod recycles (deploys/autoscale). Leaving those to
        # "the next cycle" meant a quarter of the work needed a whole extra
        # sweep — and a re-verify of the SAME robots costs nothing extra
        # because verified robots drop out of the unscored scan.
        for attempt in range(2):
            stalled = _run_one_job(client, chunk)
            if not stalled:
                break
            if attempt == 0:
                print("  retrying this batch once (worker died with its pod)")


def _run_one_job(client: ResearchApiClient, chunk: list[int]) -> bool:
    """Start + poll one verify job. Returns True when it stalled (worker died)."""
    job = client.ai_verify_start(chunk)
    jid = job.get("job_id")
    print(f"verify job {str(jid)[:8]} started for {len(chunk)} robot(s)")
    t0 = time.time()
    last_progress, stall = 0, 0
    stalled = False
    while time.time() - t0 < JOB_TIMEOUT_SECONDS:
        time.sleep(POLL_SECONDS)
        job = client.ai_verify_status(jid)
        prog = (job.get("verified") or 0) + (job.get("skipped") or 0) + (job.get("errors") or 0)
        if job.get("finished_at"):
            break
        # A worker thread dies silently with its pod; without progress for
        # 10 minutes assume it's gone.
        if prog == last_progress:
            stall += 1
            if stall >= 600 // POLL_SECONDS:
                print("  job stalled (worker likely died with pod)")
                stalled = True
                break
        else:
            stall, last_progress = 0, prog
    print(f"verify job: status={job.get('status')} verified={job.get('verified')} "
          f"skipped={job.get('skipped')} errors={job.get('errors')}")
    return stalled


if __name__ == "__main__":
    main()
