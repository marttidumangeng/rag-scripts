#!/usr/bin/env python3
"""
Backfill images for all robots that have no image.

How it works:
  1. Fetch all robots with no image from the API (uses ?no_image=true filter)
  2. Group them by company
  3. For each company run auto_research_pipeline (research + optional import)

Usage (dry run — research only, no import):
  python backfill_robot_images.py

Usage (apply — research + patch import to prod):
  python backfill_robot_images.py --apply

Options:
  --apply           Push researched data to API (default: dry-run)
  --playwright      Use headless browser for JS-heavy sites
  --stealth         Bot-detection avoidance: curl_cffi Chrome TLS impersonation
                    (Tier 1) with stealth-Playwright fallback on 403/JS-shell
                    (Tier 2). Use for sites behind Cloudflare/PerimeterX.
                    Requires: pip install curl_cffi playwright-stealth
  --limit N         Stop after processing N companies
  --company-id ID   Process only this company ID
  --status STATUS   Robot status on import (default: pending_review)
  --created-by-id N User ID for created_by field (or RESEARCH_CREATED_BY_ID env var)
  --delay N         Seconds to wait between companies (default: 2)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

import sys as _sys; load_research_env(local="--local" in _sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from workflow_auto_research import auto_research_pipeline


def _print(msg: str) -> None:
    print(msg, flush=True)


def fetch_companies_missing_images(client: ResearchApiClient) -> dict[int, dict]:
    """
    Returns {company_id: company_info} for all companies that have
    at least one robot with no image.
    """
    _print("Fetching robots with missing images...")
    robots = client.list_robots_missing_image()
    _print(f"  Found {len(robots)} robots with no image")

    companies: dict[int, dict] = {}
    for robot in robots:
        cref = robot.get("company_ref")
        if not cref:
            continue
        if isinstance(cref, dict):
            cid = cref.get("id")
            cname = cref.get("name", "")
            cslug = cref.get("slug", "")
        else:
            cid = cref
            cname = ""
            cslug = ""
        if cid and cid not in companies:
            companies[cid] = {"id": cid, "name": cname, "slug": cslug}

    _print(f"  Across {len(companies)} companies\n")
    return companies


def run(args: argparse.Namespace) -> int:
    client = ResearchApiClient()
    created_by_id = resolve_created_by_id(args.created_by_id)

    if args.company_id:
        company = client.get_company(args.company_id)
        companies = {args.company_id: company}
    else:
        companies = fetch_companies_missing_images(client)

    if not companies:
        _print("No companies with missing-image robots found. All done.")
        return 0

    total = len(companies)
    ok_count = 0
    fail_count = 0
    skipped_count = 0

    for idx, (company_id, company_info) in enumerate(companies.items(), 1):
        name = company_info.get("name") or company_info.get("slug") or str(company_id)
        _print(f"[{idx}/{total}] Company: {name} (id={company_id})")

        try:
            import signal

            def _timeout_handler(signum, frame):
                raise TimeoutError(f"Company {company_id} exceeded per-company timeout")

            # Per-company hard timeout (Windows doesn't support SIGALRM — skip there)
            use_signal_timeout = hasattr(signal, "SIGALRM")
            if use_signal_timeout:
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(args.company_timeout)

            result = auto_research_pipeline(
                company_id,
                client=client,
                only_missing=False,  # research ALL robots, not just those in missing-data queue
                use_playwright=args.playwright or None,
                use_stealth=args.stealth or None,
                apply_import=args.apply,
                created_by_id=created_by_id,
                patch=True,
                status=args.status,
            )

            if use_signal_timeout:
                signal.alarm(0)
        except Exception as exc:
            _print(f"  ERROR: {exc}")
            fail_count += 1
            if args.delay:
                time.sleep(args.delay)
            continue

        researched = result.get("research", {}).get("robots_researched", 0)
        errors = result.get("research", {}).get("errors", [])
        imp = result.get("import") or {}

        if researched == 0:
            _print(f"  Skipped — no robots found to research")
            skipped_count += 1
        else:
            _print(f"  Researched: {researched} robot(s)")
            if imp:
                _print(f"  Imported: created={imp.get('created_count',0)} updated={imp.get('updated_count',0)} errors={imp.get('error_count',0)}")
            if errors:
                _print(f"  Research errors: {errors}")
            ok_count += 1

        if args.limit and (ok_count + skipped_count) >= args.limit:
            _print(f"\nReached --limit {args.limit}, stopping.")
            break

        if args.delay and idx < total:
            time.sleep(args.delay)

    _print(f"\n{'='*60}")
    _print(f"Done. Processed={ok_count} skipped={skipped_count} errors={fail_count}")
    if not args.apply:
        _print("DRY RUN — rerun with --apply to push to prod")
    return 0 if fail_count == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Backfill images for robots missing an image")
    p.add_argument("--apply", action="store_true", help="Push results to API (default: dry-run)")
    p.add_argument("--playwright", action="store_true", help="Use headless browser for JS-heavy sites")
    p.add_argument("--stealth", action="store_true",
                   help="Bot-detection avoidance: curl_cffi Chrome impersonation + stealth-Playwright "
                        "fallback (for Cloudflare/PerimeterX-protected sites)")
    p.add_argument("--limit", type=int, default=None, help="Max number of companies to process")
    p.add_argument("--company-id", type=int, default=None, help="Process only this company ID")
    p.add_argument("--status", default="pending_review", help="Robot status on import")
    p.add_argument("--created-by-id", type=int, default=None)
    p.add_argument("--delay", type=float, default=2.0, help="Seconds between companies (default: 2)")
    p.add_argument("--company-timeout", type=int, default=120, help="Max seconds per company (default: 120, SIGALRM only — no effect on Windows)")
    p.add_argument("--local", action="store_true", help="Use *_LOCAL env vars to target local dev server")
    return p


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
