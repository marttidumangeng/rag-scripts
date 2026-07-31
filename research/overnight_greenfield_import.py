"""Overnight greenfield company import.

Reads the competitor gap list (competitor_gap_companies.json), and for each
company that is not yet in the RobotAIGeek database:

  Stage 0 — Company Creation
    • Resolve the company's official website: prefer the validated `website`
      stored on the gap entry at discovery time; fall back to a live resolve
      (Robolist page scrape → serper.dev search) only when none is stored.
    • POST /api/v1/companies/ to create the bare company record.
    • Skip if the company already exists (dedup guard via find_existing_company).

  Stage 1 — Robot Discovery
    • Call discover_robots_for_company() against the manufacturer's website.
    • Writes staging JSON to staging/robots/{slug}/.

  Stage 2 — Enrichment & Import
    • Call auto_research_pipeline() to enrich staged robots and import them
      as pending_review.

Progress is checkpointed to staging/reports/greenfield-import-progress.json
after each company so the run can be interrupted and resumed safely.

Usage:
  python -u overnight_greenfield_import.py
  python -u overnight_greenfield_import.py --max-companies 5
  python -u overnight_greenfield_import.py --dry-run
  python -u overnight_greenfield_import.py --company-name "Enchanted Tools"
  python -u overnight_greenfield_import.py --skip-discovery   # Stage 0 only
  python -u overnight_greenfield_import.py --local
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from company_country_resolve import resolve_company_country  # noqa: E402
from company_website_resolve import (  # noqa: E402
    resolve_company_website,
    validate_website,
    website_from_robolist,
)
from discover_robots import discover_robots_for_company  # noqa: E402
from workflow_auto_research import auto_research_pipeline  # noqa: E402
from workflow_greenfield import find_existing_company  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
GAP_REPORT = _RESEARCH_DIR / "staging" / "reports" / "competitor_gap_companies.json"
PROGRESS_PATH = _RESEARCH_DIR / "staging" / "reports" / "greenfield-import-progress.json"
SUMMARY_PATH = _RESEARCH_DIR / "staging" / "reports" / "greenfield-import-summary.json"
STATE_PATH = _RESEARCH_DIR / "state" / "greenfield_processed.json"

# NOTE: a `_CATEGORY_MAP` of Robolist labels lived here and was never referenced
# by anything. Category mapping now lives in `robot_categories.py`, against a
# vocabulary of slugs that actually exist on prod — half the slugs in the old map
# ("industrial-arm", "cobot", "hospitality", "medical", "logistics") did not.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_print(*args: Any, **kwargs: Any) -> None:
    kwargs.setdefault("flush", True)
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"), **kwargs)


def _load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"processed_names": [], "created_company_ids": [], "notes": {}}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _mark_processed(state: dict[str, Any], name: str, company_id: int | None, note: str) -> None:
    norm = name.strip().lower()
    if norm not in [n.lower() for n in state["processed_names"]]:
        state["processed_names"].append(name.strip())
    if company_id and company_id not in state["created_company_ids"]:
        state["created_company_ids"].append(company_id)
    state["notes"][name.strip()] = {"at": _now(), "company_id": company_id, "note": note}
    _save_state(state)


def _save_progress(progress: dict[str, Any]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = _now()
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Stage 0: Robolist website extraction
# ---------------------------------------------------------------------------

def fetch_robolist_website(slug: str, *, timeout: int = 12) -> str | None:
    """Scrape a Robolist company page and return the first external website URL.

    Thin wrapper kept for backward compatibility; the scraping logic now lives
    in :mod:`company_website_resolve` so the discovery and import stages share
    one implementation.
    """
    return website_from_robolist(slug, timeout=timeout)


# ---------------------------------------------------------------------------
# Stage 0: Company creation
# ---------------------------------------------------------------------------

def _website_plausibly_matches_company(website: str, company_name: str) -> bool:
    """Heuristic check: does the website domain look like it belongs to this company?

    Returns False when the domain is clearly a different well-known brand.
    This catches Robolist data quality issues (e.g. RobotLAB Group → ubtrobot.com).
    """
    if not website or not company_name:
        return True  # can't tell — allow through

    domain_match = re.match(r"https?://(?:www\.)?([^/]+)", website)
    if not domain_match:
        return True
    domain = domain_match.group(1).lower()
    # Strip TLD for substring matching (e.g. ti5robot.com → ti5robot)
    domain_base = re.sub(r"\.[a-z]{2,6}$", "", domain)  # remove last TLD
    domain_base = re.sub(r"\.[a-z]{2,6}$", "", domain_base)  # remove ccTLD if present

    # Tokenise the company name (split on non-alphanumeric)
    name_tokens = set(re.sub(r"[^a-z0-9]+", " ", company_name.lower()).split())
    # Remove generic stop-words
    _stop = {"co", "com", "ltd", "inc", "corp", "group", "robot", "robotics",
             "ai", "tech", "technology", "technologies", "systems", "the",
             "industries", "industry", "global", "international"}
    name_tokens -= _stop

    if not name_tokens:
        # Every token was generic ("Robot.com" -> {robot, com}, both stop-words).
        # Returning True here meant the guard silently switched OFF for exactly the
        # names it should scrutinise most: the first unattended nightly run created
        # company "Robot.com" pointing at nextmsc.com (a market-research firm) because
        # of this branch. Fall back to comparing the whole squashed name against the
        # domain instead of waving it through — "robotcom" vs "nextmsc" is clearly not
        # a match, while a genuinely generic-but-matching pair ("Robotics Inc" /
        # robotics-inc.com) still passes.
        squashed = re.sub(r"[^a-z0-9]+", "", company_name.lower())
        domain_squashed = re.sub(r"[^a-z0-9]+", "", domain_base)
        if squashed and domain_squashed and (
            squashed in domain_squashed or domain_squashed in squashed
        ):
            return True
        _safe_print(
            f"    website unverifiable: company={company_name!r} has no distinctive "
            f"tokens and domain={domain!r} does not match — skipping"
        )
        return False

    # Check 1: any name token appears as a substring of the domain base
    for tok in name_tokens:
        if len(tok) >= 2 and tok in domain_base:
            return True

    # Check 2: the domain base (or significant portion) appears in the company name
    # (handles e.g. kondo-robot.com → kondo appears in "Kondo Kagaku")
    domain_tokens = set(re.sub(r"[^a-z0-9]+", " ", domain_base).split())
    domain_tokens -= _stop
    for tok in domain_tokens:
        if len(tok) >= 4 and tok in company_name.lower():
            return True

    _safe_print(f"    website mismatch: domain={domain!r} vs company={company_name!r} — skipping")
    return False


def create_or_find_company(
    entry: dict[str, Any],
    client: ResearchApiClient,
    *,
    dry_run: bool = False,
) -> tuple[int | None, str]:
    """Return (company_id, status_string).

    Status strings:
      "existing"        — company already in DB (skipped creation)
      "created"         — new company record created
      "no_website"      — no website stored/resolved (Robolist + search both failed)
      "website_mismatch" — resolved website doesn't match the company name
      "create_failed"   — API POST failed
    """
    name = entry["name"]
    slug = entry.get("slug", "")

    # Dedup guard: check DB first (handle 403 gracefully — treat as not found)
    try:
        existing = find_existing_company(name, client)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 403:
            _safe_print(f"    search_companies returned 403 — treating as not-in-DB")
            existing = None
        else:
            raise
    if existing:
        cid = existing.get("id")
        _safe_print(f"    already in DB: id={cid} name={existing.get('name')}")
        return (int(cid) if cid else None, "existing")

    # Resolve the website. Prefer the one stored on the gap entry at discovery
    # time — Robolist pages now 404 for ~90% of slugs, so re-fetching here is
    # the original bug. Only fall back to a live resolve when none is stored.
    website: str | None = None
    stored = (entry.get("website") or "").strip()
    if stored:
        if validate_website(stored):
            website = stored
            _safe_print(f"    website (stored): {website}")
        else:
            _safe_print(f"    stored website failed validation ({stored!r}) — re-resolving")

    if not website:
        website, method = resolve_company_website(
            name, slug, country=entry.get("country"),
        )
        if website:
            _safe_print(f"    website ({method}): {website}")

    if not website:
        _safe_print(f"    no website resolved for slug={slug!r} name={name!r}")
        return (None, "no_website")

    # Sanity-check: does the domain plausibly belong to this company?
    if not _website_plausibly_matches_company(website, name):
        return (None, "website_mismatch")

    if dry_run:
        _safe_print(f"    [dry-run] would create company: name={name!r} website={website}")
        return (None, "dry_run_created")

    # Resolve country_id if country code is available. When the gap entry has no
    # country, resolve it NOW rather than creating a blank Company: enrichment
    # fills each robot's country by copying `company.country`, so a company born
    # blank stamps the error-severity "No country" flag on every robot it will
    # ever own — 232 of 806 companies were in that state on 2026-07-31.
    country_id: int | None = None
    country_code = entry.get("country") or entry.get("country_code") or ""
    if not country_code:
        country_code, how = resolve_company_country(name, website)
        if country_code:
            _safe_print(f"    country ({how}): {country_code}")
    if country_code:
        country_id = client.resolve_country_id(country_code)
        if not country_id:
            _safe_print(f"    !! country {country_code} has no Country row — left blank")

    payload: dict[str, Any] = {
        "name": name,
        "website": website,
        "source_locale": "en",
    }
    if country_id:
        payload["country_id"] = country_id

    try:
        company = client.create_company(payload)
        cid = company.get("id")
        _safe_print(f"    created company id={cid} name={company.get('name')!r} website={website}")
        return (int(cid) if cid else None, "created")
    except requests.HTTPError as exc:
        body = ""
        if exc.response is not None:
            try:
                body = exc.response.json()
            except Exception:
                body = exc.response.text[:300]
        _safe_print(f"    create_company failed: {exc} — {body}")
        return (None, "create_failed")


# ---------------------------------------------------------------------------
# Stage 1: Robot discovery
# ---------------------------------------------------------------------------

def run_discovery(
    company_id: int,
    *,
    dry_run: bool = False,
    url_limit: int = 60,
    product_pages_only: bool = True,
    max_per_page: int = 4,
) -> dict[str, Any]:
    """Run discover_robots_for_company and return the summary dict."""
    if dry_run:
        _safe_print(f"    [dry-run] would run discovery for company_id={company_id}")
        return {"ok": True, "dry_run": True, "discovered": [], "staged_files": []}

    result = discover_robots_for_company(
        company_id,
        skip_existing=True,
        product_pages_only=product_pages_only,
        max_per_page=max_per_page,
        url_limit=url_limit,
    )
    discovered = len(result.get("discovered") or [])
    staged = len(result.get("staged_files") or [])
    _safe_print(f"    discovery: ok={result.get('ok')} discovered={discovered} staged={staged}")
    return result


# ---------------------------------------------------------------------------
# Stage 2: Enrichment & import
# ---------------------------------------------------------------------------

def run_enrich_import(
    company_id: int,
    *,
    dry_run: bool = False,
    created_by_id: int | None = None,
    status: str = "pending_review",
) -> dict[str, Any]:
    """Run auto_research_pipeline and return the summary dict."""
    if dry_run:
        _safe_print(f"    [dry-run] would run enrich+import for company_id={company_id}")
        return {"ok": True, "dry_run": True}

    result = auto_research_pipeline(
        company_id,
        only_missing=True,
        apply_import=True,
        patch=True,
        status=status,
        created_by_id=created_by_id,
        grounded=False,
    )
    imp = result.get("import") or {}
    imported = imp.get("imported", 0) if isinstance(imp, dict) else 0
    _safe_print(
        f"    enrich+import: ok={result.get('ok')} imported={imported} "
        f"report={result.get('report')}"
    )
    return result


# ---------------------------------------------------------------------------
# Per-company orchestration
# ---------------------------------------------------------------------------

def process_company(
    entry: dict[str, Any],
    client: ResearchApiClient,
    state: dict[str, Any],
    *,
    dry_run: bool = False,
    skip_discovery: bool = False,
    skip_enrich: bool = False,
    created_by_id: int | None = None,
    url_limit: int = 60,
) -> dict[str, Any]:
    """Run all three stages for one company. Returns a result dict."""
    name = entry["name"]
    result: dict[str, Any] = {
        "name": name,
        "slug": entry.get("slug", ""),
        "categories": entry.get("categories", []),
        "started_at": _now(),
        "stage0_status": None,
        "company_id": None,
        "stage1": None,
        "stage2": None,
        "error": None,
    }

    try:
        # ---- Stage 0: Create or find company ----
        _safe_print(f"\n  Stage 0 — company creation: {name!r}")
        company_id, status0 = create_or_find_company(entry, client, dry_run=dry_run)
        result["stage0_status"] = status0
        result["company_id"] = company_id

        if status0 in ("no_website", "website_mismatch"):
            _mark_processed(state, name, None, status0)
            result["skipped"] = status0
            return result

        if status0 == "create_failed":
            _mark_processed(state, name, None, "create_failed")
            result["skipped"] = "create_failed"
            return result

        # For dry_run we have no real company_id — stop here
        if dry_run:
            result["skipped"] = "dry_run"
            return result

        if company_id is None:
            result["error"] = "company_id is None after stage0"
            return result

        # ---- Stage 1: Robot discovery ----
        if not skip_discovery:
            _safe_print(f"  Stage 1 — robot discovery: company_id={company_id}")
            disc = run_discovery(company_id, dry_run=dry_run, url_limit=url_limit)
            result["stage1"] = {
                "ok": disc.get("ok"),
                "discovered": len(disc.get("discovered") or []),
                "staged": len(disc.get("staged_files") or []),
                "errors": len(disc.get("errors") or []),
            }
            # If nothing was discovered, skip enrichment (nothing to import)
            if not disc.get("ok") or not disc.get("staged_files"):
                _safe_print("    no robots staged — skipping enrichment")
                _mark_processed(state, name, company_id, "no_robots_discovered")
                result["skipped"] = "no_robots_discovered"
                return result
        else:
            _safe_print(f"  Stage 1 — skipped (--skip-discovery)")
            result["stage1"] = {"skipped": True}

        # ---- Stage 2: Enrichment & import ----
        if not skip_enrich:
            _safe_print(f"  Stage 2 — enrich+import: company_id={company_id}")
            enrich = run_enrich_import(
                company_id,
                dry_run=dry_run,
                created_by_id=created_by_id,
            )
            imp = enrich.get("import") or {}
            result["stage2"] = {
                "ok": enrich.get("ok"),
                "imported": imp.get("imported", 0) if isinstance(imp, dict) else 0,
                "report": enrich.get("report"),
            }
        else:
            _safe_print("  Stage 2 — skipped (--skip-enrich)")
            result["stage2"] = {"skipped": True}

        _mark_processed(state, name, company_id, "completed")
        result["completed_at"] = _now()

    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()[-1200:]
        _safe_print(f"  ERROR processing {name!r}: {exc}")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_gap_entries() -> list[dict[str, Any]]:
    """Load the full gap list from competitor_gap_companies.json."""
    if not GAP_REPORT.exists():
        _safe_print(f"Gap report not found: {GAP_REPORT}")
        _safe_print("Run competitor_gap_discover.py first to generate it.")
        return []
    data = json.loads(GAP_REPORT.read_text(encoding="utf-8"))
    return data.get("top_gaps", [])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Overnight greenfield import: create missing companies + discover + enrich",
    )
    parser.add_argument("--max-companies", type=int, default=0, help="0 = no limit")
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no writes")
    parser.add_argument(
        "--company-name",
        type=str,
        default="",
        help="Process only this one company (partial match, case-insensitive)",
    )
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Run Stage 0 only (create company) — skip robot discovery",
    )
    parser.add_argument(
        "--skip-enrich",
        action="store_true",
        help="Run Stage 0+1 only — skip enrichment and import",
    )
    parser.add_argument(
        "--created-by-id",
        type=int,
        default=None,
        help="User ID for Robot.created_by attribution",
    )
    parser.add_argument(
        "--url-limit",
        type=int,
        default=60,
        help="Max candidate URLs to check per company during discovery (default 60)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use *_LOCAL env vars to target local dev server",
    )
    args = parser.parse_args()

    _safe_print("=== Overnight Greenfield Import ===")
    _safe_print(f"started {_now()}")
    _safe_print(f"dry_run={args.dry_run}  max_companies={args.max_companies or 'unlimited'}")

    client = ResearchApiClient()
    state = _load_state()
    already_processed = {n.strip().lower() for n in state.get("processed_names", [])}

    entries = load_gap_entries()
    if not entries:
        _safe_print("No gap entries found. Exiting.")
        return 1

    # Filter to a single company if requested
    if args.company_name.strip():
        needle = args.company_name.strip().lower()
        entries = [e for e in entries if needle in e["name"].lower()]
        if not entries:
            _safe_print(f"No entry matching --company-name {args.company_name!r}")
            return 1
        _safe_print(f"Filtered to {len(entries)} matching entries")

    progress: dict[str, Any] = {
        "started_at": _now(),
        "dry_run": args.dry_run,
        "total_entries": len(entries),
        "completed": [],
        "skipped": [],
        "failed": [],
    }
    _save_progress(progress)

    attempted = 0
    max_co = args.max_companies or None

    for entry in entries:
        name = entry["name"]
        norm = name.strip().lower()

        # Skip already-processed companies
        if norm in already_processed:
            _safe_print(f"\n  skip (already processed): {name!r}")
            continue

        _safe_print(f"\n## [{attempted + 1}] {name} (slug={entry.get('slug')!r})")

        result = process_company(
            entry,
            client,
            state,
            dry_run=args.dry_run,
            skip_discovery=args.skip_discovery,
            skip_enrich=args.skip_enrich,
            created_by_id=args.created_by_id,
            url_limit=args.url_limit,
        )

        if result.get("error"):
            progress["failed"].append(result)
            _safe_print(f"  FAILED: {result['error']}")
        elif result.get("skipped"):
            progress["skipped"].append(result)
        else:
            progress["completed"].append(result)

        _save_progress(progress)
        attempted += 1

        if max_co is not None and attempted >= max_co:
            _safe_print(f"\nReached --max-companies {max_co}. Stopping.")
            break

        # Polite delay between companies
        if not args.dry_run:
            time.sleep(2.0)

    # Final summary
    summary = {
        "finished_at": _now(),
        "dry_run": args.dry_run,
        "attempted": attempted,
        "completed": len(progress["completed"]),
        "skipped": len(progress["skipped"]),
        "failed": len(progress["failed"]),
        "companies_created": sum(
            1 for r in progress["completed"] if r.get("stage0_status") == "created"
        ),
        "robots_imported": sum(
            (r.get("stage2") or {}).get("imported", 0)
            for r in progress["completed"]
            if isinstance(r.get("stage2"), dict)
        ),
        "details": progress,
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _safe_print("\n=== Summary ===")
    _safe_print(f"  attempted:         {attempted}")
    _safe_print(f"  completed:         {summary['completed']}")
    _safe_print(f"  companies created: {summary['companies_created']}")
    _safe_print(f"  robots imported:   {summary['robots_imported']}")
    _safe_print(f"  skipped:           {summary['skipped']}")
    _safe_print(f"  failed:            {summary['failed']}")
    _safe_print(f"  summary → {SUMMARY_PATH.relative_to(_RESEARCH_DIR.parent.parent)}")

    return 1 if progress["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
