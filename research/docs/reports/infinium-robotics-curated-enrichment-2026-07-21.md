---
type: log
title: Infinium Robotics curated enrichment
status: complete
version: 1.0
owner: AI
last_updated: 2026-07-21
tags:
  - infinium-robotics
  - robot-enrichment
  - production-audit
---

# Infinium Robotics Curated Enrichment

## Scope

- Company: Infinium Robotics (`783`)
- Production records: 1
- Result: 1 enriched; 0 rejected; 0 published
- Final moderation status: `pending_review`

## Production Coverage

- `3691` Infinium Scan: 3 exact-model photos; 3 official model videos; 2 sources.
- Exact product URL and complete family, model, and variant metadata are populated.
- Availability is `available`.
- Warehouse inventory and rack-inspection purpose lines, description, features, taxonomy, and tags are populated.
- Sources include the OEM PDP and OEM warehouse-drone whitepaper.
- The copied CDN hero returns HTTP `200` as image content.

## Typed-Spec Notes

- No citeable mass, envelope dimensions, payload, flight speed, runtime/endurance, reach, repeatability, or DOF was found in the OEM PDP or whitepaper.
- Marketing claims about autonomous inventory operation were not converted into unsupported typed values.

## Media Validation

- All candidates visibly show the Infinium Scan warehouse drone and were checked by HTTP response, image magic bytes, byte size, and MD5 hash.
- Generic warehouse banners, diagrams, unrelated drones, and duplicate hashes were excluded.
- All 3 retained videos are official, model-specific Infinium Scan demonstrations.

## Dead Searches

- The OEM PDP and linked whitepaper provide no citeable physical dimensions, mass, payload, speed, or endurance.
- No separate OEM datasheet or technical manual with those typed specifications was found.

## Related

- [Infinium Robotics production script](../../fix_infinium_robots.py)
