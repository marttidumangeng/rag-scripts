---
type: log
title: Needs Cleanup Overnight — Morning Report
status: draft
version: 1.0
owner: AI
last_updated: 2026-08-14
tags:
  - content-queue
  - overnight
  - needs-cleanup
---

# Needs Cleanup Overnight — Morning Report

Generated: 2026-08-14T13:07:39.390215+00:00

## Executive summary

- Companies processed: **0**
- Soft-enriched (patched): **0**
- Rejected: **0**
- must_clear_pass after run: **0** / **0** remaining pending
- Geek+ heroes copy-media OK: **0** / attempted **0**
- Errors: **0**

### Stakeholder FYIs

- Bluefin (160) approved earlier → already Cleared.
- ACY (1369): rejected all **pending** EOAT as `non_robot`. **Published EOAT still need reject-or-keep decision.**
- Jiangsu DINGS Gripper + AGV Network reach-truck rejected (EOAT / media directory).
- Intamsys FUNMAT left as industrial 3D printers (enriched, not rejected).
- Soft pass only — no deep datasheet scrape tonight except Geek+ hero URLs.

## Per-company results

| Company | ID | Before pending | Rejected | Patched | After pending | must_clear_pass | Notes |
|---------|---:|---------------:|---------:|--------:|--------------:|----------------:|-------|

## Next for you

1. Bulk Approve companies that moved to Ready (must_clear green).
2. Decide ACY published EOAT (35) — reject all?
3. Optional deep pass: Geek+ remaining imageless if any; Hyundai series-shell dedupe.

Script: `overnight_needs_cleanup_enrich.py`
