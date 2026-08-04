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
    normalize_field,
    snapshot,
)

# StagedRobot's write-side field name -> the API's read-side key for the same
# data, when they differ. `images` writes the gallery but RobotSerializer only
# echoes it back under `photos` (a SerializerMethodField; `images` is popped
# out of validated_data on save, never re-serialized under its own name) — so
# `_verify_persisted` was permanently blind for every media remedy on every
# company. Found live on Estun (2026-07-31): the same robot reported
# `few_photos fixed` six times over three days while its real photo count
# never moved, and because the loop stops at the first real change, the false
# "fixed" also silently blocked `missing_features`/`missing_specs` from ever
# being attempted on the same pass.
_FIELD_READ_ALIASES: dict[str, str] = {
    "images": "photos",
}


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
        from schema import StagedRobot

        # Re-fetch fresh rather than trusting the caller's `robot` dict: it was
        # read during the initial queue scan, which can be many minutes before
        # this specific flag's turn comes up (pagination + earlier flags in the
        # same pass). The write below submits the FULL merged payload, not just
        # this remedy's target fields — a stale snapshot means every OTHER field
        # rides along at its old value and can silently clobber a concurrent
        # writer's more recent change. Found live on AgileX (2026-08-01): a
        # manual sweep wrote real `features`, and a `missing_family`/
        # `video_mismatch` remedy running from a stale scan snapshot overwrote
        # it back to blank purely as a side effect of fixing an unrelated flag.
        try:
            fresh = ctx.client._get(f"robots/robots/{robot_id}/")
            if isinstance(fresh, dict) and fresh:
                robot = fresh
        except Exception:  # noqa: BLE001
            pass  # fall back to the caller's snapshot rather than fail the remedy

        base = _robot_api_to_staged(robot, ctx.company_slug, ctx.company_name)
        before = snapshot(base.to_dict(), watch)

        # A hand-verified hint (remedies/hints/<company_id>.json) takes priority over
        # automated discovery — it exists precisely because discovery underperformed
        # on this company (wrong nav, attribution landmines, CMS image names). It
        # flows through the SAME merge/diff/no-op/write/verify pipeline as a live
        # research result, just skipping the network call.
        hint = ctx.hint_for(robot_id)
        used_hint = hint is not None
        if used_hint:
            researched = StagedRobot.from_dict({"name": base.name, **hint})
        else:
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

        hint_tag = " (from hint)" if used_hint else ""

        if ctx.dry_run:
            return RemedyResult(
                action, FIXED, flag=flag, changed_fields=changed,
                detail=f"dry-run — not written{hint_tag}",
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
            detail=(verify_note if persisted is None else "") + hint_tag,
        )


    except Exception as exc:  # noqa: BLE001
        # Daily Gemini budget spent -> SKIPPED, never FAILED: blocked_actions()
        # counts FAILED (2 strikes permanently blocks the action for this robot
        # via the ledger), and a robot must not be punished forever because the
        # budget happened to run out on its turn. SKIPPED is ignored by the
        # blocker, so the remedy retries normally after the UTC-midnight reset.
        try:
            from spend_guard import SpendBudgetExceeded
            if isinstance(exc, SpendBudgetExceeded):
                return RemedyResult(
                    action, SKIPPED, flag=flag,
                    detail=f"daily Gemini budget spent — retry after UTC midnight: {exc}",
                )
        except ImportError:
            pass
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

    def _in_fresh(f: str) -> bool:
        return f in fresh or _FIELD_READ_ALIASES.get(f, "") in fresh

    def _fresh_value(f: str) -> Any:
        return fresh.get(f) if f in fresh else fresh.get(_FIELD_READ_ALIASES.get(f, ""))

    verifiable = [f for f in claimed if _in_fresh(f)]
    unverifiable = [f for f in claimed if not _in_fresh(f)]
    if not verifiable:
        return None, (
            "unverified: " + ",".join(unverifiable) +
            " not returned by the API (write-only staging alias?)"
        )
    after_server = {f: normalize_field(f, _fresh_value(f)) for f in verifiable}
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

        # Re-fetch fresh rather than trusting the caller's `robot` dict — same
        # stale-snapshot risk as run_reresearch (see its comment): this remedy
        # only intends to touch family_name/variant_label, but the write below
        # submits the whole merged payload, so a stale copy of any other field
        # can clobber a concurrent writer's more recent change.
        try:
            fresh = next((s for s in siblings if int(s.get("id") or 0) == robot_id), None)
            if fresh:
                robot = fresh
        except Exception:  # noqa: BLE001
            pass

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


def _subcategory_slug(ctx: RemedyContext, sub_category: Any) -> str:
    """API returns `sub_category` as a PK; the derivation needs its slug."""
    if isinstance(sub_category, dict):
        return str(sub_category.get("slug") or "")
    if not isinstance(sub_category, int):
        return ""
    try:
        for row in ctx.client.get_subcategories() or []:
            if row.get("id") == sub_category:
                return str(row.get("slug") or "")
    except Exception:  # noqa: BLE001 — a missing slug just weakens the derivation
        return ""
    return ""


def remedy_missing_category(robot: dict[str, Any], ctx: RemedyContext) -> RemedyResult:
    """Assign Category rows from the taxonomy the robot already carries.

    This does NOT re-research. `missing_category` counts the `categories` M2M
    (`quality.py`: `n_categories == 0`), and everything needed to fill it —
    movement types, sub-category, uses, industries, name, description — is
    already on the robot. Making it a network fix would gate the flag on the
    company having a reachable website, which is exactly how 317 pending robots
    got stuck with it in the first place.

    The previous version of this remedy forced `{"sub_category",
    "movement_type_keys"}`. Neither can change `n_categories` — `sub_category`
    is `RobotSubCategory` ("Applications"), a different model — so it reported
    FIXED while the flag stayed up, and the attempt ledger then blocked the
    retry. Categories are only ever ADDED here: `_set_m2m` in the importer skips
    a robot that already has some, so a curated assignment is never overwritten.
    """
    action, flag = "refresh_category", "missing_category"
    ctx.ensure()
    robot_id = int(robot.get("id") or 0)
    try:
        from robot_auto_research import _robot_api_to_staged
        from robot_categories import derive_category_slugs
        from schema import StagedRobot

        base = _robot_api_to_staged(robot, ctx.company_slug, ctx.company_name)
        watch = frozenset({"category_slugs"})
        before = snapshot(base.to_dict(), watch)

        slugs = derive_category_slugs(
            name=str(robot.get("name") or ""),
            text=" ".join(str(robot.get(f) or "") for f in ("description", "purpose", "features")),
            movement_type_keys=base.movement_type_keys,
            sub_category_slug=_subcategory_slug(ctx, robot.get("sub_category")),
            use_keys=base.use_keys,
            industry_keys=base.industry_keys,
            existing=base.category_slugs,
            # No fallback: this remedy reads stored fields only. A robot with no
            # taxonomy at all is an enrichment gap, and stamping it "Other" would
            # clear the chip while leaving the reviewer nothing to act on.
            fallback="",
        )
        if not slugs:
            return RemedyResult(
                action, NO_OP, flag=flag,
                detail="no movement type, sub-category, use, industry or name keyword "
                       "to classify from — needs enrichment first",
            )

        payload = base.to_dict()
        payload["category_slugs"] = slugs
        merged = StagedRobot.from_dict(payload)
        changed = diff_fields(before, snapshot(merged.to_dict(), watch))
        if not changed:
            return RemedyResult(action, NO_OP, flag=flag, detail=f"already categorised: {slugs}")
        if ctx.dry_run:
            return RemedyResult(action, FIXED, flag=flag, changed_fields=changed,
                                detail=f"dry-run — would set {slugs}")

        imp = _stage_and_import(merged, robot_id, ctx, replace_media=False)
        if not imp.get("ok"):
            return RemedyResult(action, FAILED, flag=flag, changed_fields=changed,
                                detail=f"import failed: {str(imp)[:200]}")

        # `category_slugs` is a write-only staging alias — the API returns
        # `categories` (display names) — so _verify_persisted cannot see it.
        # Check the real relation instead of accepting an unverified FIXED.
        try:
            fresh = ctx.client._get(f"robots/robots/{robot_id}/")
            landed = [c for c in (fresh.get("categories") or []) if c]
        except Exception as exc:  # noqa: BLE001
            return RemedyResult(action, FIXED, flag=flag, changed_fields=changed,
                                detail=f"unverified: re-read failed ({type(exc).__name__})")
        if not landed:
            return RemedyResult(action, FAILED, flag=flag, changed_fields=[],
                                detail=f"staged {slugs} but robot still has no categories")
        return RemedyResult(action, FIXED, flag=flag, changed_fields=changed,
                            detail=", ".join(str(c) for c in landed))
    except Exception as exc:  # noqa: BLE001
        return RemedyResult(action, FAILED, flag=flag, detail=f"{type(exc).__name__}: {exc}")


def remedy_missing_manufacturer_country(robot: dict[str, Any], ctx: RemedyContext) -> RemedyResult:
    """Fill the manufacturer's country — and fix the Company that caused it.

    `missing_manufacturer_country` is an ERROR-severity flag that used to sit in
    `UNFIXABLE_FLAGS`, so 351 pending robots carried a permanent red chip nobody
    could clear. It is not unfixable; it is just not a per-robot problem. A
    robot's manufacturer country IS its company's HQ country, and on 2026-07-31
    the split was 287 robots whose company also had no country against 54 whose
    company already did (pure propagation gap).

    So: resolve once, write the COMPANY as well as the robot. The next robot
    from the same manufacturer then takes the free path, and enrichment — which
    copies `company.country` onto everything it touches — stops producing new
    blanks at the source.
    """
    action, flag = "refresh_country", "missing_manufacturer_country"
    ctx.ensure()
    robot_id = int(robot.get("id") or 0)
    try:
        from company_country_resolve import resolve_company_country
        from robot_auto_research import _robot_api_to_staged
        from schema import StagedRobot

        company_code = (ctx.country_code or "").strip().upper()
        how = "company"
        if not company_code:
            if ctx._country_lookup is None:
                code, how = resolve_company_country(ctx.company_name, ctx.company_website)
                ctx._country_lookup = ((code or "").strip().upper(), how)
            company_code, how = ctx._country_lookup
        if not company_code:
            return RemedyResult(action, NO_OP, flag=flag,
                                detail=f"HQ country not determinable ({how})")

        base = _robot_api_to_staged(robot, ctx.company_slug, ctx.company_name)
        watch = frozenset({"manufacturer_country_code"})
        before = snapshot(base.to_dict(), watch)
        payload = base.to_dict()
        payload["manufacturer_country_code"] = company_code
        # The multi-country M2M is only ever set alongside the primary FK (see the
        # note in quality.py), so seeding it keeps the two consistent.
        payload["manufacturer_country_codes"] = company_code
        merged = StagedRobot.from_dict(payload)
        changed = diff_fields(before, snapshot(merged.to_dict(), watch))
        if not changed:
            return RemedyResult(action, NO_OP, flag=flag, detail=f"already set to {company_code}")
        if ctx.dry_run:
            return RemedyResult(action, FIXED, flag=flag, changed_fields=changed,
                                detail=f"dry-run — would set {company_code} [{how}]")

        # Backfill the Company first: it is the actual defect, and doing it here
        # means one resolution fixes every sibling robot instead of N lookups.
        company_note = ""
        if how != "company" and ctx.company_id:
            company_note = _write_company_country(ctx, company_code)

        imp = _stage_and_import(merged, robot_id, ctx, replace_media=False)
        if not imp.get("ok"):
            return RemedyResult(action, FAILED, flag=flag, changed_fields=changed,
                                detail=f"import failed: {str(imp)[:200]}")

        # Staged as `manufacturer_country_code`, returned as
        # `manufacturer_country_ref` — verify against the relation.
        try:
            fresh = ctx.client._get(f"robots/robots/{robot_id}/")
            ref = fresh.get("manufacturer_country_ref") or {}
            landed = str(ref.get("code") or "").upper() if isinstance(ref, dict) else ""
        except Exception as exc:  # noqa: BLE001
            return RemedyResult(action, FIXED, flag=flag, changed_fields=changed,
                                detail=f"unverified: re-read failed ({type(exc).__name__})")
        if landed != company_code:
            return RemedyResult(action, FAILED, flag=flag, changed_fields=[],
                                detail=f"staged {company_code} but robot reads {landed or 'blank'}")
        return RemedyResult(action, FIXED, flag=flag, changed_fields=changed,
                            detail=f"{company_code} [{how}]{company_note}")
    except Exception as exc:  # noqa: BLE001
        return RemedyResult(action, FAILED, flag=flag, detail=f"{type(exc).__name__}: {exc}")


def _write_company_country(ctx: RemedyContext, code: str) -> str:
    """Persist the resolved HQ country on the Company. Never raises."""
    try:
        country_id = ctx.client.resolve_country_id(code)
        if not country_id:
            return f" (company not updated: {code} not in Country table)"
        ctx.client._patch(f"companies/{ctx.company_id}/", {"country_id": country_id})
        fresh = ctx.client.get_company(ctx.company_id) or {}
        got = fresh.get("country")
        got_code = (got.get("code") if isinstance(got, dict) else got) or ""
        if str(got_code).upper() != code:
            return " (company write did not persist)"
        ctx.country_code = code
        return f" +company {ctx.company_id}"
    except Exception as exc:  # noqa: BLE001
        return f" (company update failed: {type(exc).__name__})"


def remedy_image_not_uploaded(robot: dict[str, Any], ctx: RemedyContext) -> RemedyResult:
    """Hero exists but was never uploaded to our CDN — trigger the server's
    copy-media job (the same internal endpoint the admin button uses). The
    server downloads, rehosts, stamps content_hash, generates variants, and
    hash-dedupes the gallery; nothing to research client-side."""
    import os

    import requests as _requests

    action, flag = "copy_media_upload", "image_not_uploaded"
    robot_id = int(robot.get("id") or 0)
    secret = os.environ.get("INTERNAL_API_SECRET") or ""
    if not secret:
        return RemedyResult(action, SKIPPED, flag=flag, detail="INTERNAL_API_SECRET not set")
    if ctx.dry_run:
        return RemedyResult(action, FIXED, flag=flag, changed_fields=["s3_image"],
                            detail="dry-run — would trigger copy-media")
    base = (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")
    try:
        resp = _requests.post(
            f"{base}/admin/robots/robot/content-queue/api/robot/{robot_id}/copy-media/",
            headers={"X-Internal-Secret": secret}, timeout=180,
        )
        if resp.status_code < 300:
            return RemedyResult(action, FIXED, flag=flag, changed_fields=["s3_image"],
                                detail="copy-media triggered ok")
        return RemedyResult(action, FAILED, flag=flag,
                            detail=f"copy-media HTTP {resp.status_code}: {resp.text[:120]}")
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
# Same engine, forced overwrite: re-research regenerates features via
# features_gen (distinct bullets, verified against the server's own duplicate
# checker), replacing the copied-description block that raised the flag.
remedy_features_duplicates_description = _make(
    "refresh_features", "features_duplicates_description", {"features"}
)

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
# `missing_category` is defined above as a real function, NOT via _make: it fills
# the `categories` M2M from stored taxonomy and needs no network at all.
# `sub_category`/`movement_type_keys` moved here from the old `missing_category`
# remedy so that capability is not lost — they are taxonomy fields, and this is
# the remedy that actually re-researches the page to refill them.
remedy_missing_taxonomy = _make(
    "refresh_taxonomy", "missing_taxonomy",
    {"use_keys", "industry_keys", "sub_category", "movement_type_keys"},
    watch={"use_keys", "industry_keys"},
)
