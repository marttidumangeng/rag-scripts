---
type: log
title: Auris Health curated enrichment
status: complete
version: 1.0
owner: AI
last_updated: 2026-07-21
tags:
  - auris-health
  - robot-enrichment
  - production-audit
---

# Auris Health Curated Enrichment

## Scope

- Company: Auris Health (J&J MedTech) (`1511`)
- Production records: 1
- Result: 1 enriched; 0 rejected; 0 published
- Final moderation status: `pending_review`

## Production Coverage

- `5197` MONARCH QUEST: release year populated; 2 exact-variant photos; 1 official model video; 3 sources.
- Complete MONARCH family, model, and QUEST variant metadata is populated.
- Product URL scope is `family` because the OEM identifies QUEST within the MONARCH bronchoscopy page rather than publishing a stable standalone PDP.
- Availability is `available`.
- AI-enhanced bronchoscopy purpose lines, description, features, taxonomy, and tags are populated.
- Sources include the OEM product section, J&J MedTech clearance announcement, and FDA 510(k) `K243219`.
- The copied CDN hero returns HTTP `200` as image content.

## Typed-Spec Notes

- Release year is populated from the clearance/launch record.
- Degree of freedom is explicitly unset.
- No public citeable system mass, envelope dimensions, payload, reach, repeatability, speed, runtime, or whole-system DOF was found in the OEM product material, clearance announcement, or FDA summary. No values were inferred.

## Media Validation

- Both candidates visibly show MONARCH QUEST and were checked by HTTP response, image magic bytes, byte size, and MD5 hash.
- Generic MONARCH cart imagery, banners, diagrams, sibling imagery, and duplicate hashes were excluded.
- The retained video is an official J&J MedTech MONARCH QUEST clinical clip.

## Dead Searches

- No standalone stable QUEST PDP was available; the exact OEM page target is a section anchor on the MONARCH family page.
- No public QUEST datasheet or brochure with typed physical/system specifications was found after OEM PDP, press, and FDA review.

## Related

- [Auris Health production script](../../fix_auris_robots.py)
