---
type: log
title: Needs Cleanup Full Enrichment Report
status: complete
version: 2.1
owner: AI
last_updated: 2026-07-21
tags:
  - content-queue
  - full-enrichment
  - needs-cleanup
---

# Needs Cleanup Full Enrichment Report

This report supersedes the retracted overnight gate-fill report. Every retained
robot below received a curated OEM PDP, catalog, datasheet, technical-guide, or
regulatory-document pass. Citeable typed values were applied; absent values have
documented dead searches.

## Outcome

- Companies fully processed: **13**
- Fully enriched pending robots ready to approve: **43**
- Ready in complete-company queues: **5**
- Ready in partial-company allowlists: **38**
- Held pending records: **24**
- Duplicate, solution, workflow, software, alias, or category shells rejected: **46**
- Published by this remediation: **20**

## Ready Companies

| Company | ID | Ready | Verification |
|---------|---:|------:|--------------|
| Yamaha Robotics | 1484 | 5 | Typed core specs 5/5; unique CDN heroes 5/5; official videos cleaned |

Total ready in complete-company queues: **5**.

## Approved Since This Report

| Company | ID | Published | Verification |
|---------|---:|----------:|--------------|
| Gurki | 974 | 8 | 0 pending |
| Intamsys | 1073 | 5 | 0 pending |
| Intuitive Surgical | 52 | 3 new | 5 total published / 0 pending |
| inVia Robotics | 397 | 1 new | Duplicate cleanup required: keep enriched 2977; reject legacy 272 |
| 6 River Systems | 1373 | 1 | 0 pending |
| Auris Health | 1511 | 1 | 0 pending |
| Infinium Robotics | 783 | 1 | 0 pending |

## Partial Companies — Exact Approval Allowlists

### Geek+ (1398)

Approve only:

`1782, 1783, 1784, 1791, 1793, 1794, 1795, 1796, 2776, 2778, 2779, 3582, 3583, 4136`

- Ready: **14**
- Rejected: **38** duplicate/solution/configuration/alias shells
- Hold: P800H `1785`, S100C `1792`, RS11-DA `4950`
- Typed coverage across 17 retained: payload 16, weight 13, speed 16,
  dimensions 14–16, runtime 13, battery 15
- Accepted heroes: CDN/pixel verified **14/14**

### Hyundai Robotics (49)

Approve only:

`3731, 3721, 3720, 3718, 3717, 3716, 3712`

- Ready: **7**
- Rejected: **5** generic category/series duplicates
- Hold: **11** package/category media gaps, HH050 alias merge, identical-byte
  HDC25/HDC35 heroes, and FPD category shell

### DELTA Electronics Shanghai (1206)

Approve only:

`5199, 3663, 3664, 2943, 2933, 3661, 2935, 2937, 2941`

- Ready: **9**
- Hold: **8** exact-SKU media collisions or undocumented R65 suffixes
- Typed coverage: **15/17**; no base-family values copied into R65 records

### Mujin (810)

Approve only:

`3763, 3762, 3760, 3759, 3757, 3756, 3754, 3753`

- Ready: **8**
- Rejected: language-duplicate Depalletizer `3761`
- Hold: Pallet Changer `3758`, MujinRCP `3755`
- Cell throughput and work-envelope values remain sourced features rather than
  being misfiled as unidentified arm specs

## Cleared by Rejection

| Company | ID | Outcome |
|---------|---:|---------|
| Plus One Robotics | 254 | PickOne rejected as OEM-defined vision software |
| ACY Automation | 1369 | 55 pending EOAT rejected; published EOAT decision remains |
| Jiangsu DINGS | 1512 | Gripper EOAT rejected |
| AGV Network | 1322 | Media-directory category shell rejected |

## Important Dead Searches

- Surgical platforms: no defensible public whole-system mass, envelope,
  payload, reach, runtime, or DOF where reports say blank.
- Infinium Scan: no public mass, dimensions, payload, speed, or endurance.
- Gurki: six models have no exact-model public video; a clearly labeled family
  demonstration is retained.
- Chuck: no public travel speed.
- Geek+ held records: no accepted exact-model hero; P800H and S100C also retain
  stale related media that requires a staff-session deletion endpoint.
- Hyundai/DELTA/Mujin holds were not padded with sibling media or inherited specs.

## Verification

- All ready records remain `pending_review`.
- No remediation script approved or published content.
- Owned CDN heroes were HTTP-GET and image-byte verified.
- Exact-model media were checked for duplicate content hashes or decoded-pixel
  equality where CDN re-encoded PNGs.
- Moderation dry-runs and exact approval allowlists are recorded in
  [`../checklists/approve-publish-status.md`](../checklists/approve-publish-status.md).

## Related

- [Approve / Publish Status](../checklists/approve-publish-status.md)
- [Research Changelog](../log.md)
- [Geek+ Full Report](../../staging/reports/geekplus-curated-full-report.md)
- [Hyundai Full Report](../../staging/reports/hyundai-curated-full-report.md)
- [DELTA Full Report](../../staging/reports/delta-curated-full-report.md)
- [Mujin Full Report](../../staging/reports/mujin-curated-full-report.md)
