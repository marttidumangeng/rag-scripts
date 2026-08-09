"""Dry-run the Tier-1 remedy library against one company's To Review queue.

Researches for real but WRITES NOTHING (RemedyContext.dry_run=True), so you can
see exactly which robots the loop would fix, which would come back NO_OP (the
pipeline genuinely cannot do better), and which would fail.

  python -u remedy_dryrun.py --company-id 1476 --max-robots 5
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from remedies import (  # noqa: E402
    MEDIA_FLAGS,
    WEBSITE_FREE_FLAGS,
    RemedyContext,
    flags_from_gaps,
    plan_remedies,
)
from slug_utils import resolve_company_slug  # noqa: E402
from triage_content_queue import robot_gaps  # noqa: E402


def _p(*a):
    try:
        print(*a, flush=True)
    except UnicodeEncodeError:
        print(" ".join(str(x) for x in a).encode("ascii", "replace").decode(), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-id", type=int, default=0)
    ap.add_argument(
        "--queue", action="store_true",
        help="Cross-queue mode: scan pending_review for robots with remediable "
             "quality flags (companies with websites only) and work the busiest "
             "companies first. Replaces --company-id.",
    )
    ap.add_argument("--max-queue-companies", type=int, default=6)
    ap.add_argument("--scan-pages", type=int, default=40,
                    help="Cap the pending-queue scan (50 robots/page); keeps local tests fast")
    ap.add_argument(
        "--workers", type=int, default=1,
        help="Companies to remediate in parallel in --queue mode (default 1 = serial). "
             "Each worker gets its own API client; Playwright rendering is safe under "
             "concurrency (web_extract._PLAYWRIGHT_LOCK serializes just the render calls). "
             "Keep modest (4-6) to avoid overloading prod / API rate limits.",
    )
    ap.add_argument("--max-robots", type=int, default=5)
    ap.add_argument("--robot-ids", default="", help="Comma-separated robot IDs to target")
    ap.add_argument("--only-gapped", action="store_true", help="Skip robots with no plan")
    ap.add_argument("--status", default="pending_review")
    ap.add_argument("--apply", action="store_true", help="ACTUALLY WRITE (default: dry-run)")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()

    if args.queue:
        return run_queue_mode(client, args)
    if not args.company_id:
        _p("either --company-id or --queue is required")
        return 2
    co = client.get_company(args.company_id)
    name = str(co.get("name") or "")
    slug = resolve_company_slug(name, co.get("slug"))
    website = str(co.get("website") or "").strip()
    country = str((co.get("country") or {}).get("code") or "") if co.get("country") else ""

    _p(f"=== Remedy {'APPLY' if args.apply else 'DRY-RUN'} — {name} (id={args.company_id}) ===")
    _p(f"website={website or '(none)'} slug={slug}")

    robots = [
        r for r in client.list_robots_for_company(args.company_id)
        if str(r.get("status") or "").lower() == args.status
    ]
    robots.sort(key=lambda r: (r.get("created_at") or "", r.get("id") or 0))
    if args.robot_ids.strip():
        want = {int(x) for x in args.robot_ids.split(",") if x.strip().isdigit()}
        robots = [r for r in robots if int(r.get("id") or 0) in want]
    if args.only_gapped:
        robots = [r for r in robots if robot_gaps(r)]
    _p(f"{args.status} robots: {len(robots)} (processing {min(len(robots), args.max_robots)})\n")

    ctx = RemedyContext(
        company_id=args.company_id, company_name=name, company_slug=slug,
        company_website=website, country_code=country, client=client,
        dry_run=not args.apply,
    )

    outcomes: Counter = Counter()
    per_flag: Counter = Counter()
    rows = []
    for robot in robots[:args.max_robots]:
        rid = robot.get("id")
        # Prefer the server's computed quality_flags (rich); fall back to the coarse
        # client-side gap check only when the robot was never audited.
        qflags = robot.get("quality_flags")
        if qflags:
            flags = qflags
            src = "quality_flags"
        else:
            gaps = robot_gaps(robot)
            flags = flags_from_gaps(gaps)
            src = "robot_gaps(fallback)"
        plan = plan_remedies(
            quality_flags=flags,
            rejection_categories=robot.get("rejection_categories") or [],
            attempts=robot.get("auto_fix_attempts") or [],
        )
        _keys = [f.get("flag") if isinstance(f, dict) else f for f in (flags or [])]
        _p(f"[{rid}] {str(robot.get('name'))[:44]}")
        _p(f"      [{src}] flags={_keys or '-'} -> plan={[f for f, _ in plan] or '-'}")
        if not plan:
            outcomes["no_plan"] += 1
            rows.append({"id": rid, "flags": flags, "results": [], "note": "no plan"})
            continue
        results = []
        for flag, remedy in plan:
            res = remedy(robot, ctx)
            outcomes[res.outcome] += 1
            per_flag[f"{flag}:{res.outcome}"] += 1
            _p(f"      - {flag:24} {res.outcome:8} {','.join(res.changed_fields) or ''} {res.detail[:70]}")
            results.append(res.to_attempt())
            if res.changed and flag not in MEDIA_FLAGS:
                break  # a real change -> re-run QA before trying the next flag
                       # (media flags are noisy on re-fetch, must not eat the pass alone)
        rows.append({"id": rid, "name": robot.get("name"), "flags": flags, "results": results})

    _p("\n=== SUMMARY ===")
    for k, v in outcomes.most_common():
        _p(f"  {k:10} {v}")
    if per_flag:
        _p("  --- per flag ---")
        for k, v in per_flag.most_common():
            _p(f"  {k:34} {v}")

    out = _RESEARCH_DIR / "staging" / "reports" / f"remedy-dryrun-{args.company_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    _p(f"\nreport -> {out}")
    return 0


def run_queue_mode(client: ResearchApiClient, args) -> int:
    """Cross-queue flag remediation: the stage the nightly cycle was missing.

    Enrichment's gap-fill sees only the coarse `robot_gaps`; the flag-driven
    remedies (vision photos, tags, family, purpose...) previously ran ONLY on
    rejected robots. Pending robots with fixable warnings therefore sat untouched
    — which is exactly what Martti found browsing To Review (2026-07-29).

    Selection: scan pending_review, keep robots whose flags produce a non-empty
    remedy plan (ledger-aware via their server-side `auto_fix_attempts`), skip
    companies without websites (remedies cannot research them), work the busiest
    companies first. On --apply, every attempt is appended to the robot's
    `auto_fix_attempts` so the next cycle never retries a NO_OP.
    """
    import time as _time

    _p(f"=== Queue remediation ({'APPLY' if args.apply else 'DRY-RUN'}) ===")
    by_company: dict[int, dict] = {}
    # Draft-first pipeline (2026-08-05): drafts are where discovery imports now
    # live until promoted, so remediation must work BOTH lanes. Drafts scan
    # first — completing them is what feeds the promotion gate.
    scan_batches: list[dict] = []
    for _status in ("draft", "pending_review"):
        page = 1
        while page <= args.scan_pages:
            for attempt in range(4):
                try:
                    data = client._get("robots/robots/", params={
                        "status": _status, "page": page, "page_size": 50})
                    break
                except Exception:
                    _time.sleep(2 ** attempt)
            else:
                break
            scan_batches.append(data)
            if not data.get("next"):
                break
            page += 1
    for data in scan_batches:
        for r in data.get("results") or []:
            cref = r.get("company_ref") if isinstance(r.get("company_ref"), dict) else {}
            cid, website = cref.get("id"), (cref.get("website") or "").strip()
            if not cid:
                continue
            plan = plan_remedies(
                quality_flags=r.get("quality_flags"),
                rejection_categories=r.get("rejection_categories") or [],
                attempts=r.get("auto_fix_attempts") or [],
            )
            if not plan:
                continue
            # Website-less companies used to be dropped here wholesale, because
            # every re-research remedy SKIPs without an OEM site. Category and
            # country need no site, so dropping the company left those two flags
            # permanently unfixable on manufacturers whose website cannot be
            # resolved. Keep the robot, but only for the remedies that can run.
            if not website:
                plan = [(f, fn) for f, fn in plan if f in WEBSITE_FREE_FLAGS]
                if not plan:
                    continue
            country = cref.get("country")
            e = by_company.setdefault(int(cid), {
                "name": cref.get("name") or "", "slug": cref.get("slug") or "",
                "website": website,
                "country": (country.get("code") or "") if isinstance(country, dict) else "",
                "robots": [],
            })
            e["robots"].append(r)

    # Companies someone else has locked for exclusive manual work (see
    # company_locks.py) — a stale-snapshot write from this loop is exactly
    # what clobbered a manual sweep's changes on AgileX (2026-08-01).
    from company_locks import load_locked_company_ids
    locked_ids = load_locked_company_ids()
    if locked_ids:
        _p(f"  locked companies (skipping): {sorted(locked_ids)}")

    ranked = sorted(
        ((cid, e) for cid, e in by_company.items() if cid not in locked_ids),
        key=lambda kv: -len(kv[1]["robots"]),
    )
    dispatch = ranked[: args.max_queue_companies]
    workers = max(1, args.workers)
    if workers > 8:
        _p(f"  NOTE: --workers {workers} is high; keep it modest to avoid overloading prod.")
    _p(f"companies with remediable pending robots: {len(ranked)} "
       f"(working top {len(dispatch)} with {workers} worker(s), {args.max_robots} robots each)")

    outcomes: Counter = Counter()
    per_flag: Counter = Counter()
    if workers == 1:
        for cid, e in dispatch:
            result = _process_company_remedy(cid, e, args)
            outcomes.update(result["outcomes"])
            per_flag.update(result["per_flag"])
    else:
        # NOT a `with ThreadPoolExecutor(...) as executor:` block deliberately:
        # its __exit__ always calls shutdown(wait=True) with cancel_futures=False,
        # even when a KeyboardInterrupt is what's unwinding the block — meaning the
        # 45m `timeout --signal=INT` wrapper's interrupt would still block for
        # every ALREADY-SUBMITTED company, not just the `workers` ones actually
        # running. Measured live 2026-08-01: 18 companies queued, 6 workers, timeout
        # fired on schedule at 45m but the process didn't actually exit for ~4
        # hours — it was draining the 12 companies that hadn't even started yet.
        executor = ThreadPoolExecutor(max_workers=workers)
        futures = {
            executor.submit(_process_company_remedy, cid, e, args): cid
            for cid, e in dispatch
        }
        try:
            for fut in as_completed(futures):
                result = fut.result()
                outcomes.update(result["outcomes"])
                per_flag.update(result["per_flag"])
            executor.shutdown(wait=True)
        except KeyboardInterrupt:
            not_started = sum(1 for f in futures if not f.done() and not f.running())
            _p(f"\n  interrupted — dropping {not_started} not-yet-started companies, "
               f"waiting only for the {workers} already in flight to finish")
            executor.shutdown(wait=True, cancel_futures=True)
            raise

    _p("\n=== QUEUE SUMMARY ===")
    for k, v in outcomes.most_common():
        _p(f"  {k:10} {v}")
    for k, v in per_flag.most_common(12):
        _p(f"  {k:34} {v}")
    return 0


def _process_company_remedy(cid: int, e: dict, args) -> dict:
    """Remediate one company's queue with its OWN API client.

    Fully isolated per call (own requests.Session, own RemedyContext), so it is
    safe to run concurrently across companies via --workers > 1. Robots are
    partitioned by company up front (built in run_queue_mode's scan), so no two
    workers ever touch the same robot — the only cross-worker shared resource
    is the Playwright render path, which serializes itself internally
    (web_extract._PLAYWRIGHT_LOCK).
    """
    from api_client import ResearchApiClient

    client = ResearchApiClient()
    outcomes: Counter = Counter()
    per_flag: Counter = Counter()
    _p(f"\n## {cid} {e['name'][:40]} — {len(e['robots'])} remediable")
    ctx = RemedyContext(
        company_id=cid, company_name=e["name"],
        company_slug=resolve_company_slug(e["name"], e["slug"]),
        company_website=e["website"],
        # Without this the country remedy web-resolves a value the Company row
        # already holds — once per company, but for nothing.
        country_code=e.get("country") or "",
        client=client, dry_run=not args.apply,
    )
    for robot in e["robots"][: args.max_robots]:
        rid = robot.get("id")
        plan = plan_remedies(
            quality_flags=robot.get("quality_flags"),
            rejection_categories=robot.get("rejection_categories") or [],
            attempts=robot.get("auto_fix_attempts") or [],
        )
        if not e["website"]:
            plan = [(f, fn) for f, fn in plan if f in WEBSITE_FREE_FLAGS]
        _p(f"  [{rid}] {str(robot.get('name'))[:38]} plan={[f for f, _ in plan]}")
        attempts = list(robot.get("auto_fix_attempts") or [])
        for flag, remedy in plan:
            res = remedy(robot, ctx)
            outcomes[res.outcome] += 1
            per_flag[f"{flag}:{res.outcome}"] += 1
            attempts.append(res.to_attempt())
            _p(f"      - {flag:24} {res.outcome:8} {','.join(res.changed_fields) or ''} {res.detail[:60]}")
            if res.changed and flag not in MEDIA_FLAGS:
                break  # re-audit runs server-side on import; next cycle plans afresh
                       # (media flags are noisy on re-fetch, must not eat the pass alone)
        if args.apply and len(attempts) > len(robot.get("auto_fix_attempts") or []):
            try:
                client._patch(f"robots/robots/{rid}/", {"auto_fix_attempts": attempts})
            except Exception as exc:  # noqa: BLE001
                _p(f"      !! ledger write failed: {type(exc).__name__}")
    return {"cid": cid, "outcomes": outcomes, "per_flag": per_flag}


if __name__ == "__main__":
    raise SystemExit(main())
