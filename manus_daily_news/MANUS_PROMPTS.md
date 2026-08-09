# Manus Prompts — Deterministic Daily News Pipeline (2026-08-05)

## Session strategy (recommendation)

**Use new sessions, not the current chats.**

- Manus replays a session's context on every message, so long-running chats
  make each subsequent step more expensive. The daily run should be a
  **scheduled task whose prompt is replaced** with Prompt 2 below — scheduled
  runs start fresh each day, which is exactly what you want.
- Run Prompt 1 (one-time setup) in a **brand-new regular session** with the
  bundle zip attached. Once it reports success, the session is done — don't
  reuse it.
- Run Prompt 3 (registry growth) in a **fresh session each time** you want to
  grow the registry. The validator gate makes each growth run self-contained,
  so there is no benefit to keeping one long growth chat alive — and the old
  growth chat is where the 35 corrupted rows came from.

Upload file: `rai_deterministic_scan_bundle_20260805.zip` (in this folder).

**CRITICAL — install into the PROJECT shared-file directory, not
`/home/ubuntu/`.** The Manus sandbox resets between tasks (the skill's own
learning log, July 13, records SKILL.md disappearing this way). Anything
under `/home/ubuntu/rai_scan/` will vanish, taking the dedup memory and
the page-diff baselines with it — and a lost baseline silently re-floods
the next run with old links. Everything therefore lives in the project
shared-file directory that the scheduled task already mounts (the same
place the canonical prompt and calendar live, e.g.
`/home/ubuntu/projects/daily-news-jul-2026-282d2cf2/`). Below, `$PROJ`
means that directory; the scripts are stdlib-only and run fine from
there, so nothing has to be copied into the sandbox at all.

**Same project is not enough — it must also survive the sandbox.** Every
chat session and every scheduled run gets a fresh `/home/ubuntu`. An
install that succeeded in a setup session and then "vanished" was written
to that ephemeral home, not to the project directory. Install to `$PROJ`
and the files persist for every later session and task run in that
project. (Also make sure `$PROJ` belongs to the project the
"Daily News_6am" task actually runs in; a different project mounts a
different directory.)

**Manual step before Prompt 2 goes live:** in Manus's connector/MCP
settings, add the RobotAIGeek MCP server (mcp-prod) so the daily agent can
call `coverage_check`. Use a **scoped writer-tier API key** — never an
admin key. If the connector isn't set up yet, the daily prompt degrades
gracefully to local-log dedup only.

**Byline (action required):** submissions are attributed server-side from
the API key — `news_submit` and `articles_submit` have no author
parameter. Manus's current key belongs to **jamie**, which is why the
Aug 5 queue items show `created_by: jamie`. To publish as **Aeon (user ID
211)**, issue an API key for Aeon and use THAT key in Manus's connector.
No prompt wording can override this. The prompt below additionally
records the intended author in each package's upload metadata so manual
uploads get the same byline.

---

## Prompt 0b — Top up an incomplete baseline (run before trusting coverage)

A `--force-all` baseline run over all 493 sources usually cannot finish
inside one deadline, so a large share of sources end as
`deadline_abandoned` and never get a first fetch. Until a source has a
baseline it can never produce a diff, so it contributes nothing to the
daily scan. Run this after install (and after uploading the updated
bundle, which adds `--missing-baseline-only`) until the reported due
count stops falling:

```
cd $PROJ/rai_scan && python3 scan_due_sources.py \
    --registry registry_v4_20260805.csv --state-dir state --out-dir out \
    --force-all --missing-baseline-only --deadline 240 --workers 32
```

It scans ONLY sources that still lack a baseline, so each run is small
and safe to repeat. Two or three runs converge. The residue that never
baselines is the genuinely blocked set (403s, dead URLs, JS-only pages,
WeChat) — report those source names so the registry-growth chat can fix
or replace the URLs; do not keep retrying them daily.

---

## Prompt 0 — Diagnose and repair an install that "disappeared"

Symptom: setup ran successfully in this project, but a later session or
scheduled run reports the scripts do not exist. Cause: the earlier install
went to `/home/ubuntu/rai_scan/`, which is sandbox-local. Same project
does NOT mean same sandbox — every session and every task run gets a
fresh `/home/ubuntu`. Only the project shared-file directory survives.

Paste this into a session in the same project (attach the bundle zip only
if step 2 reports it is not already in the project directory):

```
Diagnose and repair the deterministic scan pipeline install.

DO NOT write, rewrite, or improvise any of these scripts. They are tested
deliverables. If files are missing, reinstall them from the bundle zip; if
the zip is unavailable, report that and stop.

1. Print the full path of the project shared-file directory mounted for
   this session (the one holding the canonical daily-news prompt). Call it
   $PROJ. Confirm it is writable.
2. List $PROJ and report whether these exist:
   - $PROJ/rai_scan/ (and if so, list its contents plus rai_scan/state/
     and rai_scan/out/)
   - any rai_deterministic_scan_bundle_*.zip anywhere under $PROJ
   Also check whether /home/ubuntu/rai_scan/ exists in THIS sandbox.
3. Repair:
   - If $PROJ/rai_scan/ is missing but the bundle zip is in $PROJ, unzip
     it to $PROJ/rai_scan/ and create state/ and out/ subdirectories.
   - If /home/ubuntu/rai_scan/ exists in this sandbox and $PROJ/rai_scan/
     does not, copy the whole directory (including any state/ contents) to
     $PROJ/rai_scan/ before it is lost again.
   - If neither exists and no zip is attached, report that the bundle must
     be re-uploaded and stop.
4. Verify: cd $PROJ/rai_scan && python3 validate_registry.py registry_v4_20260805.csv
   Must print "RESULT: PASS".
5. If state/scan_state.json does not exist, establish the baseline:
   python3 scan_due_sources.py --registry registry_v4_20260805.csv \
       --state-dir state --out-dir out --force-all --deadline 300
   Report the stats JSON.
6. Report: $PROJ path, what existed before repair, what you installed or
   copied, validator result, baseline stats, and the final listing of
   $PROJ/rai_scan/ including state/. Do not draft any content.
```

---

## Prompt 1 — One-time setup

Run this **in the same project as the "Daily News_6am" scheduled task**,
with the zip attached. (If a previous install disappeared, use Prompt 0
instead.)

```
Set up the deterministic scan pipeline for the RobotAIGeek Tier 1 Daily News
Agent. The zip rai_deterministic_scan_bundle_20260805.zip is attached.

DO NOT write, rewrite, improvise, or "rebuild" any of these scripts. They
are tested deliverables and must be installed exactly as shipped. If
something appears missing or broken, report it and stop; do not substitute
your own implementation.

1. Identify the project shared-file directory mounted for this session
   (the directory holding the canonical daily-news prompt, e.g.
   /home/ubuntu/projects/daily-news-<hash>/). Call it $PROJ and print its
   full path. Confirm it is writable with a touch test. Everything below
   installs THERE, not under /home/ubuntu/, because the sandbox resets
   between tasks and would destroy the scan baselines and dedup memory.

2. Unzip the attachment to $PROJ/rai_scan/ (create it), then create
   $PROJ/rai_scan/state/ and $PROJ/rai_scan/out/. Read
   $PROJ/rai_scan/README_BUNDLE.md in full.

3. Validate the registry:
   cd $PROJ/rai_scan && python3 validate_registry.py registry_v4_20260805.csv
   It must print "RESULT: PASS". If it fails, stop and report the errors.
   registry_v4_20260805.csv is the new canonical source registry: it
   repairs 35 column-shifted rows from the Jul 30 registry (all 19 Japan
   company rows including FANUC, Yaskawa, Kawasaki, Omron, plus 16
   international organizations). Do not scan from any older registry file.

4. Establish the scan baseline (one time only), writing state and output
   inside the project directory:
   python3 scan_due_sources.py --registry registry_v4_20260805.csv \
       --state-dir state --out-dir out --force-all --deadline 300
   Expect many sources marked "baseline" and few candidates — that is
   correct on a first run. Report the stats JSON it prints.

5. Seed the dedup log. Take every story published or packaged in the last
   14 days (from the daily agent's published log, tracker, or the recent
   delivered packages), convert them to a JSON list of objects with fields
   date (YYYY-MM-DD), lane (news|article|video), title, url, companies
   (array), event_type (short phrase such as "funding", "product launch",
   "partnership"), save as $PROJ/rai_scan/seed.json, then run:
   python3 dedup_check.py seed --from-json seed.json --log state/published_log.jsonl
   Report how many entries were seeded.

6. Report the status of references/published_articles_log.csv in the
   skill directory. If it does not exist, say so and DO NOT create a
   substitute — the pipeline degrades gracefully without it (the local
   dedup log plus coverage_check cover the same ground).

7. Confirm whether the RobotAIGeek MCP connector is configured and whether
   coverage_check is callable. Report the result and, if it resolves to a
   user, report which user the API key belongs to (the byline must be
   Aeon, user ID 211). Do not attempt to reconfigure it yourself.

8. Report back: $PROJ path and writability, validator result, baseline
   scan stats, seeded entry count, published_articles_log.csv status, MCP
   connector status and key owner, and a listing of $PROJ/rai_scan/. Do
   NOT scan for news, draft any content, or modify the scheduled task in
   this session.
```

---

## Prompt 2 — Replacement scheduled daily prompt

Replace the scheduled task's prompt with the text below. It preserves the
Morning Package spec but moves scanning and dedup into scripts.

> Re-synced to SKILL.md (Aug 6 version) after a quality regression: the
> skill is the editorial authority and is read IN FULL every run. This
> prompt only replaces the *mechanics* (scanning, dedup surfaces, QC
> tooling). Word counts follow SKILL.md 3.4.1's 1,500 minimum, with an
> 1,800 ceiling for News per editorial decision. If Martti wants a lower
> News floor, amend SKILL.md 3.4.1 first — never let this prompt and the
> skill disagree.

```
Run the RobotAIGeek RAI Tier 1 Daily News Agent Morning Package as specified
in /home/ubuntu/projects/daily-news-jul-2026-282d2cf2/RobotAIGeek_Daily_News_Scheduled_Prompt.md,
with the deterministic-pipeline overrides below, which take precedence
wherever they conflict with that file.

START SEQUENCE:
1. Run python3 /home/ubuntu/skills/rai-tier1-daily-news-agent/scripts/verify_skill_version.py
   — halt and report if it fails.
2. Read the FULL SKILL.md (rai-tier1-daily-news-agent) and every bundled
   resource it marks as load-at-start, EVERY run. Each scheduled run is a
   fresh session with no memory of previous runs; the skill is the
   editorial authority and skipping it degrades output quality. The
   credit savings in this pipeline come from scanning and dedup mechanics
   below, never from skipping editorial references.

PATHS: $PROJ = the project shared-file directory mounted for this run (the
one holding the canonical daily-news prompt). The pipeline lives in
$PROJ/rai_scan/ and keeps its state there, because the sandbox resets
between tasks. Resolve $PROJ first and print it.

0. PREFLIGHT (first command of every run):
   cd $PROJ/rai_scan && python3 preflight_check.py --pipeline daily
   Exit 0 = ready; read the warnings and act on them (an unbaselined-source
   warning means coverage is thin, a missing-dedup-log warning means dedup
   is blind). Exit 1 = BLOCKED: report the exact errors and STOP. Do not
   rebuild, improvise, or substitute your own versions of any script, and
   do not fall back to manual browsing. A blocked preflight means the
   pipeline needs reinstalling from the bundle zip, which is a separate
   setup session.

SCANNING (replaces direct scanning of registry sources):
3. cd $PROJ/rai_scan && python3 scan_due_sources.py --registry registry_v4_20260805.csv --state-dir state --out-dir out --deadline 300
   The script enforces its own hard 300-second wall clock: it always
   finishes, reporting slow hosts as "deadline-abandoned (slow host)" in
   errors. Read out/scan_delta_<today>.json. This file IS the scan:
   candidates (each with source, tier, title, description, og_image,
   published_date, date_status, age_days, keyword hits), stale_excluded,
   needs_browser, and errors.
3c. STRICT SAME-DAY DATE GATE (SKILL.md Section 4 — non-negotiable):
   - `date_status: "same-day"` — drafting-eligible.
   - `date_status: "unverified"` — a page-scrape link with no machine
     readable date. You MUST confirm the publication date at the source
     before drafting. If it is not today's date in the source's own
     timezone, drop it and record the exclusion in the tracker.
   - `stale_excluded[]` — already dated before today. Do NOT draft these,
     do NOT use them to reach the 8-package target, and do NOT quietly
     re-date them. If same-day sourcing genuinely falls short, deliver the
     smaller verified package and explain the shortage (honest-shortage
     rule). Widening to prior-day items requires explicit user approval
     in the run request; only then rerun with --allow-prior-day and say
     so in the run log.
   Every package's evidence note must record the verified publication
   date and the source timezone used to judge it.
3b. FAILURE PROTOCOL: if the script exits without writing today's
   scan_delta file, retry ONCE with --deadline 180 --tier P0. If that also
   fails, do NOT fall back to manually scanning the registry in the
   browser. Instead: browse at most the P0 sources listed in needs_browser
   and errors of the most recent successful scan delta (hard cap 15
   pages), draft from what you find, and open the run log with a
   "SCAN SCRIPT FAILED" line describing the error so it gets fixed.
   Deadline-abandoned sources need no follow-up; they are retried
   automatically on the next run.
4. Do NOT open registry source pages in the browser except: (a) sources in
   needs_browser, (b) sources in errors, (c) pages needed to verify a story
   you are actually drafting. Hard cap: 15 browser-opened source pages per
   run outside of story verification. On Mondays, per SKILL.md Section 4,
   do the WeChat review pass FIRST (before drafting any packages),
   restricted to registry sources whose collection route includes WeChat,
   capped at 20 browser steps.
5. First-hand-source rule (unchanged in spirit): every drafted story must
   be verified against the first-hand source in the registry; aggregators
   (TechTimes, Interesting Engineering, Logistics Viewpoints, etc.) are
   never primary sources.

DEDUP (SKILL.md Section 4.1 applies in full; only the SURFACES change —
scripted log checks and coverage_check replace browsing the live pages):
6. For every candidate you select for drafting, run (always from
   $PROJ/rai_scan — the log path is relative):
   cd $PROJ/rai_scan && python3 dedup_check.py check --title "<working headline>" \
       --companies "<Company1,Company2+ alias set: product brand, corporate name, Chinese name>" \
       --event-type "<funding|product launch|partnership|...>" \
       --log state/published_log.jsonl \
       --csv-log /home/ubuntu/skills/rai-tier1-daily-news-agent/references/published_articles_log.csv
   Pass the FULL alias set as companies (Section 4.1.1). Exit 2 = a
   duplicate-claim, duplicate-title, or 5-day-company-recency match: drop
   the story, or proceed only if the new event is a materially different
   Tier 1 development, noting the justification in the run log.
6b. For every story that passes the local check, call the coverage_check
   tool on the RobotAIGeek MCP connector with the story's topic/companies
   before drafting — it sees published AND in-review content across ALL
   contributors (this replaces the live News/Articles page check). Skip
   stories it reports as covered. One call per story, no retries. If the
   MCP connector is unavailable, note "coverage_check unavailable" in the
   run log and proceed on the local check alone.
6c. Then apply the remaining Section 4.1 judgments yourself against the
   check outputs: same-event rule (date the event, not the article),
   thematic saturation (one capital-flow/industry-trend piece per week),
   same-thesis rule, and claim-level checks for recurring companies.
   Merging beats padding. Do not browse the live site for deduplication.

DRAFTING (the skill governs; this prompt adds nothing to style):
7. Output target per SKILL.md Sections 4 and 13: minimum 8 upload-ready
   packages, at least 1 Article Post and at least 3 non-China stories,
   with the honest-shortage exception (never pad with older, weaker,
   duplicate, or lower-tier content). Word counts per SKILL.md 3.4.1:
   News Posts minimum 1,500 words in the public body, ceiling 1,800;
   Article Posts 1,500-2,500. Reach the minimum through the required
   Pillar-Sync elements at full depth, never through filler.
8. STYLE AND STRUCTURE: apply SKILL.md Sections 3 through 3.7 and the
   Section 14 final checklist IN FULL from the freshly read skill — not
   from any summary in this prompt. That includes Pillar-Sync SEO/AEO/GEO
   execution, dynamic modules, the metadata taxonomy, pillar internal
   links, the editorial pulse check, Wise Peer voice, Benchmark
   Publication Style, the Article Variance Engine reference, and the
   originality and attribution standard.
9. Hero images: use each candidate's og_image from the scan delta as the
   first option — verify it is a real JPG under 5 MB with a proper credit
   line (prefer actual event photography). Only hunt for images in the
   browser if the og_image is unusable.
10. Run scripts/audit_originality.py on every public body. Maximum 2
    revision passes per piece; if blocking findings remain after 2 passes,
    exclude the piece and record it in the run log.
10b. Run the compliance lint on every public body (from $PROJ/rai_scan):
    python3 package_lint.py <body file> --lane <news|article> --run-date <today>
    It enforces the mandatory standard disclaimer, the word-count band
    (news 1,500-1,800 / article 1,500-2,500), no em dashes, no bare "$"
    without a currency prefix, no third-party outlet attribution in the
    body ("according to Reuters" etc., SKILL 14.11), no "What is X?"
    openers, no labeled ELI5/Hard Truth headings, and warns on banned
    AI-phrasing (SKILL 3.5) and on non-USD amounts missing US$
    conversions. Exit 1 = fix the listed errors and re-run. No piece
    enters the package until its lint passes.

PACKAGING:
11. Deliver YYYYMMDD_RobotAIGeek_Daily_Package.zip plus the separate
    tracker XLSX and run log. Produce the daily knowledge review summary
    per SKILL.md Section 8 as concise Markdown; use DOCX format on
    Mondays.
11b. AUTHOR: every package's upload metadata block must state
    "Author: Aeon (user ID 211)". If you submit through the RobotAIGeek
    MCP connector, the byline comes from the API key: verify the key
    resolves to Aeon before submitting, and if a submission lands under
    any other user, stop submitting and report it — do not keep filing
    items under the wrong byline.
11c. DATE LINE: each package's metadata must carry the verified
    publication date of the underlying event and confirm it equals the
    run date. Any package whose source date is not today must not be in
    the delivery.
12. After packaging, register every packaged story in the dedup log AND
    append the confirmed-published rows to
    references/published_articles_log.csv per SKILL.md once the user
    confirms publication:
    cd $PROJ/rai_scan && python3 dedup_check.py append \
        --log state/published_log.jsonl \
        --date <today> --lane <news|article|video> \
        --title "<final headline>" --url "<planned or final URL>" \
        --companies "<Company1,Company2>" --event-type "<event type>"
13. Set every package to "Do not publish automatically"; never publish or
    post without explicit user confirmation.
```

---

## Prompt 3 — Registry growth (fresh session per growth run)

```
Grow the RobotAIGeek first-hand source registry. The canonical registry is
$PROJ/rai_scan/registry_v4_20260805.csv (if a newer registry_v*.csv
exists in that directory, use the newest). Target for this run: <REGION OR
SOURCE TYPE TO GROW — e.g. "20 more European robotics companies with IR
pages" — FILL IN>.

Rules:
1. Read the header row: every new source must fill the exact same 18
   columns. Allowed values — priority_tier: P0, P1, or P2 only.
   update_frequency: Daily, Weekly, Monthly, Occasional, or Event-driven
   only. collection_route: combinations of "page scrape", "RSS", "API",
   "WeChat", "search query", "IPO calendar", "IR calendar", "exchange
   filings", "HKEX filings" joined with " + ". rss_or_api: "RSS: <url>",
   "API: <name>", or "None — scrape". url_news and url_home must be plain
   URLs with no annotations in parentheses.
2. First-hand sources only: company newsrooms and IR pages, government and
   regulator portals, exchange disclosure feeds, standards bodies, and
   research institutions. No aggregators or trade media.
3. Prefer sources with an RSS feed or API — actively look for feed URLs
   (common paths: /feed, /rss, /news.xml, .atom) and record them, because
   RSS sources cost the daily pipeline almost nothing.
4. Deduplicate against the existing registry by source_name AND url_news
   before adding anything.
5. Write the updated file with Python's csv module (never assemble rows by
   string concatenation — unquoted commas inside prose are what corrupted
   the Jul 30 registry).
6. MANDATORY GATE: run
   python3 $PROJ/rai_scan/validate_registry.py <new file>
   and iterate until it prints "RESULT: PASS". A registry that does not
   pass is not a deliverable.
7. Save the result as $PROJ/rai_scan/registry_v<next>_<YYYYMMDD>.csv,
   plus a matching XLSX copy, and deliver both along with a summary table
   of added sources (name, region, tier, route, has-RSS yes/no) and the
   validator output. Do not modify or delete the previous registry version.
```
