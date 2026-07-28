---
type: index
title: Robot Research Documentation
status: published
version: 1.6
owner: AI
last_updated: 2026-07-21
tags:
  - research
  - import
  - staging
---

# Robot Research Documentation

Navigation for `scripts/research/` workflows — staging, validation, and bulk-import to prod.

## Start here

| Doc | Use when |
|-----|----------|
| [checklists/approve-publish-status.md](checklists/approve-publish-status.md) | **Approve tonight** — living status (Approve = Publish for robots) |
| [playbooks/approve-reject-robots.md](playbooks/approve-reject-robots.md) | **Moderation** — publish / reject / hold after enrichment |
| [playbooks/catalog-oem-import.md](playbooks/catalog-oem-import.md) | **Catalog OEM** (list pages with heroes) — Estun-style import |
| [checklists/prod-manufacturer-import.md](checklists/prod-manufacturer-import.md) | **Before prod import** — avoid wasted API/S3 runs |
| [reference/estun-import-postmortem.md](reference/estun-import-postmortem.md) | **Lessons learned** — what worked/failed on Estun |
| [concepts/catalog-vs-enrich-pipeline.md](concepts/catalog-vs-enrich-pipeline.md) | Choosing catalog parser vs `auto pipeline` |
| [concepts/evidence-and-target-not-found.md](concepts/evidence-and-target-not-found.md) | Immutable crawl evidence + fail-closed missing targets |
| [decisions/adapter-registry-deferred.md](decisions/adapter-registry-deferred.md) | When to build domain→staging adapters (not before next ESTUN-class OEM) |
| [specifications/huayan-1490-full-enrichment-design.md](specifications/huayan-1490-full-enrichment-design.md) | Huayan company 1490 — approved 42-model reconciliation design |
| [plans/huayan-1490-full-enrichment-plan.md](plans/huayan-1490-full-enrichment-plan.md) | Huayan company 1490 — implementation workflow and verification gates |
| [../AUTOMATION.md](../AUTOMATION.md) | Scheduled / CLI automation prompts |
| [../../.cursor/skills/robot-research-agent/SKILL.md](../../.cursor/skills/robot-research-agent/SKILL.md) | Full agent skill (discover, enrich, validate) |

## Document hierarchy

```
docs/
├── index.md                          ← you are here
├── log.md                            ← changelog
├── playbooks/
│   ├── approve-reject-robots.md      ← moderation (Approve=Publish)
│   └── catalog-oem-import.md         ← step-by-step catalog OEM flow
├── concepts/
│   ├── catalog-vs-enrich-pipeline.md ← when to use which pipeline
│   └── evidence-and-target-not-found.md
├── decisions/
│   └── adapter-registry-deferred.md  ← defer adapter registry
├── specifications/
│   └── huayan-1490-full-enrichment-design.md
├── plans/
│   └── huayan-1490-full-enrichment-plan.md
├── checklists/
│   ├── approve-publish-status.md     ← living approve/publish queue status
│   └── prod-manufacturer-import.md   ← prod guardrails
└── reference/
    └── estun-import-postmortem.md    ← Estun case study / anti-patterns
```

## Scripts (common)

| Script | Purpose |
|--------|---------|
| `apply_estun_english_catalog.py` | Estun: English list pages → staging → import |
| `discover_robots.py` | Crawl OEM site → staging (+ evidence under `staging/evidence/`) |
| `robot_auto_research.py` | Enrich existing robots → staging (+ lean evidence; same tree) |
| `evidence_store.py` | Save/replay page text/HTML + extract JSON; retention sweep |
| `recopy_estun_images.py` | Re-download catalog heroes via bulk-import (may 502 on prod) |
| `trigger_estun_copy_media.py` | Prod S3 copy via internal copy-media API (preferred after deploy) |
| `cli.py import` | Generic staging → bulk-import API |
| `cli.py auto pipeline` | Full crawl enrich — **not** for catalog OEMs with list-page heroes |

## Related

- Staging schema: `scripts/research/schema.py`
- State: `scripts/research/state/processed_ids.json`
- Reports: `scripts/research/staging/reports/`
