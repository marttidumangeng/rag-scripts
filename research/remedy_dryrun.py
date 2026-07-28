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
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from remedies import RemedyContext, flags_from_gaps, plan_remedies  # noqa: E402
from slug_utils import resolve_company_slug  # noqa: E402
from triage_content_queue import robot_gaps  # noqa: E402


def _p(*a):
    try:
        print(*a, flush=True)
    except UnicodeEncodeError:
        print(" ".join(str(x) for x in a).encode("ascii", "replace").decode(), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-id", type=int, required=True)
    ap.add_argument("--max-robots", type=int, default=5)
    ap.add_argument("--robot-ids", default="", help="Comma-separated robot IDs to target")
    ap.add_argument("--only-gapped", action="store_true", help="Skip robots with no plan")
    ap.add_argument("--status", default="pending_review")
    ap.add_argument("--apply", action="store_true", help="ACTUALLY WRITE (default: dry-run)")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
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
            if res.changed:
                break  # a real change -> re-run QA before trying the next flag
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


if __name__ == "__main__":
    raise SystemExit(main())
