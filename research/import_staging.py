"""Import validated staging JSON to the bulk-import API."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from api_client import ResearchApiClient
from citations import sync_information_sources
from map_to_bulk_import import staging_robots_to_bulk_import_rows
from validate_staging import validate_robot_batch
from workflow_backfill import load_config


def resolve_created_by_id(explicit: int | None = None) -> int | None:
    """CLI flag > RESEARCH_CREATED_BY_ID env > config.json created_by_id."""
    if explicit:
        return explicit
    env_val = os.environ.get("RESEARCH_CREATED_BY_ID", "").strip()
    if env_val.isdigit():
        return int(env_val)
    config_val = load_config().get("created_by_id")
    if config_val:
        return int(config_val)
    return None


def load_json_robots(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "robots" in raw:
        robots = raw["robots"]
        return robots if isinstance(robots, list) else []
    if isinstance(raw, dict) and raw.get("name"):
        return [raw]
    raise ValueError(f"Unrecognized JSON format in {path}")


def collect_robot_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".json" else []
    if target.is_dir():
        # Underscore-prefixed files are metadata, not robot records
        # (e.g. _verification_report.json written by the --verify step).
        return sorted(p for p in target.glob("*.json") if not p.name.startswith("_"))
    return []


def _import_batch_with_retry(
    client: ResearchApiClient,
    batch: list[dict[str, Any]],
    *,
    patch: bool,
    force_overwrite: bool,
    status: str,
    skip_company_update: bool,
    created_by_id: int | None,
    replace_media: bool,
) -> dict[str, Any]:
    """Post one batch; on gateway timeout split batch and retry smaller."""
    update_existing = patch or force_overwrite
    patch_existing = patch and not force_overwrite
    try:
        return client.bulk_import_robots(
            batch,
            update_existing=update_existing,
            patch_existing=patch_existing,
            status=status,
            skip_company_update=skip_company_update,
            created_by_id=created_by_id,
            replace_media=replace_media,
        )
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        if status_code not in (502, 503, 504) or len(batch) <= 1:
            raise
        mid = max(1, len(batch) // 2)
        left = _import_batch_with_retry(
            client, batch[:mid], patch=patch, force_overwrite=force_overwrite, status=status,
            skip_company_update=skip_company_update, created_by_id=created_by_id,
            replace_media=replace_media,
        )
        time.sleep(1)
        right = _import_batch_with_retry(
            client, batch[mid:], patch=patch, force_overwrite=force_overwrite, status=status,
            skip_company_update=skip_company_update, created_by_id=created_by_id,
            replace_media=replace_media,
        )
        merged = {
            "created_count": left.get("created_count", 0) + right.get("created_count", 0),
            "updated_count": left.get("updated_count", 0) + right.get("updated_count", 0),
            "skipped_count": left.get("skipped_count", 0) + right.get("skipped_count", 0),
            "error_count": left.get("error_count", 0) + right.get("error_count", 0),
            "results": (left.get("results") or []) + (right.get("results") or []),
        }
        return merged


# The "easy win" fields a NEW robot must carry at least one of to be worth
# importing. A row with none of these is a skeleton: it costs a reviewer's
# attention, a remediation slot, and paid re-research calls, and small
# companies never reach the top of the busiest-first remediation queue — so
# skeletons rot in To Review indefinitely (robot 6717 "SWR – TIGMIG",
# 2026-08-02: imported with NONE of these, untouched for 2 days, unapprovable).
_EASY_FIELDS = (
    "features", "purpose", "tags", "use_keys", "industry_keys",
    "category_slugs", "sub_category_slug",
)


def _is_skeleton(rec: dict[str, Any]) -> bool:
    """True when a staged row has NONE of the easy fields — enrichment either
    never ran on it or entirely failed. Only blocks CREATES (see call site)."""
    for f in _EASY_FIELDS:
        v = rec.get(f)
        if isinstance(v, str) and v.strip():
            return False
        if isinstance(v, (list, tuple)) and len(v) > 0:
            return False
    return True


def import_staging(
    target: Path | list[Path],
    *,
    client: ResearchApiClient | None = None,
    patch: bool = False,
    status: str = "pending_review",
    batch_size: int = 50,
    dry_run: bool = True,
    skip_company_update: bool = False,
    created_by_id: int | None = None,
    replace_media: bool = False,
    force_overwrite: bool = False,
    block_skeletons: bool = False,
    allow_skeletons_env: str = "IMPORT_ALLOW_SKELETONS",
) -> dict[str, Any]:
    """`target` may be a staging dir, a single JSON file, or an explicit list of
    files — pipelines pass the current run's staged files so stale JSON left in
    the persistent per-company staging dir is never re-imported implicitly.

    block_skeletons: hold back rows with none of the easy fields (features,
    purpose, tags, uses/industries, category) instead of creating unapprovable
    shells in To Review. Discovery-import paths pass True — they're the only
    paths that create NET-NEW robots from scratch. Patch paths (enrichment,
    remedies) must NOT pass it: their rows carry current DB state, and a robot
    whose DB fields are legitimately still sparse must remain patchable.
    Escape hatch for a deliberate skeleton import: set IMPORT_ALLOW_SKELETONS=1.
    """
    client = client or ResearchApiClient()
    created_by_id = resolve_created_by_id(created_by_id)
    if isinstance(target, (list, tuple)):
        files = [f for t in target for f in collect_robot_files(Path(t))]
    else:
        files = collect_robot_files(target)
    if not files:
        return {"ok": False, "errors": [f"No JSON files found at {target}"]}

    records: list[dict[str, Any]] = []
    for fpath in files:
        records.extend(load_json_robots(fpath))

    held_skeletons: list[str] = []
    if block_skeletons and os.environ.get(allow_skeletons_env, "").lower() not in ("1", "true", "yes"):
        keep: list[dict[str, Any]] = []
        for rec in records:
            # Features are MANDATORY for new discovery rows (Martti, 2026-08-03:
            # "There can be no 'No features'... from Discovery"). The staging
            # writers promote description->features, so a blank here means the
            # page yielded neither — not worth a review slot.
            no_features = not str(rec.get("features") or "").strip()
            if _is_skeleton(rec) or no_features:
                held_skeletons.append(str(rec.get("name") or "?"))
            else:
                keep.append(rec)
        if held_skeletons:
            print(
                f"  SKELETON GATE: holding back {len(held_skeletons)} row(s) with no "
                f"features/purpose/tags/taxonomy — enrich them in staging first, or set "
                f"{allow_skeletons_env}=1 to force: {', '.join(held_skeletons[:8])}"
                + (" …" if len(held_skeletons) > 8 else ""),
                flush=True,
            )
        records = keep
        if not records:
            return {
                "ok": True, "robot_count": 0, "held_skeletons": held_skeletons,
                "created_count": 0, "updated_count": 0, "skipped_count": 0, "error_count": 0,
            }

    validation = validate_robot_batch(records)
    if not validation.ok:
        return {
            "ok": False,
            "errors": [f"{i.field}: {i.message}" for i in validation.errors()],
            "warnings": [f"{i.field}: {i.message}" for i in validation.warnings()],
        }

    rows = staging_robots_to_bulk_import_rows(records)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "robot_count": len(rows),
            "patch": patch,
            "status": status,
            "created_by_id": created_by_id,
            "sample": rows[:2],
            "warnings": [f"{i.field}: {i.message}" for i in validation.warnings()],
        }

    totals = {"created_count": 0, "updated_count": 0, "skipped_count": 0, "error_count": 0}
    all_results: list[dict[str, Any]] = []

    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        data = _import_batch_with_retry(
            client,
            batch,
            patch=patch,
            force_overwrite=force_overwrite,
            status=status,
            skip_company_update=skip_company_update,
            created_by_id=created_by_id,
            replace_media=replace_media,
        )
        for key in totals:
            totals[key] += data.get(key, 0)
        all_results.extend(data.get("results", []))

    # Interim provenance trail while research/discovery is still in flight: sync
    # whatever citations we can parse out of url/notes into RobotInformationSource
    # (see citations.py). Best-effort — a sync failure must not fail the import.
    for row in all_results:
        rid = row.get("id")
        if not rid or row.get("action") not in ("created", "updated"):
            continue
        try:
            sync_information_sources(client, rid)
        except Exception as exc:
            row["citation_sync_error"] = str(exc)

    return {
        # A batch with failed rows is not a successful import — callers use this
        # for exit codes and scheduler success, so partial failure must show.
        "ok": totals["error_count"] == 0,
        "dry_run": False,
        "created_by_id": created_by_id,
        **totals,
        "held_skeletons": held_skeletons,
        "results": all_results,
        "warnings": [f"{i.field}: {i.message}" for i in validation.warnings()],
    }
