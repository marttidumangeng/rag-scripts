---
type: workflow
title: Huayan Robotics 1490 Full Enrichment Implementation Plan
status: approved
version: 1.1
owner: AI
last_updated: 2026-07-21
tags:
  - research
  - enrichment
  - huayan
---

# Huayan Robotics 1490 Full Enrichment Implementation Plan

## Goal

Reconcile company `1490` with Huayan Robotics' 42 current model-level products,
fully enrich supported non-media fields, and preserve moderation and media-rights
invariants.

## Architecture

- Keep immutable official facts in `huayan_1490_catalog.py`.
- Keep reconciliation, payload construction, apply, and verification in
  `fix_huayan_1490_robots.py`.
- Test catalog and pure payload behavior before mutation logic.
- Default to a mutation-free dry run.
- Apply only behind `--apply`.
- Reconcile by normalized model identity while enforcing known IDs.
- Create missing rows through bulk import, then detail-PATCH and GET-verify them.
- Produce a deterministic report that distinguishes success, errors, and partial
  writes.

## Global Constraints

- Company ID: `1490`.
- Canonical slug: `huayan-robotics`.
- Current catalog: exactly 42 unique model codes.
- Existing current records: 24 known model-to-ID mappings.
- Missing current records: 18.
- New records: `pending_review`.
- Preserve every existing moderation status and media value.
- Do not reject or unpublish S35, Echo shell `5302`, or STAR shell `5303`.
- Do not attach, hotlink, transform, download, or rehost Huayan media.
- Keep imageless current records blocked and report them under `media_blocked`.
- Do not infer model-specific Elfin-Li or S-Li numeric specifications.
- Prefer current Chinese S-series facts over conflicting stale English values.
- Do not commit unless explicitly requested.

## Current Catalog

### Families and Models

- Elfin: E03, E05, E05-L, E10, E10-L, E12, E15.
- Elfin-Pro: E03-Pro, E05-Pro, E05L-Pro, E10-Pro, E10L-Pro, E12-Pro,
  E15-Pro.
- Elfin-Ex: E05F, E10F, E10F-L, E12F, E15F.
- S: S20, S30, S40, S50, S60.
- Echo: Echo 3, Echo 5, Echo 15.
- HY: HY 3, HY 7, HY 15.
- STAR: STAR-S, STAR-L, STAR-M, STAR-H.
- Elfin-Li: E03Li, E05Li, E05Li-L, E10Li, E12Li, E15Li.
- S-Li: S20Li, S30Li.

Do not create standalone HR150, HR300, HR600, or HR1200 records. They are STAR
mobile bases, not complete independent robots.

### Known Existing IDs

- Elfin: E03 `5295`, E05-L `5296`, E05 `5297`, E10-L `5298`, E10 `5299`,
  E12 `5300`, E15 `5301`.
- Elfin-Pro: E03-Pro `3670`, E05-Pro `3671`, E05L-Pro `3672`, E10-Pro
  `3673`, E10L-Pro `3674`, E12-Pro `3675`, E15-Pro `3676`.
- Elfin-Ex: E05F `3683`, E10F `3684`, E10F-L `3685`, E12F `3686`, E15F
  `3687`.
- S: S20 `3677`, S30 `5205`, S40 `3680`, S50 `3681`, S60 `3682`.

Fail closed if any known model maps to another ID or a known ID maps to another
model.

### Retirement Recommendations

- `3679`: legacy S35, absent from current model tables.
- `5302`: published Echo family shell, superseded by model-level rows.
- `5303`: published STAR family shell, superseded by model-level rows.

This workflow reports these rows but does not mutate them.

### Typed-Fact Rules

- Map exact model columns to supported typed fields:
  - `weight_kg`
  - `payload_kg`
  - `reach_mm`
  - `dof`
  - `repeatability_mm`
  - `speed`
  - `runtime_minutes`
- Treat Echo and HY weights as upper bounds in Features; do not map them to
  exact typed weights.
- Map STAR speed in km/h and runtime in minutes.
- Keep every Elfin-Li and S-Li `typed` dictionary empty because the official
  page provides only series ranges.
- Record source conflicts:
  - S20 repeatability.
  - S40 reach.
  - S50 weight.

## Payload Contract

Every current model payload includes:

- canonical name and model/variant identity
- family key, name, URL, and product URL scope
- official description, application-based purpose, and Features
- availability
- manufacturer country and country relation
- family-appropriate categories, uses, industries, movement types, and tags
- official information-source URLs
- model-supported typed fields

Use taxonomy contracts:

- categories: API-supported names or identifiers
- uses, industries, movement types: API identifiers
- tags: exact catalog names, never integer IDs

Resolve every requested tag name against the tag catalog. Fail closed and report
the exact missing names if any requested name is unresolved.

New records also include:

- `status=pending_review`
- blank `image`, `images`, and `s3_image`
- the actionable Huayan image-permission note

## Reconciliation Workflow

1. Fetch all company `1490` records and detail representations.
2. Resolve China and assert the runtime country contract.
3. Resolve every requested tag name.
4. Build taxonomy from known family exemplars.
5. Enforce all 24 known model-to-ID mappings.
6. Reject duplicate normalized current codes and unexpected records.
7. Build 24 existing updates and 18 missing creates on the initial state.
8. Validate exact catalog count, family metadata, sources, purpose, typed fields,
   status, and no planned Huayan media.
9. Write a dry-run report without mutation.

## Apply Workflow

### Existing Current Records

For each existing current row:

1. GET immediately before PATCH.
2. Refuse status drift from the planned state.
3. PATCH factual fields and relations without media or status fields.
4. GET immediately after PATCH.
5. Verify:
   - status and media unchanged
   - exact family metadata
   - availability and manufacturer country
   - taxonomy and tag relations
   - official sources
   - exact purpose
   - every model-supported typed field
6. Record success only after every check passes.

### Missing Current Records

For each missing model:

1. Re-fetch and reconcile immediately before creation.
2. Skip creation if the normalized code now exists.
3. Bulk-import one imageless `pending_review` row with:
   - `skip_company_update=True`
   - `replace_media=False`
   - `replace_videos=False`
4. Capture the returned ID and action.
5. Detail-PATCH typed fields, family metadata, availability, country, taxonomy,
   tags, sources, and purpose.
6. GET and verify the complete expected factual state, status, permission note,
   and no media.
7. Record under `created` only after PATCH and verification succeed.
8. If creation succeeded but PATCH or verification failed, record ID, model,
   action, failed stage, and error under `partial_writes`.
9. Treat an import `updated` race result idempotently and report it separately
   under `create_race_updated`.

## Final Verification

After apply:

1. Fetch all company details.
2. Reconcile exactly 42 unique current model-level rows.
3. Verify no missing or unexpected current model.
4. Verify complete factual fields for every current row.
5. Verify all existing statuses and media are preserved.
6. Verify all new rows are `pending_review`, imageless, and carry the exact
   permission note.
7. Build `media_blocked` from every imageless current row in the final
   reconciliation.
8. Keep all retirement candidates unchanged.
9. Return failure when any error, partial write, or post-apply mismatch exists.

## Report Contract

The report includes:

- `company_id`
- `mode`
- `before_counts`
- `after_counts`
- `existing_updated`
- `created`
- `create_race_updated`
- `partial_writes`
- `retirement_candidates`
- `media_blocked`
- `source_conflicts`
- `errors`

Never list a partial write under a fully successful result.

## TDD and Verification

Use red-green-refactor for each behavior:

```powershell
python -m pytest scripts/research/tests/test_huayan_1490_catalog.py scripts/research/tests/test_fix_huayan_1490_robots.py scripts/research/tests/test_fix_huayan_1490_reconciliation.py scripts/research/tests/test_fix_huayan_1490_apply.py -q
python -m py_compile scripts/research/huayan_1490_catalog.py scripts/research/fix_huayan_1490_robots.py scripts/research/tests/test_huayan_1490_catalog.py scripts/research/tests/test_fix_huayan_1490_robots.py scripts/research/tests/test_fix_huayan_1490_reconciliation.py scripts/research/tests/test_fix_huayan_1490_apply.py
```

Read IDE diagnostics for all changed Huayan files and this plan.

Production commands require a separate explicit approval:

```powershell
python scripts/research/fix_huayan_1490_robots.py
python scripts/research/fix_huayan_1490_robots.py --apply
```

## Related

- [Huayan Full Enrichment Design](../specifications/huayan-1490-full-enrichment-design.md)
- [Catalog OEM Import](../playbooks/catalog-oem-import.md)
- [Production Manufacturer Import](../checklists/prod-manufacturer-import.md)
- [Robot Research Documentation](../index.md)
- [Research Docs Changelog](../log.md)
