"""One-command, capped test of the subscription-CLI broker on a single company.

Prepared 2026-08-02 for Martti's explicit constraint: NO unattended overnight
runs against subscription quota. This script is the entire test — run it when
YOU decide, watch it live, and it physically cannot exceed --max-cli-calls
subscription calls (everything past the cap falls through to budget-guarded
Gemini, so the run still completes).

Usage (tomorrow):

    cd scripts/research
    python -u broker_company_test.py                     # defaults: company 1604, 25-call cap
    python -u broker_company_test.py --company-id 1604 --max-cli-calls 25

What to look for in the output:
  * `[llm_broker] claude_cli ok in Ns ... [k/25]` — each subscription call, counted
  * the end-of-run scorecard: subscription calls used vs Gemini fallbacks vs
    what the same run would have cost entirely on Gemini
  * then check the robots in To Review — the quality judgment is yours.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company-id", type=int, default=1604,
                    help="default 1604 = Shandong Kewei Robot (1 pending skeleton, real robot)")
    ap.add_argument("--max-cli-calls", type=int, default=25)
    ap.add_argument("--providers", default="claude_cli,gemini")
    args = ap.parse_args()

    # Env must be set BEFORE pipeline modules import spend_guard/llm_broker.
    os.environ["RESEARCH_LLM_PROVIDER"] = args.providers
    os.environ["LLM_CLI_MAX_CALLS"] = str(args.max_cli_calls)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    from load_env import load_research_env
    load_research_env(local=False)

    import llm_broker
    import spend_guard

    print(f"=== Broker company test — company {args.company_id} ===")
    print(f"provider chain : {llm_broker.provider_chain()}")
    print(f"CLI call cap   : {args.max_cli_calls}")
    gem_before = spend_guard.status()
    print(f"Gemini today   : {gem_before['calls']}/{gem_before['budget']} before run\n")

    from workflow_auto_research import auto_research_pipeline
    res = auto_research_pipeline(
        args.company_id,
        only_missing=True,
        apply_import=True,
        patch=True,
        created_by_id=1,
        grounded=True,
    )

    r = res.get("research") or {}
    imp = res.get("import") or {}
    gem_after = spend_guard.status()
    gemini_used = gem_after["calls"] - gem_before["calls"]

    print("\n=== SCORECARD ===")
    print(f"robots researched      : {r.get('robots_researched')}")
    print(f"imported (updated)     : {imp.get('updated_count')} | errors: {imp.get('error_count')}")
    print(f"auto-rejected non-robots: {len(r.get('auto_rejected_non_robots') or [])}")
    print(f"subscription CLI calls : {llm_broker._cli_calls_made} (cap {args.max_cli_calls})")
    print(f"Gemini calls (fallback + search-grounded): {gemini_used}")
    print(f"Gemini today total     : {gem_after['calls']}/{gem_after['budget']}")
    print("\nJudge quality in the admin queue: "
          f"https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id={args.company_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
