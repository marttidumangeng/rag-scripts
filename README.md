# rag-scripts

Operations and research tooling for **RobotAIGeek** — the scripts that discover, enrich, verify, and ship robot catalog data into the production database. This repo is the working companion to the main application repos (`robotaigeek-server`, Django 5.2 API; `robotaigeek-web`, Nuxt 3 frontend); everything here talks to the server through its authenticated REST API or, for prod maintenance, through `kubectl exec` into the GKE cluster.

## Repository layout

| Path | What it is |
|------|------------|
| `research/` | The core package: discovery, enrichment, verification, and import tooling |
| `research/docs/` | Playbooks, checklists, decisions, and postmortems — start at `research/docs/index.md` |
| `research/remedies/` | Flag-keyed remedy library for the rejection feedback loop (auto-fix engine + no-op detector + planner) |
| `research/tests/` | Test suite for remedies, catalog parsers, and fix scripts |
| `research/deploy/` | `vm_startup.sh` — the GCE startup script that orchestrates the nightly pipeline VM (see its README) |
| `research/seeds/` | Company seed lists for greenfield discovery |
| `research/state/` | Run bookkeeping (processed IDs, leads log); caches are gitignored |
| `research/staging/` | Scratch area for staged import files — gitignored, can grow to gigabytes |
| `rival_watch/` | Versioned competitor snapshots taken by `watch_rivals.py` |
| *(repo root)* | One-off utilities: media optimization, endpoint probes, cluster/telemetry toggles, skill-feedback helpers |

### Naming convention in `research/`

- `snake_case.py` (no leading underscore) — durable, reusable tools.
- `_leading_underscore.py` — one-off scratch scripts from specific enrichment campaigns, kept for history and as worked examples. Don't build on them; the reusable logic they proved out lives in the durable modules (`api_client.py`, `verify_lib.py`, `description_lib.py`, `remedies/`).

## Key pipelines

- **Greenfield discovery** — `research/workflow_greenfield.py` / `overnight_greenfield_import.py`: sitemap-seeded per-company discovery → staging → consolidation → verify-fix → import → media pass.
- **Rejection feedback loop** — `research/rejection_feedback_loop.py` + `research/remedies/`: CRM-rejected robots are classified, auto-fixed by the matching remedy, re-verified, and resubmitted; the attempt ledger is written back so the loop learns. Terminal cases escalate instead of retrying blindly.
- **Verification** — server-side `verify_content` (Gemini-scored) stamps the review queue; `research/verify_staging.py` covers pre-import checks. Prod scores must come from the server, never local runs.
- **Rival watcher** — `watch_rivals.py` snapshots competitor catalogs into `rival_watch/` and diffs them between runs.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use bin/activate elsewhere
pip install -r research/requirements.txt
# optional, for HubSpot/SPA image extraction:
pip install playwright && playwright install chromium
```

All credentials come from environment variables — nothing is hardcoded, and `.env` files are gitignored. The main ones:

| Variable | Purpose |
|----------|---------|
| `IMPORT_SYNC_API_BASE_URL` | RobotAIGeek API base, e.g. `http://127.0.0.1:8000/api/v1/` |
| `IMPORT_SYNC_API_KEY` | API key for import/sync endpoints |
| `GEMINI_API_KEY` | Grounded selection and content verification |
| `SERPER_API_KEY` | Web search (serper.dev is the standard search provider) |

### Running scripts — known gotchas

- `cd` into `scripts/research/` before running its modules; relative imports assume that working directory.
- Set `PYTHONIOENCODING=utf-8` — several vendors have CJK product names that crash cp1252 consoles on Windows.
- Wrap production API calls in 429 backoff; cache intermediate results locally rather than re-fetching.

## Ground rules

These are hard-won and enforced across the tooling — see `research/docs/` for the full playbooks:

1. **Imports create new robots only.** Never overwrite existing records via bulk import; existing-record backfill goes through targeted PATCH.
2. **Auto-fix tooling only touches Draft / To Review robots** — never Approved or Published.
3. **Stage one company, review, then import.** No mass multi-company import batches.
4. **`release_year` requires a grounded citation** end-to-end.
5. **Prod is the ground truth** for review statuses; the local DB is display seed data.

## Deploying the nightly pipeline

The whole pipeline runs nightly on a GCE Spot VM. Shipping code = re-uploading the tarball to `gs://robotaigeek-core-enrichment/code/repo-code.tar.gz`; the VM re-pulls it on every boot. The orchestration itself (stage order, smoke gate, timeouts) is `research/deploy/vm_startup.sh` — see `research/deploy/README.md` for the exact deploy commands.
