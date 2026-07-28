"""
Backfill missing company info (website, country, logo, description, hq_address)
by researching each company using Claude with web search, then patching via API.

Usage:
  # Dry run — show what would be updated
  python backfill_company_info.py

  # Apply to local
  python backfill_company_info.py --local --apply

  # Apply to prod
  python backfill_company_info.py --apply

  # Only fill specific fields
  python backfill_company_info.py --apply --fields website,country,logo

  # Limit to N companies
  python backfill_company_info.py --apply --limit 20

  # Filter by company ID
  python backfill_company_info.py --apply --company-id 174

  # Delay between companies (seconds)
  python backfill_company_info.py --apply --delay 2
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
import urllib.request
from typing import Any

# Ensure UTF-8 output on Windows (company names may contain non-ASCII chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Load env before importing api_client
import sys as _sys
from load_env import load_research_env
load_research_env(local="--local" in _sys.argv)

from api_client import ResearchApiClient
from company_research import research_company, CompanyResearchResult


FIELDS_DEFAULT = (
    "website,country,logo,description,hq_address,"
    "contact_info,leaders_roles,sources,"
    "company_status,company_maturity,product_type,"
    "employee_count,primary_focus"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill missing company info via API + Claude research")
    p.add_argument("--apply", action="store_true", help="Write changes to DB (default: dry run)")
    p.add_argument("--local", action="store_true", help="Use LOCAL env vars (*_LOCAL)")
    p.add_argument("--fields", default=FIELDS_DEFAULT, help=f"Comma-separated fields to fill (default: {FIELDS_DEFAULT})")
    p.add_argument("--limit", type=int, default=0, help="Stop after N companies (0 = no limit)")
    p.add_argument("--company-id", type=int, default=0, help="Backfill a single specific company by ID")
    p.add_argument("--delay", type=float, default=1.5, help="Seconds to wait between companies (default: 1.5)")
    p.add_argument("--source-locale", default="en", help="Only process companies with this source_locale (default: en)")
    p.add_argument("--min-robots", type=int, default=0, help="Only process companies with >= N robots")
    return p.parse_args()


def _download_logo(url: str, timeout: int = 15) -> tuple[bytes, str] | None:
    """Download logo bytes from URL. Returns (bytes, filename) or None."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
        # Derive filename from URL
        path = url.split("?")[0].rstrip("/")
        filename = path.split("/")[-1] or "logo.png"
        if "." not in filename:
            filename += ".png"
        return content, filename
    except Exception as exc:
        print(f"      logo download failed: {exc}")
        return None


_NULL_FIELDS = {"employee_count", "employee_min", "employee_max"}
_JSON_LIST_FIELDS = {"primary_focus"}


def _fields_missing(company: dict[str, Any], fields: list[str]) -> list[str]:
    """Return which of the requested fields are actually empty on this company."""
    missing = []
    for f in fields:
        if f == "country":
            if not company.get("country"):
                missing.append(f)
        elif f == "logo":
            if not company.get("logo_url"):
                missing.append(f)
        elif f in _NULL_FIELDS:
            if company.get(f) is None:
                missing.append(f)
        elif f in _JSON_LIST_FIELDS:
            val = company.get(f)
            if not val:  # None or empty list
                missing.append(f)
        else:
            if not (company.get(f) or "").strip():
                missing.append(f)
    return missing


def _build_patch(result: CompanyResearchResult, fields_needed: list[str], client: ResearchApiClient) -> dict[str, Any]:
    """Build PATCH payload from research result, skipping empty values."""
    patch: dict[str, Any] = {}

    _str_fields = {
        "website": result.website,
        "description": result.description,
        "hq_address": result.hq_address,
        "contact_info": result.contact_info,
        "leaders_roles": result.leaders_roles,
        "sources": result.sources,
        "company_status": result.company_status,
        "company_maturity": result.company_maturity,
        "product_type": result.product_type,
    }
    for field, value in _str_fields.items():
        if field in fields_needed and value:
            patch[field] = value

    if "country" in fields_needed and result.country_code:
        country_id = client.resolve_country_id(result.country_code)
        if country_id:
            patch["country_id"] = country_id

    if "employee_count" in fields_needed and result.employee_count is not None:
        patch["employee_count"] = result.employee_count
    if "employee_min" in fields_needed and result.employee_min is not None:
        patch["employee_min"] = result.employee_min
    if "employee_max" in fields_needed and result.employee_max is not None:
        patch["employee_max"] = result.employee_max

    if "primary_focus" in fields_needed and result.primary_focus:
        patch["primary_focus"] = result.primary_focus

    return patch


def process_company(
    company: dict[str, Any],
    fields: list[str],
    client: ResearchApiClient,
    apply: bool,
    idx: int,
    total: int,
) -> dict[str, str]:
    """Research and patch one company. Returns summary dict."""
    name = company.get("name", "?")
    company_id = company.get("id")
    website = company.get("website") or ""
    fields_missing = _fields_missing(company, fields)

    print(f"\n[{idx}/{total}] {name} (id={company_id})")
    if not fields_missing:
        print("  — all fields already filled, skipping")
        return {"status": "skipped", "reason": "already complete"}

    print(f"  missing: {', '.join(fields_missing)}")

    # Research via Claude
    result = research_company(
        name=name,
        known_website=website,
        fields_needed=fields_missing,
    )

    updates: list[str] = []

    # Build text field patch
    patch = _build_patch(result, fields_missing, client)

    # Handle logo separately (multipart upload)
    logo_bytes = None
    logo_filename = ""
    if "logo" in fields_missing and result.logo_url:
        logo_data = _download_logo(result.logo_url)
        if logo_data:
            logo_bytes, logo_filename = logo_data
            updates.append(f"logo ({logo_filename})")

    if patch:
        updates.extend(f"{k}={v!r:.40}" for k, v in patch.items() if k != "country_id")
        if "country_id" in patch:
            updates.append(f"country={result.country_code}")

    if not patch and not logo_bytes:
        print(f"  — nothing found (confidence={result.confidence})")
        return {"status": "no_data", "confidence": result.confidence}

    print(f"  found: {', '.join(updates)}")
    print(f"  confidence: {result.confidence}")

    if not apply:
        print("  [dry run] no changes written")
        return {"status": "dry_run"}

    # Apply text patch
    if patch:
        try:
            client.patch_company(company_id, patch)
        except Exception as exc:
            print(f"  ERROR patching text fields: {exc}")
            return {"status": "error", "error": str(exc)}

    # Apply logo upload
    if logo_bytes:
        try:
            client.patch_company_logo(company_id, logo_bytes, logo_filename)
        except Exception as exc:
            print(f"  ERROR uploading logo: {exc}")
            # Don't abort — text patch already succeeded

    print(f"  OK updated: {', '.join(updates)}")
    return {"status": "updated", "fields": updates}


def main() -> None:
    args = parse_args()
    client = ResearchApiClient()

    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    dry_run = not args.apply

    print("=" * 64)
    print("Company Info Backfill")
    print(f"  Fields : {', '.join(fields)}")
    print(f"  Mode   : {'DRY RUN' if dry_run else 'APPLY'}")
    print(f"  Target : {'LOCAL' if args.local else 'PROD'}")
    print("=" * 64)

    # Fetch companies to process
    if args.company_id:
        companies = [client.get_company(args.company_id)]
    else:
        print(f"\nFetching companies with missing fields: {', '.join(fields)} ...")
        companies = client.list_companies_missing_info(
            fields=args.fields,
            source_locale=args.source_locale,
        )
        if args.min_robots:
            companies = [c for c in companies if (c.get("robot_count") or 0) >= args.min_robots]

    total = len(companies)
    if args.limit:
        companies = companies[: args.limit]
    print(f"Companies to process: {len(companies)} (total with missing data: {total})\n")

    stats = {"updated": 0, "skipped": 0, "no_data": 0, "error": 0, "dry_run": 0}

    for idx, company in enumerate(companies, 1):
        result = process_company(
            company=company,
            fields=fields,
            client=client,
            apply=args.apply,
            idx=idx,
            total=len(companies),
        )
        status = result.get("status", "error")
        stats[status] = stats.get(status, 0) + 1

        if idx < len(companies) and args.delay > 0:
            time.sleep(args.delay)

    print("\n" + "=" * 64)
    print("Summary")
    for k, v in stats.items():
        if v:
            print(f"  {k}: {v}")
    if dry_run:
        print("\nRun with --apply to write changes.")
    print("=" * 64)


if __name__ == "__main__":
    main()
