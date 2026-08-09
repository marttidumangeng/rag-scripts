# ARPI Topic Writer Deterministic Bundle (2026-08-06)

Deterministic scripts for the ARPI Dedicated Topic Writer workflow.
Principle: **scripts resolve, seed, assemble, and check; the agent
verifies, judges, and writes.**

Install location: **`$PROJ/arpi_topic/`, inside the Manus PROJECT
shared-file directory** (the one holding the canonical prompt and the
calendar workbook). Never install under `/home/ubuntu/` — that sandbox is
wiped between sessions and task runs, which would delete the `heroes/`
archive and any accumulated scan history.
Dependencies: `openpyxl` (assignment_lookup) and `python-docx`
(build_docx); everything else is stdlib.

## Files

| File | Purpose |
|---|---|
| `preflight_check.py` | Health check, run FIRST every run: verifies scripts, registry, calendar, python-docx/openpyxl availability, creates missing heroes/ and scan_history/ dirs, blocks if installed under the ephemeral sandbox home. Exit 1 = do not run the pipeline. |
| `assignment_lookup.py` | Resolves RUN_DATE (Asia/Shanghai), exact-matches calendar Tab 4, derives Asset Class + Post Slot, extracts the Tab 5 framework, computes deliverable filenames. Stop conditions are exit codes: 3 = no post scheduled, 4 = framework missing. |
| `market_ledger_seed.py` | Seeds the Market-Development Ledger from the daily pipeline's scan_delta history + published log + targeted registry RSS pulls, filtered by topic keywords. Degrades to RSS-only mode when scan history is absent. Output is a SEED; the agent still applies the relevance gate and Tier-1 verification. |
| `article_lint.py` | Mechanical QC: word band 1,200-1,600, no inline citation markers, no em/spaced-en dashes, no References heading, evidence kept out of the body file, no publication/workflow names, acronym first-use heuristic (warnings), hero true-JPG 16:9 + filename date, docx validity + evidence section + disclaimer. Exit 0 required before delivery. |
| `build_docx.py` | Assembles the Word-first deliverable (cover, metadata table, dark-blue headings, embedded table PNGs, internal-only Evidence Source Notes closing page, disclaimer) from body.md + evidence.md + meta.json + assignment.json + hero, and runs the open-and-render test. |
| `registry_v4_20260805.csv` | Source registry copy for market_ledger_seed's targeted RSS mode. |
| `ARPI_Dedicated_Topic_Writer_Prompt_v9.md` | The canonical run prompt. Setup copies it to `$PROJ/` beside the calendar; the run trigger points at it there. Edit that copy to change the workflow. |

## Run flow

```
cd $PROJ/arpi_topic
python3 preflight_check.py --pipeline topic --calendar $PROJ/ARPI_Content_Calendar_Strategy_v6.xlsx
python3 assignment_lookup.py --calendar $PROJ/ARPI_Content_Calendar_Strategy_v6.xlsx --out assignment.json
# MCP: coverage_check (duplicate gate), articles_search (series continuity)
python3 market_ledger_seed.py --assignment assignment.json \
    --keywords "<topic synonyms>" --registry registry_v4_20260805.csv \
    --scan-dir $PROJ/arpi_topic/scan_history --out ledger_seed.json
# agent: relevance gate + Tier-1 verification + writing
# agent writes: body.md, evidence.md, meta.json, hero jpg, table PNGs, XLSX
python3 build_docx.py --assignment assignment.json --body body.md \
    --evidence evidence.md --meta meta.json --hero <hero.jpg>
python3 article_lint.py body.md --run-date <date> --hero <hero.jpg> \
    --docx <built docx> --exempt "<company short forms>"
```

## Notes

- `heroes/` holds a copy of every generated hero; the differentiation
  review happens locally against it instead of browsing the site.
- The daily news pipeline runs in a DIFFERENT Manus project, so its scan
  deltas are not reachable here. The seed runs RSS-only unless copies of
  `scan_delta_*.json` are placed in `$PROJ/arpi_topic/scan_history/`.
  Copying them across projects periodically unlocks the richer mode; it is
  not required to run.
- The calendar workbook stays canonical in the project shared-file
  directory; scripts read it in place, never copy or modify it.
