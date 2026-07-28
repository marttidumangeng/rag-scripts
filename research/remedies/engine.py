"""The shared remedy engine + the concrete per-flag remedies.

Every hand-written ``fix_*.py`` in scripts/research does the same three moves:
fetch the robot, re-research it against the OEM site, write the result back.
All 122 of them import ``api_client``; 51 import ``import_staging``; 35 import
``robot_auto_research``. This module is that pattern, extracted once, with the
per-flag variation reduced to *which fields may be overwritten*.

``run_reresearch`` is the whole engine:

    snapshot(watch_fields) -> research -> merge onto CURRENT DB state
      -> diff -> NO_OP (write nothing) | FIXED (stage + patch import)

Merging onto the current DB state is what makes ``force_overwrite`` safe: the
staged payload always carries every existing value forward, so an overwrite
patch can never blank a field the researcher happened not to find.
"""

from __future__ import annotations

import json
import traceback
from typing import Any

from .base import (
    FAILED,
    FIXED,
    NO_OP,
    SKIPPED,
    RemedyContext,
    RemedyResult,
    diff_fields,
    snapshot,
)


def _stage_and_import(merged: Any, robot_id: int, ctx: RemedyContext, *, replace_media: bool) -> dict[str, Any]:
    """Write the merged payload to staging and patch-import it."""
    from import_staging import import_staging

    path = ctx.staging_dir / f"robot_{robot_id}.json"
    path.write_text(
        json.dumps([merged.to_dict()], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return import_staging(
        path,
        client=ctx.client,
        patch=True,
        # A remedy exists to correct a WRONG value, so it must be allowed to
        # overwrite. Safe because `merged` starts from the robot's current state.
        force_overwrite=True,
        replace_media=replace_media,
        status=ctx.status,
        batch_size=1,
        skip_company_update=True,
        dry_run=False,
        created_by_id=ctx.created_by_id,
    )


def run_reresearch(
    robot: dict[str, Any],
    ctx: RemedyContext,
    *,
    action: str,
    flag: str,
    force_fields: frozenset[str],
    watch_fields: frozenset[str] | None = None,
    replace_media: bool = False,
    vision: bool = False,
) -> RemedyResult:
    """Re-research one robot and write back ONLY if watched fields changed.

    `force_fields` are the fields this remedy may overwrite even when already
    populated. `watch_fields` (default: force_fields) are the fields compared to
    decide fixed-vs-no-op.
    """
    watch = watch_fields or force_fields
    ctx.ensure()
    robot_id = int(robot.get("id") or 0)

    if not ctx.company_website:
        return RemedyResult(action, SKIPPED, flag=flag, detail="company has no website — cannot re-research")

    try:
        from robot_auto_research import _merge_staged, _robot_api_to_staged

        base = _robot_api_to_staged(robot, ctx.company_slug, ctx.company_name)
        before = snapshot(base.to_dict(), watch)

        researched = ctx.get_researcher(vision=vision).research_robot(
            robot,
            company_slug=ctx.company_slug,
            company_name=ctx.company_name,
            company_website=ctx.company_website,
            manufacturer_country_code=ctx.country_code,
            # When the stored URL is the thing under repair, don't anchor on it.
            trust_stored_url="url" not in force_fields,
            refresh_description="description" in force_fields,
            evidence=ctx.evidence,
        )
        if researched is None:
            return RemedyResult(action, FAILED, flag=flag, detail="target_not_found on OEM site")

        merged = _merge_staged(base, researched, force_fields=force_fields)
        merged = _strip_quarantined(base, merged)
        after = snapshot(merged.to_dict(), watch)
        changed = diff_fields(before, after)

        # --- the anti-waste guard: nothing new, so never write or retry ---
        if not changed:
            return RemedyResult(
                action, NO_OP, flag=flag,
                detail="re-research produced no new value for " + ",".join(sorted(watch)),
            )

        if ctx.dry_run:
            return RemedyResult(
                action, FIXED, flag=flag, changed_fields=changed,
                detail="dry-run — not written",
            )

        imp = _stage_and_import(merged, robot_id, ctx, replace_media=replace_media)
        if not imp.get("ok"):
            return RemedyResult(
                action, FAILED, flag=flag, changed_fields=changed,
                detail=f"import failed: {str(imp)[:200]}",
            )

        # --- persistence check: a 200 from the import does NOT mean the value landed ---
        # The bulk importer silently re-routes some staged fields (e.g. it packs
        # payload_kg/reach_mm into `notes` instead of their real columns), and any field
        # missing from RobotSerializer.Meta.fields is dropped without error. Reporting
        # FIXED off the staged diff alone therefore produces false successes — and a
        # false FIXED is worse than a NO_OP because it hides a broken write path.
        persisted, verify_note = _verify_persisted(robot_id, ctx, changed, before)
        if persisted is False:
            return RemedyResult(
                action, FAILED, flag=flag, changed_fields=[],
                detail=f"write did not persist ({verify_note}) — staged {','.join(changed)}",
            )
        return RemedyResult(
            action, FIXED, flag=flag, changed_fields=changed,
            detail=verify_note if persisted is None else "",
        )


    except Exception as exc:  # noqa: BLE001
        return RemedyResult(
            action, FAILED, flag=flag,
            detail=f"{type(exc).__name__}: {exc} | {traceback.format_exc()[-200:]}",
        )


def _strip_quarantined(base: Any, merged: Any) -> Any:
    """Restore quarantined fields to their pre-research values.

    `_merge_staged` fills every blank field from the research result, not just the
    remedy's target, so an unreliable field can ride along on an unrelated fix and
    land in prod recorded as something else. Reverting them here keeps a remedy's
    write confined to data we actually trust.
    """
    from .registry import QUARANTINED_FIELDS

    if not QUARANTINED_FIELDS:
        return merged
    from schema import StagedRobot

    base_data = base.to_dict()
    data = merged.to_dict()
    changed = False
    for name in QUARANTINED_FIELDS:
        if data.get(name) != base_data.get(name):
            data[name] = base_data.get(name)
            changed = True
    return StagedRobot.from_dict(data) if changed else merged


def _verify_persisted(
    robot_id: int,
    ctx: RemedyContext,
    claimed: list[str],
    before: dict[str, Any],
) -> tuple[bool | None, str]:
    """Confirm the fields this remedy CLAIMS it changed actually landed server-side.

    Two traps this guards against, both hit in prod on 2026-07-26 (robot 5049):
      * checking "did ANY watched field change" passes when some OTHER field moved —
        the remedy reported movement_type_keys fixed while sub_category was what
        actually changed;
      * some staged names are write-only aliases the API never returns
        (`movement_type_keys` maps to `movement_type`), so they read blank on both
        sides and can never register as changed. Silently treating that as success
        is exactly the serializer-gate bug class.

    Returns (True, note) persisted, (False, reason) definitely not, (None, note)
    when nothing could be checked — the caller keeps FIXED but carries the caveat.
    """
    try:
        fresh = ctx.client._get(f"robots/robots/{robot_id}/")
    except Exception as exc:  # noqa: BLE001
        return None, f"unverified: re-read failed ({type(exc).__name__})"
    if not isinstance(fresh, dict) or not fresh:
        return None, "unverified: empty re-read"

    verifiable = [f for f in claimed if f in fresh]
    unverifiable = [f for f in claimed if f not in fresh]
    if not verifiable:
        return None, (
            "unverified: " + ",".join(unverifiable) +
            " not returned by the API (write-only staging alias?)"
        )
    after_server = snapshot(fresh, frozenset(verifiable))
    landed = diff_fields({k: before.get(k) for k in verifiable}, after_server)
    if landed:
        note = ""
        if unverifiable:
            note = "partly unverified: " + ",".join(unverifiable) + " not returned by the API"
        return True, note
    return False, "claimed fields unchanged server-side: " + ",".join(verifiable)


# ---------------------------------------------------------------------------
# Concrete remedies — one per quality flag. Thin by design: the variation
# between them is only which fields may be overwritten.
# ---------------------------------------------------------------------------

def remedy_missing_family(robot: dict[str, Any], ctx: RemedyContext) -> RemedyResult:
    """Fill family_name/variant_label from the company's own catalogue.

    Unlike the other remedies this does not re-research a page: family is a property
    of the model LINE-UP, so the evidence is the company's other robots. Enrichment
    also captures the vendor's own series wording when a page exposes it
    (`web_extract.extract_series_hint`); this is the floor for vendors that don't.

    Writes only `family_name`/`variant_label` — `family_key` is derived server-side by
    `robots.family.resolve_import_family_metadata`, which is why this goes through the
    import path rather than a bare PATCH.
    """
    action, flag = "refresh_family", "missing_family"
    ctx.ensure()
    robot_id = int(robot.get("id") or 0)
    try:
        from family_infer import infer_families
        from robot_auto_research import _robot_api_to_staged
        from schema import StagedRobot

        siblings = ctx.client.list_robots_for_company(ctx.company_id)
        hit = infer_families(siblings).get(robot_id)
        if not hit:
            # No sibling shares this robot's prefix — a genuine one-off has no family,
            # and inventing one would be worse than leaving it blank.
            return RemedyResult(action, NO_OP, flag=flag,
                                detail="no sibling shares this name prefix — not a family")

        base = _robot_api_to_staged(robot, ctx.company_slug, ctx.company_name)
        before = snapshot(base.to_dict(), frozenset({"family_name", "variant_label"}))
        payload = base.to_dict()
        payload["family_name"] = hit["family_name"]
        payload["variant_label"] = hit["variant_label"]
        merged = StagedRobot.from_dict(payload)
        after = snapshot(merged.to_dict(), frozenset({"family_name", "variant_label"}))
        changed = diff_fields(before, after)
        if not changed:
            return RemedyResult(action, NO_OP, flag=flag, detail="family already correct")
        if ctx.dry_run:
            return RemedyResult(action, FIXED, flag=flag, changed_fields=changed,
                                detail=f"dry-run — would set {hit['family_name']}/{hit['variant_label'] or 'base'}")

        imp = _stage_and_import(merged, robot_id, ctx, replace_media=False)
        if not imp.get("ok"):
            return RemedyResult(action, FAILED, flag=flag, changed_fields=changed,
                                detail=f"import failed: {str(imp)[:200]}")
        persisted, note = _verify_persisted(robot_id, ctx, changed, before)
        if persisted is False:
            return RemedyResult(action, FAILED, flag=flag, changed_fields=[],
                                detail=f"write did not persist ({note})")
        return RemedyResult(action, FIXED, flag=flag, changed_fields=changed,
                            detail=note if persisted is None else f"{hit['family_name']}/{hit['variant_label'] or 'base'}")
    except Exception as exc:  # noqa: BLE001
        return RemedyResult(action, FAILED, flag=flag, detail=f"{type(exc).__name__}: {exc}")


def _make(action: str, flag: str, force: set[str], *, watch: set[str] | None = None, media: bool = False):
    # Media remedies need the vision fallback: filename matching finds nothing on
    # OEMs with CMS/date/hash image names, so pixels are the only remaining signal.
    def _remedy(robot: dict[str, Any], ctx: RemedyContext) -> RemedyResult:
        return run_reresearch(
            robot, ctx,
            action=action, flag=flag,
            force_fields=frozenset(force),
            watch_fields=frozenset(watch or force),
            replace_media=media,
            vision=media,
        )
    _remedy.__name__ = f"remedy_{flag}"
    _remedy.__doc__ = f"Remedy for `{flag}`: re-research and overwrite {sorted(force)}."
    return _remedy


# Media — replace the hero/photos (needs replace_media so the server swaps them).
remedy_missing_image = _make("refresh_media", "missing_image", {"image", "images"}, media=True)
remedy_image_mismatch = _make("refresh_media", "image_mismatch", {"image", "images"}, media=True)
remedy_image_dead = _make("refresh_media", "image_dead", {"image", "images"}, media=True)
remedy_few_photos = _make("refresh_media", "few_photos", {"images"}, media=True)

# Source URL — never anchor on the stored (broken) URL; `sources` moves with it.
remedy_missing_url = _make("refresh_url", "missing_url", {"url", "sources"})
remedy_url_dead = _make("refresh_url", "url_dead", {"url", "sources"})
remedy_malformed_url = _make("refresh_url", "malformed_url", {"url", "sources"})
remedy_url_domain_mismatch = _make("refresh_url", "url_domain_mismatch", {"url", "sources"})
remedy_url_content_mismatch = _make("refresh_url", "url_content_mismatch", {"url", "sources"})

# Narrative — purpose is derived from description, so they refresh together
# (refreshing one without the other strands a stale purpose).
remedy_missing_description = _make("refresh_description", "missing_description", {"description", "purpose"})
remedy_short_description = _make("refresh_description", "short_description", {"description", "purpose"})
remedy_content_contradiction = _make("refresh_description", "content_contradiction", {"description", "purpose"})
remedy_missing_purpose = _make("refresh_description", "missing_purpose", {"purpose"})
remedy_purpose_duplicates_description = _make(
    "refresh_description", "purpose_duplicates_description", {"purpose"}
)
remedy_missing_features = _make("refresh_features", "missing_features", {"features"})

# Video
remedy_missing_video = _make("refresh_video", "missing_video", {"video_urls"})
remedy_video_mismatch = _make("refresh_video", "video_mismatch", {"video_urls"})

# Structured data
remedy_missing_specs = _make(
    "refresh_specs", "missing_specs",
    {"payload_kg", "reach_mm", "weight_kg", "dof", "dimensions_mm",
     "length_mm", "width_mm", "height_mm"},
)
remedy_missing_release_year = _make("refresh_release_year", "missing_release_year", {"release_year"})
remedy_missing_tags = _make("refresh_tags", "missing_tags", {"tags"})
remedy_missing_category = _make("refresh_taxonomy", "missing_category", {"sub_category", "movement_type_keys"})
remedy_missing_taxonomy = _make("refresh_taxonomy", "missing_taxonomy", {"use_keys", "industry_keys"})
