#!/usr/bin/env python3
"""CLI for the RobotAIGeek research agent."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as `python scripts/research/cli.py` without installing the package.
_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

import sys as _sys; load_research_env(local="--local" in _sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from import_staging import import_staging  # noqa: E402
from workflow_backfill import (  # noqa: E402
    apply_company_patch,
    fetch_next_company,
    fetch_robots_missing_for_company,
    load_config,
    load_processed_ids,
    mark_processed,
    write_backfill_report,
)
from workflow_greenfield import (  # noqa: E402
    greenfield_dedupe_report,
    load_seed_companies,
)
from robot_auto_research import research_robots_for_company  # noqa: E402
from workflow_auto_research import auto_research_pipeline  # noqa: E402
from discover_robots import discover_robots_for_company  # noqa: E402
from validate_staging import validate_company, validate_robot  # noqa: E402


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))


def cmd_backfill_next_company(args: argparse.Namespace) -> int:
    country = args.country or None
    company = fetch_next_company(country_code=country)
    if not company:
        config = load_config()
        cc = country or config.get("country_code", "US")
        include_null = config.get("include_null_country", True)
        print(
            f"No companies with missing data found "
            f"(country_code={cc}, include_null_country={include_null})."
        )
        return 0
    _print_json({
        "instruction": (
            "Research missing fields. Write staging file to the path in _staging_file. "
            "Use _suggested_slug (from company name), not generic company-NN slugs."
        ),
        "company": company,
        "missing_fields_hint": [
            "description", "website", "country", "hq_address",
            "contact_info", "leaders_roles", "employee_count",
        ],
        "slug_note": (
            "Set slug to _suggested_slug in staging JSON when _has_generic_slug is true."
        ),
    })
    return 0


def cmd_backfill_robots(args: argparse.Namespace) -> int:
    if not args.company_id:
        print("--company-id is required", file=sys.stderr)
        return 1
    robots = fetch_robots_missing_for_company(args.company_id)
    _print_json({
        "instruction": "Research blank fields only; write one JSON per robot under staging/robots/{slug}/",
        "company_id": args.company_id,
        "robots_missing_data": robots,
        "count": len(robots),
    })
    return 0


def cmd_backfill_apply_company(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    result = apply_company_patch(path, dry_run=not args.apply)
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_validate(args: argparse.Namespace) -> int:
    exit_code = 0
    paths: list[Path] = []
    if args.file:
        paths.append(Path(args.file))
    if args.dir:
        paths.extend(sorted(Path(args.dir).glob("*.json")))

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "company_slug" in data or data.get("name") and "sources" in data and "company_name" in data:
            result = validate_robot(data)
        elif "website" in data or "hq_address" in data or data.get("id"):
            result = validate_company(data)
        else:
            result = validate_robot(data)

        print(f"\n{path}:")
        if result.ok:
            print("  OK")
        else:
            exit_code = 1
            print("  FAILED")
        for issue in result.issues:
            print(f"  [{issue.level}] {issue.field}: {issue.message}")
    return exit_code


def cmd_import(args: argparse.Namespace) -> int:
    target = Path(args.dir or args.file)
    result = import_staging(
        target,
        patch=args.patch,
        status=args.status,
        batch_size=args.batch_size,
        dry_run=not args.apply,
        skip_company_update=args.skip_company_update,
        created_by_id=args.created_by_id,
        replace_media=getattr(args, "refresh_media", False),
    )
    _print_json(result)
    # ok=False can mean "ran with row errors" — still write the audit report
    # whenever an import actually executed (counts present).
    if args.apply and not result.get("dry_run") and "created_count" in result:
        run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        write_backfill_report(
            run_id,
            mode="patch" if args.patch else "greenfield",
            import_summary=result,
        )
    return 0 if result.get("ok") else 1


def cmd_greenfield_dedupe(args: argparse.Namespace) -> int:
    report = greenfield_dedupe_report(args.company)
    _print_json(report)
    return 0


def cmd_greenfield_seeds(args: argparse.Namespace) -> int:
    seeds_file = None
    if getattr(args, "file", None):
        seeds_file = Path(args.file)
        if not seeds_file.is_absolute():
            seeds_file = _RESEARCH_DIR / seeds_file
    _print_json({"seed_companies": load_seed_companies(seeds_file)})
    return 0


def cmd_state_show(_args: argparse.Namespace) -> int:
    _print_json(load_processed_ids().to_dict())
    return 0


def cmd_state_mark(args: argparse.Namespace) -> int:
    state = mark_processed(args.type, args.id)
    _print_json(state.to_dict())
    return 0


def cmd_subcategories(_args: argparse.Namespace) -> int:
    client = ResearchApiClient()
    _print_json(client.get_subcategories())
    return 0


def _refresh_force_fields(args: argparse.Namespace) -> frozenset[str]:
    fields: set[str] = set()
    if getattr(args, "refresh_media", False):
        fields.update({"image", "images", "video_urls"})
    if getattr(args, "refresh_website_url", False):
        fields.update({"url", "sources"})
    if getattr(args, "refresh_description", False):
        # purpose is derived from the description (robot_auto_research builds it from the
        # first sentence), so refreshing one without the other strands the old purpose.
        fields.update({"description", "purpose"})
    for raw in (getattr(args, "force_fields", "") or "").split(","):
        name = raw.strip()
        if name:
            fields.add(name)
    return frozenset(fields)


def _add_verify_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--verify", action="store_true",
        help="AI-verify staged robots BEFORE import: score URL/image/video match with Gemini and "
             "quarantine robots below --min-confidence to staging/.../quarantine/ (needs GEMINI_API_KEY)",
    )
    parser.add_argument(
        "--min-confidence", type=int, default=50,
        help="Verification confidence gate for import, 0-100 (default: 50)",
    )
    parser.add_argument(
        "--strict-verify", action="store_true", dest="strict_verify",
        help="Also quarantine robots the verifier could not check at all (e.g. bot-walled source pages)",
    )


def _add_grounded_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--grounded", action="store_true",
        help="Gemini-grounded media/URL selection during research: visually pick the hero image, "
             "confirm the product URL against fetched page text, and vet videos by metadata "
             "(needs GEMINI_API_KEY; falls back to heuristics when unavailable)",
    )


def _add_apify_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--apify", action="store_true",
        help="Bot-wall escape hatch: fetch pages that block all stealth tiers through Apify's "
             "website-content-crawler (headless Firefox + rotating proxy; needs APIFY_API_KEY; "
             "budgeted per run — slow but reliable). In discovery, also crawls the whole site "
             "via Apify when normal URL discovery is blocked.",
    )


def _add_refresh_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--refresh-media", action="store_true",
        help="Re-research and OVERWRITE existing image/photo/video data, even if already set "
             "(fixes wrong/duplicated photos — implies --all-robots)",
    )
    parser.add_argument(
        "--refresh-website-url", action="store_true",
        help="Re-derive the robot's source/product URL from a fresh company-site crawl (ignoring "
             "the stored URL as crawl anchor) and OVERWRITE it, even if already set — fixes "
             "wrong/off-domain source URLs; keeps the stored URL if re-derivation finds nothing "
             "(implies --all-robots)",
    )
    parser.add_argument(
        "--refresh-description", action="store_true",
        help="Re-research and OVERWRITE the robot's description and purpose, even if already set "
             "(implies --all-robots)",
    )
    parser.add_argument(
        "--force-fields", default="",
        help="Comma-separated staged field names to OVERWRITE even when the DB already holds a "
             "value, for fields without a dedicated flag (e.g. "
             "'features,use_keys,industry_keys,movement_type_keys,release_year'). A freshly "
             "researched blank never overwrites a stored value. Implies --all-robots",
    )


def cmd_auto_robots(args: argparse.Namespace) -> int:
    force_fields = _refresh_force_fields(args)
    all_robots = args.all_robots or bool(force_fields)
    result = research_robots_for_company(
        args.company_id,
        only_missing=not all_robots,
        use_playwright=args.playwright or None,
        use_stealth=getattr(args, "stealth", False) or None,
        use_apify=getattr(args, "apify", False) or None,
        grounded=getattr(args, "grounded", False),
        force_fields=force_fields,
    )
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_auto_verify(args: argparse.Namespace) -> int:
    from verify_staging import verify_staging

    company_name = ""
    company_website = ""
    if args.dir:
        target = Path(args.dir)
        if not target.is_absolute():
            target = _RESEARCH_DIR / target
    elif args.company_id:
        client = ResearchApiClient()
        company = client.get_company(args.company_id)
        company_name = str(company.get("name") or "")
        company_website = str(company.get("website") or "")
        from slug_utils import resolve_company_slug
        slug = resolve_company_slug(company_name, company.get("slug"))
        target = _RESEARCH_DIR / "staging" / "robots" / slug
    else:
        print("--dir or --company-id is required", file=sys.stderr)
        return 1

    result = verify_staging(
        target,
        company_name=args.company_name or company_name,
        company_website=args.company_website or company_website,
        min_confidence=args.min_confidence,
        strict=args.strict,
        quarantine=not args.no_quarantine,
    )
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_auto_discover(args: argparse.Namespace) -> int:
    seed_urls = [u.strip() for u in args.seed_urls.split(",") if u.strip()] if args.seed_urls else []
    result = discover_robots_for_company(
        args.company_id,
        seed_urls=seed_urls,
        use_playwright=args.playwright,
        use_stealth=getattr(args, "stealth", False),
        use_apify=getattr(args, "apify", False) or None,
        skip_existing=not args.include_existing,
        product_pages_only=args.product_pages_only,
        max_per_page=args.max_per_page,
        gemini_delay=args.delay,
        url_limit=args.url_limit,
    )
    if not result.get("ok"):
        print(f"ERROR: {result.get('error')}", file=sys.stderr)
        return 1
    discovered = result.get("discovered", [])
    if not discovered:
        print("No new robots discovered.")
        return 0
    if args.apply_import:
        from import_staging import import_staging
        staging_dir = _RESEARCH_DIR / "staging" / "robots" / result["company_slug"]

        if getattr(args, "verify", False):
            from verify_staging import verify_staging
            client = ResearchApiClient()
            company = client.get_company(args.company_id)
            result["verify"] = verify_staging(
                staging_dir,
                company_name=str(company.get("name") or ""),
                company_website=str(company.get("website") or ""),
                min_confidence=getattr(args, "min_confidence", 50),
                strict=getattr(args, "strict_verify", False),
            )

        # Import only files staged by THIS discovery run — never whatever else
        # happens to sit in the persistent staging dir. The verify gate may have
        # quarantined (moved) some of them, hence the is_file() filter.
        staged_paths = [Path(p) for p in result.get("staged_files", [])]
        importable = [p for p in staged_paths if p.is_file()]
        imp: dict = {}
        if importable:
            imp = import_staging(
                importable,
                patch=True,
                status=args.status,
                dry_run=False,
                created_by_id=args.created_by_id,
            )
            result["import"] = imp
        else:
            print("No importable staged files (all quarantined?) — skipping import.")

        if args.enrich and (imp.get("created_count", 0) + imp.get("updated_count", 0)) > 0:
            enrich = research_robots_for_company(
                args.company_id,
                only_missing=True,
                use_playwright=args.playwright or None,
            )
            result["enrich"] = enrich

    _print_json(result)
    import_ok = result.get("import") is None or result["import"].get("ok", False)
    return 0 if result.get("ok") and import_ok else 1


def cmd_auto_pipeline(args: argparse.Namespace) -> int:
    force_fields = _refresh_force_fields(args)
    all_robots = args.all_robots or bool(force_fields)
    result = auto_research_pipeline(
        args.company_id,
        only_missing=not all_robots,
        use_playwright=args.playwright or None,
        use_stealth=getattr(args, "stealth", False) or None,
        use_apify=getattr(args, "apify", False) or None,
        grounded=getattr(args, "grounded", False),
        apply_import=args.apply_import,
        created_by_id=args.created_by_id,
        patch=not args.no_patch,
        status=args.status,
        force_fields=force_fields,
        verify=getattr(args, "verify", False),
        min_confidence=getattr(args, "min_confidence", 50),
        strict_verify=getattr(args, "strict_verify", False),
    )
    _print_json(result)
    return 0 if result.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RobotAIGeek research agent CLI")
    parser.add_argument("--local", action="store_true", help="Use *_LOCAL env vars to target local dev server")
    sub = parser.add_subparsers(dest="command", required=True)

    backfill = sub.add_parser("backfill", help="Backfill missing company/robot data")
    backfill_sub = backfill.add_subparsers(dest="backfill_cmd", required=True)

    p_next = backfill_sub.add_parser("next-company", help="Fetch next US company with missing data")
    p_next.add_argument(
        "--country",
        default="",
        help="ISO country code filter (default: US from config.json)",
    )
    p_next.set_defaults(func=cmd_backfill_next_company)

    p_robots = backfill_sub.add_parser("robots", help="List robots missing data for a company")
    p_robots.add_argument("--company-id", type=int, required=True)
    p_robots.set_defaults(func=cmd_backfill_robots)

    p_apply = backfill_sub.add_parser("apply-company", help="PATCH company from staging JSON")
    p_apply.add_argument("--file", required=True)
    p_apply.add_argument("--apply", action="store_true", help="Apply patch (default: dry-run)")
    p_apply.set_defaults(func=cmd_backfill_apply_company)

    greenfield = sub.add_parser("greenfield", help="Greenfield company catalog tools")
    gf_sub = greenfield.add_subparsers(dest="greenfield_cmd", required=True)

    p_dedupe = gf_sub.add_parser("dedupe", help="Dedupe staged robots against DB")
    p_dedupe.add_argument("--company", required=True)
    p_dedupe.set_defaults(func=cmd_greenfield_dedupe)

    p_seeds = gf_sub.add_parser("seeds", help="List seed companies")
    p_seeds.add_argument(
        "--file",
        default="",
        help="Seed file path (default: seeds/companies.txt)",
    )
    p_seeds.set_defaults(func=cmd_greenfield_seeds)

    p_val = sub.add_parser("validate", help="Validate staging JSON")
    p_val.add_argument("--file")
    p_val.add_argument("--dir")
    p_val.set_defaults(func=cmd_validate)

    p_imp = sub.add_parser("import", help="Import staging JSON via bulk-import API")
    p_imp.add_argument("--file")
    p_imp.add_argument("--dir")
    p_imp.add_argument("--patch", action="store_true", help="Patch existing robots (backfill)")
    p_imp.add_argument("--apply", action="store_true", help="Push to API (default: dry-run)")
    p_imp.add_argument("--status", default="pending_review")
    p_imp.add_argument("--batch-size", type=int, default=50)
    p_imp.add_argument("--skip-company-update", action="store_true")
    p_imp.add_argument(
        "--created-by-id",
        type=int,
        default=None,
        help="User ID for Robot.created_by and media attribution (or RESEARCH_CREATED_BY_ID / config.json)",
    )
    p_imp.add_argument("--refresh-media", action="store_true", help="Replace existing robot photos on patch import")
    p_imp.add_argument("--run-id", help="Report filename id")
    p_imp.set_defaults(func=cmd_import)

    state = sub.add_parser("state", help="Processed ID tracking")
    state_sub = state.add_subparsers(dest="state_cmd", required=True)
    p_show = state_sub.add_parser("show")
    p_show.set_defaults(func=cmd_state_show)
    p_mark = state_sub.add_parser("mark")
    p_mark.add_argument("--type", choices=["company", "robot"], required=True)
    p_mark.add_argument("--id", type=int, required=True)
    p_mark.set_defaults(func=cmd_state_mark)

    p_tax = sub.add_parser("subcategories", help="Fetch robot subcategories from API")
    p_tax.set_defaults(func=cmd_subcategories)

    auto = sub.add_parser("auto", help="Automated web research (staging JSON with images/videos)")
    auto_sub = auto.add_subparsers(dest="auto_cmd", required=True)

    p_discover = auto_sub.add_parser(
        "discover",
        help="Crawl site to find NEW robots not yet in DB, then stage/import them",
    )
    p_discover.add_argument("--company-id", type=int, required=True)
    p_discover.add_argument(
        "--seed-urls",
        default="",
        help="Comma-separated product page URLs to prioritize (optional)",
    )
    p_discover.add_argument("--playwright", action="store_true", help="Render JS pages")
    p_discover.add_argument(
        "--stealth",
        action="store_true",
        help="Bot-detection avoidance: curl_cffi Chrome impersonation + stealth-Playwright fallback "
             "(requires: pip install curl_cffi playwright-stealth). Use for 403/504 bot-walled sites.",
    )
    p_discover.add_argument(
        "--apply-import",
        action="store_true",
        help="Import staged robots after discovery",
    )
    p_discover.add_argument("--status", default="pending_review")
    p_discover.add_argument("--created-by-id", type=int, default=None)
    p_discover.add_argument("--delay", type=float, default=1.0, help="Seconds between Gemini calls")
    p_discover.add_argument("--url-limit", type=int, default=60, help="Max candidate URLs to check")
    p_discover.add_argument("--include-existing", action="store_true", help="Don't skip robots already in DB")
    p_discover.add_argument(
        "--product-pages-only",
        action="store_true",
        help="Skip blog/case-study URLs with long slugs; only process dedicated product pages",
    )
    p_discover.add_argument(
        "--max-per-page",
        type=int,
        default=0,
        help="Skip pages yielding more than N robots (listing pages). 0=no limit",
    )
    p_discover.add_argument(
        "--enrich",
        action="store_true",
        help="After importing, run enrichment pipeline to fill specs, images, categories. Requires --apply-import.",
    )
    _add_verify_args(p_discover)
    _add_apify_arg(p_discover)
    p_discover.set_defaults(func=cmd_auto_discover)

    p_auto_robots = auto_sub.add_parser(
        "robots",
        help="Crawl manufacturer site and write staging/robots/{slug}/*.json",
    )
    p_auto_robots.add_argument("--company-id", type=int, required=True)
    p_auto_robots.add_argument(
        "--all-robots",
        action="store_true",
        help="Research all company robots, not only missing-data queue",
    )
    p_auto_robots.add_argument(
        "--playwright",
        action="store_true",
        help="Render JS pages (requires: pip install playwright && playwright install chromium)",
    )
    p_auto_robots.add_argument(
        "--stealth",
        action="store_true",
        help="Bot-detection avoidance: curl_cffi Chrome impersonation + stealth-Playwright fallback "
             "(requires: pip install curl_cffi playwright-stealth)",
    )
    _add_refresh_args(p_auto_robots)
    _add_grounded_arg(p_auto_robots)
    _add_apify_arg(p_auto_robots)
    p_auto_robots.set_defaults(func=cmd_auto_robots)

    p_verify = auto_sub.add_parser(
        "verify",
        help="AI-verify staged robots (URL/image/video match) and quarantine mismatches",
    )
    p_verify.add_argument("--company-id", type=int, default=None,
                          help="Resolve staging dir + company name/website from the API")
    p_verify.add_argument("--dir", default="",
                          help="Staging dir or single JSON file (overrides --company-id lookup)")
    p_verify.add_argument("--company-name", default="", help="Company name for grounding (with --dir)")
    p_verify.add_argument("--company-website", default="", help="Company website for grounding (with --dir)")
    p_verify.add_argument("--min-confidence", type=int, default=50)
    p_verify.add_argument("--strict", action="store_true",
                          help="Also quarantine robots that could not be checked at all")
    p_verify.add_argument("--no-quarantine", action="store_true",
                          help="Score and report only; do not move any files")
    p_verify.set_defaults(func=cmd_auto_verify)

    p_auto_pipe = auto_sub.add_parser(
        "pipeline",
        help="Auto-research robots then optionally import (--apply-import)",
    )
    p_auto_pipe.add_argument("--company-id", type=int, required=True)
    p_auto_pipe.add_argument("--all-robots", action="store_true")
    p_auto_pipe.add_argument("--playwright", action="store_true")
    p_auto_pipe.add_argument(
        "--stealth",
        action="store_true",
        help="Bot-detection avoidance: curl_cffi Chrome impersonation + stealth-Playwright fallback",
    )
    p_auto_pipe.add_argument(
        "--apply-import",
        action="store_true",
        help="Import staged robots after research (patch mode by default)",
    )
    p_auto_pipe.add_argument("--no-patch", action="store_true", help="Full overwrite on import")
    p_auto_pipe.add_argument("--status", default="pending_review")
    p_auto_pipe.add_argument("--created-by-id", type=int, default=None)
    _add_refresh_args(p_auto_pipe)
    _add_grounded_arg(p_auto_pipe)
    _add_apify_arg(p_auto_pipe)
    _add_verify_args(p_auto_pipe)
    p_auto_pipe.set_defaults(func=cmd_auto_pipeline)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
