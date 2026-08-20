# Daily News Scheduler Self-Diagnosis (paste into a NEW session in the daily-news project)

Context for Martti: two daily-news project directory hashes have been
observed (`282d2cf2` in the old scheduled prompt, `0ebec8cd` in the repair
session that found the install healthy). The most likely fault is that the
scheduled task and the rai_scan install are attached to different
projects. This prompt makes Manus prove or rule that out and hand back
exact fix steps. The scan STATE (baselines + dedup log) lives with the
install, so the fix must move the TASK to the install, never the other
way around.

```
The Daily News scheduled task is not running the deterministic pipeline
correctly. Diagnose why, fix only what is inside the sandbox, and report
exact Manus UI steps for everything else.

HARD RULES: Do not run the Morning Package or draft any content. Do not
rewrite, rebuild, or substitute any pipeline script. Do not create or
modify any scheduled task yourself. Do not delete or move anything under
rai_scan/state/. Diagnose, verify, report.

STEP 1 — Where am I?
Run and paste raw output:
  ls -d /home/ubuntu/projects/*/
  ls /home/ubuntu/projects/*/
State the mounted project directory (note its hash suffix) and whether it
contains rai_scan/. Call it $PROJ.

STEP 2 — Is the install here, and is it healthy?
If $PROJ/rai_scan exists:
  cd $PROJ/rai_scan && python3 preflight_check.py --pipeline daily
  Paste the full output, including the unbaselined-source count and
  dedup-log entry count. Also report:
  ls -la $PROJ/rai_scan/state/ $PROJ/rai_scan/out/ | head -30
If $PROJ/rai_scan does NOT exist, say so and check whether the bundle zip
(rai_deterministic_scan_bundle_20260805.zip) is anywhere in $PROJ. Do NOT
install anything in this case — if the install lives in a different
project, installing a second empty copy here would split the state. Skip
to STEP 4.

STEP 3 — Does the scan actually run here?
Only if preflight passed:
  python3 scan_due_sources.py --registry registry_v4_20260805.csv \
      --state-dir state --out-dir out --deadline 240
  Paste the stats JSON. A normal result has same_day/stale_excluded
  fields and writes out/scan_delta_<today>.json. This proves the
  pipeline itself is fine and isolates the problem to scheduling.

STEP 4 — Why didn't the SCHEDULED runs work?
Inspect what you can see about the Daily News scheduled task from inside
this project: its name, prompt text if visible, schedule and timezone,
and recent run history/logs. Quote the first lines of the most recent
failed or wrong runs if accessible. Classify the failure as exactly one:
  A. Task attached to a different project than the rai_scan install
     (strong prior: hashes 282d2cf2 vs 0ebec8cd have both been observed)
  B. Task prompt is outdated — it does not resolve $PROJ and run
     preflight_check/scan_due_sources (quote what it runs instead)
  C. Task never fired (schedule/timezone problem; state configured
     schedule and timezone)
  D. Task fired and the pipeline errored (paste the error)
  E. Cannot determine from inside the sandbox (say what visibility was
     missing)

STEP 5 — Report
  1. Root cause: one letter plus one sentence.
  2. What passed in this session (preflight result, scan stats).
  3. Exact Manus UI steps for me, numbered. If the cause is A: state
     that the task must be recreated or re-pointed INSIDE the project
     whose Files contain rai_scan/ (this project if Step 2 found it),
     and explicitly warn me NOT to fix it by installing a fresh copy in
     the task's current project, because the scan baselines and dedup
     log live with the existing install and a fresh copy starts blind.
     If the cause is B: say the task prompt should be replaced with the
     current Prompt 2 from MANUS_PROMPTS.md (do not invent new prompt
     text). If C: state the exact schedule/timezone to set.
  4. Verification: what I should expect to see in the first minute of
     the next scheduled run if the fix worked ($PROJ printed, preflight
     READY, scan stats JSON).
Do not proceed past this report.
```
