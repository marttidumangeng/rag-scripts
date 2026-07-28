---
type: log
title: Intamsys curated enrichment
status: complete
version: 1.0
owner: AI
last_updated: 2026-07-21
tags:
  - intamsys
  - robot-enrichment
  - production-audit
---

# Intamsys Curated Enrichment

## Scope

- Company: Intamsys (`1073`)
- Production records: 5
- Result: 5 enriched; 0 rejected; 0 published
- Final moderation status: `pending_review` for all records
- Qualification decision: retained under repository precedent for industrial additive-manufacturing robots. Printer classification alone is not a supported rejection reason.

## Production Coverage

- `2973` FUNMAT PRO 310 NEO: mass and external dimensions populated; 2 exact-model photos; 1 OEM model video; 2 sources.
- `2974` FUNMAT HT: mass, external dimensions, and release year populated; 1 exact-model photo; 2 model-specific videos; 2 sources.
- `2975` FUNMAT PRO 410: mass and external dimensions populated; 1 exact-model photo; 2 model-specific videos; 2 sources.
- `2976` FUNMAT PRO 610HT: mass and external dimensions populated; 1 exact-model photo; 2 model-specific videos; 2 sources.
- `3692` FUNMAT PRO 310 APOLLO: mass, external dimensions, and release year populated; 2 exact-model photos; 1 OEM model video; 2 sources.

All five records include:

- Exact product URL and complete family, model, and variant metadata.
- `available` availability.
- Curated taxonomy and tags.
- OEM application-purpose lines, description, and features.
- OEM product and documentation sources.
- Copied CDN hero with successful HTTP image response.

## Typed-Spec Notes

- Build volumes, nozzle and chamber temperatures, layer resolution, and print speeds remain in model descriptions/features because the current Robot schema has no dedicated typed fields for these additive-manufacturing specifications.
- No payload, reach, repeatability, runtime, or degree-of-freedom values were inferred; those manipulator fields do not describe these printers.

## Media Validation

- Exact-model candidates were checked by HTTP response, image magic bytes, byte size, and MD5 hash.
- Sibling products, diagrams, banners, and duplicate hashes were excluded.
- All 5 CDN heroes return HTTP `200` as image content.
- The FUNMAT HT, PRO 410, and PRO 610HT clips are model-specific third-party demonstrations; no qualifying OEM-hosted model clip was found after product-page, documentation, and OEM-channel search.

## Dead Searches

- No dedicated typed schema slot exists for citeable build volume.
- No additional exact-model OEM gallery image passed the quality rules for FUNMAT HT, PRO 410, or PRO 610HT.
- No OEM model-specific video was found for FUNMAT HT, PRO 410, or PRO 610HT.

## Related

- [Intamsys production script](../../fix_intamsys_robots.py)
