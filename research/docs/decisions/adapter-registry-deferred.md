---
type: decision
title: Adapter Registry Deferred Until Next ESTUN-Class OEM
status: published
version: 1.0
owner: AI
last_updated: 2026-07-15
tags:
  - research
  - catalog
  - adapters
---

# Adapter Registry Deferred Until Next ESTUN-Class OEM

## Decision

Do **not** build a manufacturer adapter registry (`domain → staging JSON`) until the next ESTUN-class site is imported — an OEM with server-rendered list pages that need a deterministic catalog parser, not a generic crawl/enrich pass.

## Context

Estun already has a working one-off path:

- `estun_english_catalog.py`
- `apply_estun_english_catalog.py`
- Hard-coded `is_estun_website` branches in enrich/discover

A thin registry (domain map, mandatory smoke test, generic fallback, port Estun as first entry) is the right design — but speculative. Building it before the next similar OEM adds interface churn without a second consumer.

## When to build it

Trigger: the next OEM that would otherwise get another `_company_*.py` / `*_english_catalog.py` one-off.

Then spend the extra hour to:

1. Define `Adapter` interface: `domain → list[staging robots]` (+ optional detail enrich).
2. Require a smoke test per adapter (at least one known model URL + hero).
3. Keep generic crawl/Gemini discover as fallback when no adapter matches.
4. Port Estun into the registry as the first entry.

## Non-goals (now)

- Refactoring Estun into a registry with no second adapter.
- Wrapping every overnight enrich OEM behind adapters.

## Related

- [../concepts/catalog-vs-enrich-pipeline.md](../concepts/catalog-vs-enrich-pipeline.md)
- [../playbooks/catalog-oem-import.md](../playbooks/catalog-oem-import.md)
- [../reference/estun-import-postmortem.md](../reference/estun-import-postmortem.md)
