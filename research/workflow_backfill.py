"""Backfill workflow helpers for company and robot missing-data queues."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_client import ResearchApiClient
from schema import ProcessedIds, StagedCompany
from slug_utils import is_generic_company_slug, resolve_company_slug, slugify_company_name
from validate_staging import validate_company

RESEARCH_DIR = Path(__file__).resolve().parent
STATE_FILE = RESEARCH_DIR / "state" / "processed_ids.json"
CONFIG_FILE = RESEARCH_DIR / "config.json"
STAGING_COMPANIES = RESEARCH_DIR / "staging" / "companies"
STAGING_REPORTS = RESEARCH_DIR / "staging" / "reports"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {
            "country_code": "US",
            "include_null_country": True,
            "exclude_generic_slugs": False,
        }
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def load_processed_ids() -> ProcessedIds:
    if not STATE_FILE.exists():
        return ProcessedIds()
    return ProcessedIds.from_dict(json.loads(STATE_FILE.read_text(encoding="utf-8")))


def save_processed_ids(state: ProcessedIds) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")


def mark_processed(entity_type: str, entity_id: int) -> ProcessedIds:
    state = load_processed_ids()
    if entity_type == "company":
        if entity_id not in state.companies:
            state.companies.append(entity_id)
    elif entity_type == "robot":
        if entity_id not in state.robots:
            state.robots.append(entity_id)
    else:
        raise ValueError(f"Unknown entity type: {entity_type}")
    save_processed_ids(state)
    return state


def fetch_next_company(
    client: ResearchApiClient | None = None,
    *,
    country_code: str | None = None,
    exclude_generic_slugs: bool | None = None,
) -> dict[str, Any] | None:
    client = client or ResearchApiClient()
    state = load_processed_ids()
    config = load_config()
    cc = country_code if country_code is not None else config.get("country_code", "US")
    exclude_generic = (
        exclude_generic_slugs
        if exclude_generic_slugs is not None
        else bool(config.get("exclude_generic_slugs", False))
    )
    include_null = bool(config.get("include_null_country", True))
    company = client.get_company_missing_data(
        exclude_ids=state.exclude_ids_param("company"),
        country_code=cc or None,
        include_null_country=include_null,
        exclude_generic_slugs=exclude_generic,
    )
    if not company:
        return None
    name = company.get("name") or ""
    current_slug = company.get("slug")
    suggested = resolve_company_slug(name, current_slug)
    company["_suggested_slug"] = suggested
    company["_has_generic_slug"] = is_generic_company_slug(current_slug)
    company["_staging_file"] = f"scripts/research/staging/companies/{suggested}.json"
    return company


def fetch_robots_missing_for_company(
    company_id: int,
    client: ResearchApiClient | None = None,
    *,
    detailed: bool = True,
) -> list[dict[str, Any]]:
    """Return robots with missing data that belong to company_id."""
    client = client or ResearchApiClient()
    state = load_processed_ids()
    missing: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client.get_robot_missing_data(
            detailed=detailed,
            exclude_ids=state.exclude_ids_param("robot"),
            page=page,
            page_size=50,
        )
        batch = data.get("results", [])
        for robot in batch:
            cref = robot.get("company_ref") or {}
            rid = cref.get("id") if isinstance(cref, dict) else robot.get("company_ref")
            if rid == company_id:
                missing.append(robot)
        if not data.get("next"):
            break
        page += 1
    return missing


def _sources_to_text(sources: list) -> str:
    """Company.sources is a TextField — serialize staging source refs to plain text."""
    lines: list[str] = []
    for src in sources:
        if hasattr(src, "url"):
            url = src.url
            title = getattr(src, "title", "") or ""
        elif isinstance(src, dict):
            url = src.get("url", "")
            title = src.get("title", "") or ""
        else:
            url = str(src)
            title = ""
        if url:
            lines.append(f"{title}: {url}" if title else url)
    return "\n".join(lines)


def company_staging_to_patch_payload(staged: StagedCompany) -> dict[str, Any]:
    """Map staged company to CompanyUpdateSerializer fields (non-empty only)."""
    payload: dict[str, Any] = {}
    if staged.description:
        payload["description"] = staged.description
    if staged.website:
        payload["website"] = staged.website
    if staged.hq_address:
        payload["hq_address"] = staged.hq_address
    if staged.contact_info:
        payload["contact_info"] = staged.contact_info
    if staged.leaders_roles:
        payload["leaders_roles"] = staged.leaders_roles
    if staged.employee_count:
        payload["employee_count"] = staged.employee_count
    if staged.employee_min is not None:
        payload["employee_min"] = staged.employee_min
    if staged.employee_max is not None:
        payload["employee_max"] = staged.employee_max
    if staged.company_status:
        payload["company_status"] = staged.company_status
    if staged.product_stage:
        payload["product_stage"] = staged.product_stage
    if staged.company_maturity:
        payload["company_maturity"] = staged.company_maturity
    if staged.product_type:
        payload["product_type"] = staged.product_type
    if staged.primary_focus:
        payload["primary_focus"] = staged.primary_focus
    if staged.notes:
        notes = staged.notes
        if staged.research_notes:
            notes = f"{notes} | {staged.research_notes}"
        payload["notes"] = f"[AI Research] {notes}"
    elif staged.research_notes:
        payload["notes"] = f"[AI Research] {staged.research_notes}"
    if staged.country_id is not None:
        payload["country_id"] = staged.country_id
    if staged.slug:
        payload["slug"] = staged.slug
    source_urls = "|".join(s.url for s in staged.sources if s.url)
    if source_urls and "notes" in payload:
        payload["notes"] += f" | Sources: {source_urls.replace('|', ' | ')}"
    elif source_urls:
        payload["notes"] = f"[AI Research] Sources: {source_urls.replace('|', ' | ')}"
    if staged.sources:
        payload["sources"] = _sources_to_text(staged.sources)
    return payload


def apply_company_patch(
    staged_path: Path,
    *,
    client: ResearchApiClient | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    client = client or ResearchApiClient()
    data = json.loads(staged_path.read_text(encoding="utf-8"))
    staged = StagedCompany.from_dict(data)
    current_slug = data.get("slug") or data.get("_current_slug")
    if staged.name:
        staged.slug = resolve_company_slug(staged.name, current_slug)
    if staged.country_id is None and staged.country_code:
        resolved = client.get_country_id(staged.country_code)
        if resolved is not None:
            staged.country_id = resolved
    validation = validate_company(staged)
    if not validation.ok:
        return {
            "ok": False,
            "errors": [f"{i.field}: {i.message}" for i in validation.errors()],
            "warnings": [f"{i.field}: {i.message}" for i in validation.warnings()],
        }

    company_id = staged.id
    if not company_id:
        return {"ok": False, "errors": ["Company staging JSON must include id for patch."]}

    payload = company_staging_to_patch_payload(staged)
    if not payload:
        return {"ok": False, "errors": ["No patch fields to apply."]}

    if dry_run:
        return {"ok": True, "dry_run": True, "company_id": company_id, "payload": payload}

    try:
        result = client.patch_company(company_id, payload)
    except Exception as exc:
        detail = str(exc)
        if hasattr(exc, "response") and exc.response is not None:
            try:
                detail = exc.response.text
            except Exception:
                pass
        return {"ok": False, "errors": [detail], "payload": payload}

    mark_processed("company", company_id)
    return {"ok": True, "dry_run": False, "company_id": company_id, "result": result}


def write_backfill_report(
    run_id: str,
    *,
    mode: str,
    company: dict[str, Any] | None = None,
    robots_staged: int = 0,
    robots_skipped: int = 0,
    import_summary: dict[str, Any] | None = None,
    notes: str = "",
) -> Path:
    STAGING_REPORTS.mkdir(parents=True, exist_ok=True)
    path = STAGING_REPORTS / f"{run_id}.md"
    lines = [
        f"# Research run {run_id}",
        "",
        f"- **Mode:** {mode}",
        f"- **Timestamp:** {datetime.now(timezone.utc).isoformat()}",
    ]
    if company:
        lines.append(f"- **Company:** {company.get('name')} (id={company.get('id')}, slug={company.get('slug')})")
    lines.extend([
        f"- **Robots staged:** {robots_staged}",
        f"- **Robots skipped:** {robots_skipped}",
    ])
    if import_summary:
        lines.extend([
            "",
            "## Import summary",
            f"- created: {import_summary.get('created_count', 0)}",
            f"- updated: {import_summary.get('updated_count', 0)}",
            f"- skipped: {import_summary.get('skipped_count', 0)}",
            f"- errors: {import_summary.get('error_count', 0)}",
        ])
    if notes:
        lines.extend(["", "## Notes", notes])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
