---
type: concept
title: Catalog vs Enrich Pipeline
status: published
version: 1.0
owner: AI
last_updated: 2026-07-10
tags:
  - research
  - catalog
  - enrich
  - pipeline
---

# Catalog vs Enrich Pipeline

Two distinct ways to populate robot staging JSON. Pick the wrong one and you waste API cost, overwrite good data, or import footer junk as product heroes.

## Catalog pipeline

**Input:** OEM product list pages (HTML tables/cards with model name, link, image).

**Tools:** Manufacturer-specific parser + apply script (Estun: `estun_english_catalog.py`, `apply_estun_english_catalog.py`).

**Strengths:**

- Deterministic URL and hero image per model
- No LLM or Apify required when lists are server-rendered
- Fast to re-run when OEM updates catalog

**Weaknesses:**

- Requires one-time parser per OEM layout
- May miss models not on public English lists
- Usually thin on specs unless detail pages are scraped separately

## Enrich pipeline

**Input:** Existing robot records or discover crawl of manufacturer site.

**Tools:** `cli.py auto discover`, `auto robots`, `auto pipeline`, optional `--stealth` / `--playwright`.

**Strengths:**

- Works when URLs are opaque and no list page exists
- Can fill specs, videos, tags from product detail pages
- Good for backfill of missing fields on sparse records

**Weaknesses:**

- Image extraction often grabs site chrome (phone icons, social badges)
- Expensive when run at scale (Playwright, Apify, Gemini search)
- **Must not** run `--refresh-media` after a catalog apply — overwrites good heroes

## Decision matrix

| Question | If yes → | If no → |
|----------|----------|---------|
| Does OEM publish list pages with model + image? | Catalog pipeline | Enrich pipeline |
| Are prod URLs/images already wrong? | Force-overwrite import, not patch | Patch OK for backfill blanks |
| Fixing images on prod after bad import? | copy-media or recopy script + deployed S3 fixes | N/A |
| Only 5–10 models missing from catalog? | Manual staging or targeted search | Do not re-enrich all robots |

## Hybrid (allowed)

1. Catalog apply for **url + image + sources**.
2. Enrich **without** `--refresh-media` for specs only (when supported).
3. Or: enrich individual robots with weak URLs via `product_url_search.py`.

## Related

- [../playbooks/catalog-oem-import.md](../playbooks/catalog-oem-import.md)
- [../reference/estun-import-postmortem.md](../reference/estun-import-postmortem.md)
- Skill: `.cursor/skills/robot-research-agent/SKILL.md`
