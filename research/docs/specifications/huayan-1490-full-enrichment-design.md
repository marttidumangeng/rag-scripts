---
type: specification
title: Huayan Robotics 1490 Full Enrichment Design
status: approved
version: 1.0
owner: AI
last_updated: 2026-07-21
tags:
  - research
  - enrichment
  - huayan
---

# Huayan Robotics 1490 Full Enrichment Design

## Purpose

Reconcile RobotAIGeek company 1490 with Huayan Robotics' current 42-model
official catalog and fully enrich all supported non-media fields.

## Scope

- Audit and update the 24 existing current model-level records.
- Create 18 missing current model-level records as `pending_review`.
- Audit the legacy S35 record and the published Echo and STAR family shells.
- Preserve existing moderation states during enrichment.
- Produce explicit retirement recommendations for unsupported legacy or family-shell records.

## Official Sources

- Current Chinese catalog: [Huayan Robotics](https://www.huayan-robotics.com/)
- English catalog: [Huayan Robotics global](https://www.huayan-robotics.net/)
- Elfin: [Elfin collaborative robot](https://www.huayan-robotics.net/elfin-collaborative-robot)
- Elfin-Pro: [Elfin-Pro collaborative robot](https://www.huayan-robotics.net/elfin-pro-collaborative-robot)
- Elfin-Ex: [Elfin-Ex collaborative robot](https://www.huayan-robotics.net/elfin-ex-explosion-proof-collaborative-robot)
- S series: [Current S series](https://www.huayan-robotics.com/s)
- Echo and HY: [Seven-axis arms](https://www.huayan-robotics.net/7-axis-humanoid-robotic-arm)
- STAR: [STAR mobile manipulators](https://www.huayan-robotics.net/star-mobile-manipulator)
- Elfin-Li and S-Li: [Lithium-battery series](https://www.huayan-robotics.com/li)

## Catalog Reconciliation

### Existing Current Models

- Elfin: E03, E05, E05-L, E10, E10-L, E12, E15
- Elfin-Pro: E03-Pro, E05-Pro, E05L-Pro, E10-Pro, E10L-Pro, E12-Pro, E15-Pro
- Elfin-Ex: E05F, E10F, E10F-L, E12F, E15F
- S series: S20, S30, S40, S50, S60

Normalize hyphenated S-series names to Huayan's current `S20`–`S60` format.

### Missing Current Models

- Echo: Echo 3, Echo 5, Echo 15
- HY: HY 3, HY 7, HY 15
- STAR: STAR-S, STAR-L, STAR-M, STAR-H
- Elfin-Li: E03Li, E05Li, E05Li-L, E10Li, E12Li, E15Li
- S-Li: S20Li, S30Li

### Retirement Candidates

- S35: absent from current model tables; retain until a separate moderation decision.
- Echo 7-Axis Humanoid Arm Series: published family shell superseded by six model records.
- STAR Mobile Manipulator: published family shell superseded by four model records.

Do not create standalone HR150, HR300, HR600, or HR1200 records. Huayan documents
them as STAR mobile bases rather than complete independent robots.

## Enrichment Requirements

For every current model:

- Correct model name, description, and application-based purpose.
- Availability status based on the current official catalog.
- Manufacturer country and complete categories, uses, industries, and movement types.
- Family-appropriate tags: remove unrelated AGV, Drone, Autonomous, and Humanoid
  tags from Elfin, Elfin-Pro, and Elfin-Ex while retaining legitimate humanoid-arm
  classification for Echo and HY models.
- Family key, name, URL, model/variant metadata, and product URL scope.
- Every citeable typed specification from the matching official model column.
- Official information-source URLs.
- Exact-model or clearly labeled official family videos where available.
- Documented dead searches for fields absent from current official sources.

The current Chinese S-series table takes precedence over stale English values.
Record conflicts for S20 repeatability, S40 reach, and S50 weight.

## Media Policy

Huayan publishes exact model images, but no reusable-media license or written
republication permission was found.

- Do not download, hotlink, copy, crop, or rehost Huayan images.
- Preserve existing media unless it is demonstrably wrong or duplicated.
- Create missing models without primary images and add an actionable licensing note.
- Keep every imageless model blocked from approval.
- Link or embed official YouTube videos only through YouTube; do not rehost video files.
- Request written image permission from `marketing@huayan-robotics.com` or
  `marketing.oversea@huayan-robotics.com`.

## Data Flow

1. Fetch all company 1490 records and live taxonomy/tag catalogs.
2. Map existing records to the 42-model official catalog by normalized model code.
3. Build curated records from official model tables and family pages.
4. Validate model ownership, family uniqueness, typed specifications, and sources.
5. Dry-run all updates and creations with moderation-state invariants.
6. Apply existing-record patches and create missing records as `pending_review`.
7. Reapply typed fields, availability, and family metadata after import.
8. Run deterministic quality and moderation checks.
9. Produce a model-level readiness and blocker report.

## Failure Handling

- Refuse a specification when current official sources conflict and no source is authoritative.
- Refuse media without explicit reuse permission.
- Stop on model-count, model-key, or family-key collisions.
- Do not change an existing status during enrichment.
- Do not reject or unpublish retirement candidates without a separate moderation instruction.
- Report partial API writes explicitly and make the workflow safe to retry.

## Verification

- Exactly 42 current model-level records are represented after reconciliation.
- No duplicate normalized model codes or cross-family key collisions; siblings
  share one consistent family key.
- Existing status values remain unchanged.
- All 18 new records are `pending_review`.
- Every current record has family metadata, availability, taxonomy, sources, and distinct purpose text.
- Typed specifications match the correct official model column.
- No new Huayan image is attached or copied.
- Every imageless record has an actionable licensing note and approval blocker.

## Related

- [Robot Research Documentation](../index.md)
- [Catalog OEM Import](../playbooks/catalog-oem-import.md)
- [Production Manufacturer Import](../checklists/prod-manufacturer-import.md)
- [Research Docs Changelog](../log.md)
