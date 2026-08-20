# Scheduler Self-Diagnosis Prompt (paste into a NEW session in the dedicated-topic-article project)

```
The scheduled task for the ARPI Dedicated Topic Writer is not producing
articles. Diagnose why, report your findings, and fix ONLY what is inside
the sandbox. Some causes can only be fixed in the Manus UI, which you
cannot touch: for those, report the exact steps I must take.

HARD RULES: Do not draft an article. Do not rewrite, rebuild, or
substitute any pipeline script. Do not create or modify any scheduled
task yourself. Diagnose, repair files if possible, verify, and report.

STEP 1 — Where am I?
Run and paste the raw output:
  ls -d /home/ubuntu/projects/*/
  ls /home/ubuntu/projects/*/
State which project directory is mounted and whether it contains
ARPI_Content_Calendar_Strategy_v6.xlsx. Call the directory that contains
the calendar $PROJ. If NO mounted directory contains that calendar, STOP:
diagnosis is "this session (and probably the scheduled task) is attached
to the wrong project." Report that the task must be recreated from inside
the dedicated-topic-article project, and skip to STEP 5.

STEP 2 — Are the pipeline files in the project?
Check for each of these in $PROJ and report PRESENT or MISSING:
  - arpi_topic_bundle_20260806.zip
  - ARPI_Dedicated_Topic_Writer_Prompt_v9.md
  - ARPI_Content_Calendar_Strategy_v6.xlsx
Any MISSING file can only be fixed by uploading it to the project's Files
in the Manus UI; name exactly which files I must upload. If the zip is
missing but an unzipped arpi_topic/ directory somehow exists, note that
it will NOT survive the next session and the zip is still required.

STEP 3 — Does the pipeline actually run here?
Only if the zip is PRESENT, bootstrap and smoke-test exactly as the run
prompt would:
  WORK=/home/ubuntu/arpi_topic
  mkdir -p $WORK && cd $WORK
  unzip -o $PROJ/arpi_topic_bundle_20260806.zip -d $WORK
  mkdir -p $WORK/heroes $WORK/scan_history
  python3 -c "import openpyxl" 2>/dev/null || pip3 install -q openpyxl
  python3 -c "import docx" 2>/dev/null || pip3 install -q python-docx
  python3 preflight_check.py --pipeline topic --calendar $PROJ/ARPI_Content_Calendar_Strategy_v6.xlsx
Paste the full preflight output. Then verify the calendar resolves for a
known date:
  python3 assignment_lookup.py --calendar $PROJ/ARPI_Content_Calendar_Strategy_v6.xlsx --date 2026-08-06
It must return the Post 9 "Beyond the Invoice" assignment. Also confirm
the no-post behavior with --date 2026-08-08 (expect exit 3, "no post
scheduled" — that is correct behavior, not a failure).

STEP 4 — Why didn't the SCHEDULED runs work?
Inspect what you can see about the scheduled task from inside this
project (task name, prompt text if visible, schedule, timezone, and its
run history/logs if accessible). For the most recent failed or empty
runs, quote the first lines of their output if available. Classify the
failure as exactly one of:
  A. Task attached to the wrong project (mounted directory has no calendar)
  B. Required files missing from project Files (name them)
  C. Task prompt is wrong or outdated (does not match the current run
     prompt that bootstraps from the zip; quote the difference)
  D. Task never fired (schedule/timezone problem; state the configured
     schedule and timezone and what you expected)
  E. Task fired and the pipeline errored (paste the error)
  F. Cannot determine from inside the sandbox (say what visibility was
     missing)

STEP 5 — Report
Produce a short report with these sections:
  1. Root cause: the single letter from Step 4 plus one sentence.
  2. What I fixed in the sandbox (if anything).
  3. What YOU must do in the Manus UI, as exact numbered steps: which
     project to open, which files to upload, what to set the task's
     prompt to (say "use the run prompt from MANUS_TOPIC_PROMPTS.md /
     the short trigger that bootstraps from the zip" rather than
     inventing new prompt text), and what schedule/timezone to set.
  4. Verification: state that the bootstrap and both calendar smoke
     tests passed in this session, or exactly which one failed and its
     output.
Do not proceed past this report. Do not draft content.
```

## Notes for Martti (not part of the prompt)

- Run it in a NEW session **inside the dedicated-topic-article project** —
  that is itself part of the test: if Step 1 shows no calendar, the
  project attachment is the whole problem.
- The prompt forbids Manus from creating/altering scheduled tasks because
  a task it creates from inside a session may not be attached where you
  expect; task creation should stay a UI action you do, following its
  numbered steps.
- If the report comes back "F — cannot determine," paste the report to
  Claude along with a screenshot of the scheduled task's settings page
  (project, prompt, schedule); the combination pins it down.
```
