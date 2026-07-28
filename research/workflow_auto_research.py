"""End-to-end automated research: stage robots (+ optional import)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import research_robots_for_company
from workflow_backfill import STAGING_REPORTS, write_backfill_report

RESEARCH_DIR = Path(__file__).resolve().parent


def auto_research_pipeline(
    company_id: int,
    *,
    client: ResearchApiClient | None = None,
    only_missing: bool = True,
    use_playwright: bool | None = None,
    use_stealth: bool | None = None,
    use_apify: bool | None = None,
    grounded: bool = False,
    apply_import: bool = False,
    created_by_id: int | None = None,
    patch: bool = True,
    status: str = "pending_review",
    force_fields: frozenset[str] = frozenset(),
    verify: bool = False,
    min_confidence: int = 50,
    strict_verify: bool = False,
) -> dict[str, Any]:
    """
    1. Auto-research robots for company → write staging JSON (images, videos, specs)
    2. Optionally AI-verify staged robots and quarantine mismatches (--verify)
    3. Optionally import via bulk-import API

    `force_fields` names fields that should be refreshed even if the DB already has a
    (possibly wrong) value for them — see `robot_auto_research._merge_staged`.
    `grounded` enables Gemini-grounded image/URL/video selection during research.
    """
    client = client or ResearchApiClient()
    created_by_id = resolve_created_by_id(created_by_id)

    research_summary = research_robots_for_company(
        company_id,
        client=client,
        only_missing=only_missing,
        use_playwright=use_playwright,
        use_stealth=use_stealth,
        use_apify=use_apify,
        grounded=grounded,
        force_fields=force_fields,
    )

    import_summary: dict[str, Any] | None = None
    verify_summary: dict[str, Any] | None = None
    company_slug = research_summary.get("company_slug", "")
    staging_dir = RESEARCH_DIR / "staging" / "robots" / company_slug

    # Only THIS run's staged files may be imported — the per-company staging dir
    # is persistent, and stale/manually edited JSON from earlier runs must not
    # ride along on an automated import.
    repo_root = RESEARCH_DIR.parent.parent
    staged_paths = [
        repo_root / str(row["staging_file"])
        for row in research_summary.get("results", [])
        if row.get("staging_file")
    ]

    if verify and staged_paths:
        from verify_staging import verify_staging

        company = client.get_company(company_id)
        verify_summary = verify_staging(
            staging_dir,
            company_name=str(company.get("name") or ""),
            company_website=str(company.get("website") or ""),
            min_confidence=min_confidence,
            strict=strict_verify,
        )

    if apply_import:
        # The verify gate moves quarantined files aside, so drop any staged
        # path that no longer exists before importing.
        importable = [p for p in staged_paths if p.is_file()]
        if importable:
            import_summary = import_staging(
                importable,
                client=client,
                patch=patch,
                status=status,
                dry_run=False,
                created_by_id=created_by_id,
                replace_media="image" in force_fields,
            )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = write_backfill_report(
        run_id,
        mode="auto-research",
        company={"id": company_id, "slug": company_slug},
        robots_staged=research_summary.get("robots_researched", 0),
        import_summary=import_summary,
        notes=_format_report_notes(research_summary, import_summary, verify_summary),
    )

    return {
        "ok": research_summary.get("ok", False) and (import_summary is None or import_summary.get("ok", False)),
        "research": research_summary,
        "verify": verify_summary,
        "import": import_summary,
        "report": str(report_path.relative_to(RESEARCH_DIR.parent.parent)).replace("\\", "/"),
        "staging_dir": str(staging_dir.relative_to(RESEARCH_DIR.parent.parent)).replace("\\", "/"),
    }


def _format_report_notes(
    research: dict[str, Any],
    imp: dict[str, Any] | None,
    verify: dict[str, Any] | None = None,
) -> str:
    lines = []
    for row in research.get("results", []):
        lines.append(
            f"- {row.get('name')}: images={row.get('images_count')}, videos={row.get('videos_count')}, "
            f"file={row.get('staging_file')}"
        )
    if research.get("errors"):
        lines.append("Errors: " + "; ".join(research["errors"]))
    if verify:
        counts = verify.get("counts", {})
        lines.append(
            f"Verify: passed={counts.get('passed', 0)} quarantined={counts.get('quarantined', 0)} "
            f"unverifiable={counts.get('unverifiable', 0)} errors={counts.get('errors', 0)}"
        )
    if imp:
        lines.append(
            f"Import: created={imp.get('created_count', 0)} updated={imp.get('updated_count', 0)} "
            f"errors={imp.get('error_count', 0)}"
        )
    return "\n".join(lines)
