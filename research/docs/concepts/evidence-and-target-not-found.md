---
type: concept
title: Evidence Storage and target_not_found
status: published
version: 1.1
owner: AI
last_updated: 2026-07-15
tags:
  - research
  - discovery
  - enrichment
  - quality
---

# Evidence Storage and target_not_found

Two quality upgrades on the discovery/enrich pipeline. They travel together: evidence makes batches auditable; `target_not_found` stops wrong staging when a model cannot be located.

**Heads-up:** both discovery and enrichment write under `staging/evidence/` and consume disk. Overnight enrich of hundreds of robots is expected to create sizable trees; retention sweep keeps the last N runs per company (defaults: `EVIDENCE_KEEP_RUNS=5`, `EVIDENCE_MAX_BYTES_PER_COMPANY≈200MB`).

## Evidence storage + replay

**Module:** `scripts/research/evidence_store.py`

| Pipeline | Wired in | Default page body |
|----------|----------|-------------------|
| Discover | `discover_robots.py` | Raw HTML (when available) |
| Enrich | `robot_auto_research.py` → overnight / backfill / targeted | Lean: parsed text + Gemini request/response JSON |

Layout (shared):

```
staging/evidence/{company_slug}/{run_id}/
  meta.json
  manifest.json
  pages/{host}_{sha12}.{html|txt}
  extract/{host}_{sha12}.json
```

- **pages** — discover: HTML preferred; enrich: text by default. Raw HTML is kept for `target_not_found` skips and low grounded/verify scores (`force_html`).
- **extract** — Gemini / classifier payloads (request preview + response).
- **manifest** — `page` / `extract` / `robot_link` / `target_not_found` entries. Enrich tags entries with `robot_id`.

Replay without re-fetch: load `manifest.json`, read saved bodies, re-run mapping/validation offline.

Summary fields: `evidence_dir`, `evidence_run_id` (discovery + enrich/overnight).

Retention: `sweep_company_evidence(slug)` after each enrich company run.

## Snapshot verify (must not fake a live fetch)

`verify_robot(..., page_snapshot=..., evidence_ref=...)` can score against saved text.

When snapshot mode is used:

- Result `page.verified_against` = `evidence_snapshot`
- `page.fetched` stays **false** for live-reachability accounting
- `url_match` / `content_consistency` are nulled (do not calibrate on snapshot text)
- Summary is prefixed with `[Verified against evidence snapshot…]`

Default `manage.py verify_content` / `verify_staged_robot` without a snapshot still do a **live** HTTP fetch. Never feed snapshots into the calibrated live bands silently.

## target_not_found semantics

When a specific robot/model fragment cannot be confirmed on the fetched page(s):

| Path | Behavior |
|------|----------|
| Discover | Skip staging; log `target_not_found` in evidence + summary `skipped_target_not_found` |
| Enrich (`research_robot`) | Return `None`; save HTML bodies + manifest `page_paths`; callers skip import |
| Image select (`select_images_for_pages`) | Fail closed → empty hero/gallery (no whole-page fallback) |

Confirmation uses `confirm_target_on_page` / `model_name_in_page` (title, meta, body text, or URL path tokens).

Estun catalog hits (`estun_entry`) bypass the enrich gate: the English list already bound name → URL/image.

## Related

- [catalog-vs-enrich-pipeline.md](catalog-vs-enrich-pipeline.md)
- [../decisions/adapter-registry-deferred.md](../decisions/adapter-registry-deferred.md)
