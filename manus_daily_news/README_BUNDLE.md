# RAI Deterministic Scan Bundle (2026-08-05)

Deterministic scripts for the RobotAIGeek Tier 1 Daily News Agent.
Principle: **scripts discover, the agent judges and writes.** Every fetch,
diff, and dedup that used to cost agent browsing steps now runs in Python.

Install location: **`$PROJ/rai_scan/`, inside the Manus PROJECT
shared-file directory** (the one holding the canonical daily-news prompt,
e.g. `/home/ubuntu/projects/daily-news-<hash>/`). Do NOT install under
`/home/ubuntu/` — that sandbox resets between tasks and would destroy the
scan baselines and dedup memory. Run the scripts from `$PROJ/rai_scan`
with `--state-dir state --out-dir out` so state persists there too.

## Files

| File | Purpose |
|---|---|
| `registry_v4_20260805.csv` | Canonical source registry (500 sources, repaired 2026-08-05: 35 column-shifted rows fixed, incl. all Japan companies). Scripts read THIS file. |
| `RAI_FirstHand_Source_Registry_v4_20260805.xlsx` | Human-readable copy of the same data. Never scanned by scripts. |
| `preflight_check.py` | Health check, run FIRST every run: verifies every script and data file is present and non-empty, creates missing state/out dirs, blocks if installed under the ephemeral sandbox home, and reports unbaselined-source and empty-dedup-log warnings. Exit 1 = do not run the pipeline. |
| `validate_registry.py` | Schema gate. Any new/updated registry must exit 0 before it becomes canonical. |
| `scan_due_sources.py` | Daily scan: due-set selection by tier+frequency, RSS polling, conditional page fetch + link diff, candidate metadata (title/description/og:image/date). **Strict same-day gate:** every candidate is classified `same-day` / `unverified` / `prior-day` / `stale`; only same-day and unverified reach `candidates`, the rest are quarantined in `stale_excluded`. `--allow-prior-day` widens the window and requires explicit user approval. |
| `dedup_check.py` | Claim-level dedup against a local `published_log.jsonl` (14-day window, company aliases + event-type synonyms). Replaces browsing the live site. |
| `package_lint.py` | Compliance lint for public copy, keyed to SKILL.md: disclaimer (14.10), word band news 1,500-1,800 / article 1,500-2,500 (3.4.1), no em dashes (14.6), no bare `$` (14.14), no third-party outlet attribution (14.11), no "What is X?" openers or labeled ELI5/Hard Truth headings (3.5.1), banned-phrase and US$-conversion warnings, and `--run-date` stale-date warnings (Section 4). Every body must exit 0 before packaging. |

## Daily flow (what the scheduled agent runs)

```
cd $PROJ/rai_scan
python3 preflight_check.py --pipeline daily   # exit 1 = stop, do not improvise
python3 scan_due_sources.py --registry registry_v4_20260805.csv --state-dir state --out-dir out
# -> out/scan_delta_YYYYMMDD.json  (candidates, needs_browser, errors)

# per story selected for drafting:
python3 dedup_check.py check --log state/published_log.jsonl \
    --title "..." --companies "X,Y" --event-type funding
# exit 0 = fresh, exit 2 = duplicate (JSON report on stdout)

# after packaging, one call per packaged story (or --from-json):
python3 dedup_check.py append --log state/published_log.jsonl \
    --date YYYY-MM-DD --lane news --title "..." \
    --url "..." --companies "X" --event-type funding
```

## Cadence rules (encoded in scan_due_sources.py)

- P0 or Daily-frequency: scanned every day (~110 sources)
- Weekly: one stable weekday per source; Monthly: one stable day-of-month
- Event-driven: P1 every 3 days, P2 weekly; Occasional: P1 weekly, P2 monthly
- Net effect: ~160-180 due sources/day instead of 472, most of which
  return 304/no-change and cost one HTTP request, zero agent steps.

## State (do not delete)

- `state/scan_state.json` (inside $PROJ/rai_scan) — ETags, link-set hashes, seen RSS ids.
  Deleting it forces a new baseline (first run after deletion emits no
  scrape candidates).
- `state/published_log.jsonl` — the dedup memory. Seed once from the
  existing published log, then `append` keeps it current.

## First run

`--force-all` once at install time to establish the baseline. RSS
candidates appear immediately (3-day lookback); page-scrape diffs start
from the second run.

## Registry updates (growth chats)

New registry versions MUST pass `python3 validate_registry.py <file>`
(exit 0) before replacing the canonical CSV. Always generate CSV rows with
Python's `csv` module — hand-concatenated comma strings are what corrupted
the Jul-30 registry.
