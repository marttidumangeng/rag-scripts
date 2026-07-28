---
type: log
title: Intuitive Surgical curated enrichment
status: complete
version: 1.0
owner: AI
last_updated: 2026-07-21
tags:
  - intuitive-surgical
  - robot-enrichment
  - production-audit
---

# Intuitive Surgical Curated Enrichment

## Scope

- Company: Intuitive Surgical (`52`)
- Production records: 3
- Result: 3 enriched; 0 rejected; 0 published
- Final moderation status: `pending_review` for all records

## Production Coverage

- `3693` Da Vinci SP: release year populated; 3 exact-model photos; 1 OEM model video; 2 sources.
- `3694` Da Vinci 5: release year populated; 1 official launch photo; 1 OEM model video; 3 sources, including FDA 510(k) `K232610`.
- `3695` Ion robotic bronchoscopy: release year populated; 2 exact-model photos; 1 OEM model video; 3 sources, including FDA 510(k) `K182188`.

All three records include:

- Exact product URL and complete family, model, and variant metadata.
- `available` availability.
- Curated medical taxonomy and tags.
- Indication-aligned purpose lines, description, and features.
- OEM product pages, OEM brochures, and applicable FDA documentation.
- Copied CDN hero with successful HTTP image response.

## Typed-Spec Notes

- Release year is populated for all 3 records.
- Degree of freedom is explicitly unset. Public product pages, brochures, and cited FDA summaries do not provide a defensible whole-system DOF count.
- No system mass, envelope dimensions, payload, reach, repeatability, speed, or runtime was found in the reviewed public OEM and regulatory material. No values were inferred from instrument articulation or marketing claims.

## Media Validation

- Exact-model candidates were checked by visual identity, HTTP response, image magic bytes, byte size, and MD5 hash.
- Sibling systems, diagrams, banners, and duplicate hashes were excluded.
- All 3 CDN heroes return HTTP `200` as image content.
- All 3 retained videos are official, model-specific Intuitive clips.

## Dead Searches

- Da Vinci SP: no citeable public whole-system dimensions, mass, payload, reach, repeatability, speed, runtime, or DOF after OEM PDP and brochure review.
- Da Vinci 5: no citeable public whole-system dimensions, mass, payload, reach, repeatability, speed, runtime, or DOF after OEM PDP, brochure, and FDA summary review.
- Ion: no citeable public whole-system dimensions, mass, payload, reach, repeatability, speed, runtime, or DOF after OEM PDP, brochure, and FDA summary review.

## Related

- [Intuitive Surgical production script](../../fix_intuitive_robots.py)
