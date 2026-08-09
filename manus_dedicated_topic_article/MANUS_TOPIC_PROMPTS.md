# Manus Prompts — ARPI Dedicated Topic Writer, Deterministic Pipeline (2026-08-06)

## How this works now (one prompt, no setup session)

The Manus project directory is **re-created from your uploaded project
files at the start of every session**, under a new directory hash. Only
files you upload to the project survive; anything a session writes into
that directory is gone next time. That is why installing an unpacked
`arpi_topic/` folder kept "disappearing".

So the bundle zip itself is the durable artifact. Each run unpacks it into
a scratch directory in seconds. There is no setup session and nothing to
verify by hand.

### One-time, done through the Manus UI (not a prompt)

Upload these two files to the **project's files** (the same place the
calendar lives):

1. `arpi_topic_bundle_20260806.zip`
2. `ARPI_Dedicated_Topic_Writer_Prompt_v9.md`

Optionally rename `ARPI_Dedicated_Topic_Writer_Scheduled_Task_Prompt_v8.md`
with an `ARCHIVED_` prefix so only one canonical prompt exists.

To change the workflow later, upload a replacement v9 file. To change the
scripts, upload a replacement zip. Nothing else ever changes.

---

## The run prompt (fresh session per article, or a scheduled task)

```
Run the ARPI Dedicated Topic Writer.

1. Find the project directory (the hash changes every session):
   ls /home/ubuntu/projects/*/ARPI_Content_Calendar_Strategy_v6.xlsx
   Set PROJ to the directory containing it and print it.

2. Bootstrap the pipeline into a scratch directory:
   PROJ=<that directory>
   WORK=/home/ubuntu/arpi_topic
   mkdir -p $WORK && cd $WORK
   unzip -o $PROJ/arpi_topic_bundle_20260806.zip -d $WORK
   mkdir -p $WORK/heroes $WORK/scan_history
   cp $PROJ/heroes/*.jpg $WORK/heroes/ 2>/dev/null
   python3 -c "import openpyxl" 2>/dev/null || pip3 install -q openpyxl
   python3 -c "import docx" 2>/dev/null || pip3 install -q python-docx
   python3 preflight_check.py --pipeline topic --calendar $PROJ/ARPI_Content_Calendar_Strategy_v6.xlsx

   If the zip is not in PROJ, STOP and report that it must be uploaded to
   the project files. If preflight exits non-zero, report the errors and
   STOP. Never rewrite, rebuild, or substitute any pipeline script, and
   never fall back to broad manual browsing.

3. Read $PROJ/ARPI_Dedicated_Topic_Writer_Prompt_v9.md IN FULL and follow
   it exactly. It supersedes
   ARPI_Dedicated_Topic_Writer_Scheduled_Task_Prompt_v8.md; ignore v8.
   Run every pipeline command from $WORK; read the calendar from $PROJ.

4. Deliver the package for editorial review. Do not publish. Include this
   run's hero JPG as a separate deliverable so it can be uploaded to the
   project's heroes/ folder for future differentiation checks.
```

For a specific editorial date, add:

```
Manual rerun for 2026-08-13: pass --date 2026-08-13 to assignment_lookup.py.
```

---

## What changed vs v8 (for reference)

| v8 step | v9 replacement | Why |
|---|---|---|
| Manual RUN_DATE resolution + Tab 4/5 matching with prose safety rules | `assignment_lookup.py` exit codes | Wrong-date/wrong-slot runs become impossible instead of warned-against |
| Browse live site for duplicate check | one `coverage_check` MCP call | Also sees pending-review drafts; zero browsing |
| Browse live site to reconstruct the series | `series_prior_posts` from the calendar + one `articles_search` call | Zero browsing |
| Browse recent articles to study heroes | local `heroes/` archive, seeded from the project's uploaded heroes | Zero browsing once the archive is seeded |
| Broad 90-day multi-source browser scan | `market_ledger_seed.py` over targeted RSS (plus daily-pipeline scan deltas if copied into the project) | The big credit cut; agent verifies instead of searches |
| Ad-hoc python-docx assembly each run | `build_docx.py` template + built-in render test | No regeneration loops on formatting |
| 12-point manual QC re-reading | `article_lint.py` mechanical half + agent judges the rest | Same play as package_lint in the daily pipeline |
