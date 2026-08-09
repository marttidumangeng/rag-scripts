# ARPI Dedicated Topic Writer Prompt v9 — Deterministic Pipeline

Produce exactly one upload-ready evergreen article package for the editorial
date. The `arpi-dedicated-topic-writer` skill remains the governing editorial
workflow; this prompt replaces only the *mechanics* (assignment resolution,
market scan seeding, assembly, QC) and the Word-first delivery standard.
Never publish; every package requires editorial review.

## Read the skill first, in full, every run

Read the entire `arpi-dedicated-topic-writer` SKILL.md BEFORE any drafting.
Each run is a fresh session with no memory of previous runs, and the skill
is the editorial authority. The credit savings in this pipeline come from
the deterministic mechanics below, never from skipping editorial
references.

**Precedence.** The skill governs every editorial judgment EXCEPT the five
overrides listed here, which are deliberate and current. Anything else
that appears to conflict: the skill wins, and you must record the conflict
in the run log so this prompt can be corrected.

| Skill section | Override | Reason |
| --- | --- | --- |
| §6, §8 body length 800–1,200 words | **1,200–1,600 words** | Editorial decision carried from prompt v8; delivered packages already follow it. Extending beyond 1,600 still requires the skill's justification in the editor summary. |
| §9 deliver a Markdown draft | **Word-first `.docx`** via `build_docx.py`; Markdown files are internal build inputs only | Word-first delivery standard from prompt v8. |
| Gate 4 "Open RobotAIGeek" for the duplicate check | **`coverage_check` MCP call** | Sees in-review as well as published items; the live site is a single-page application that returns a loading shell to the sandbox browser. |
| Gate 4 review the latest 3–5 hero images on the site | **local `heroes/` archive**, with up to 3 page fetches only when the archive is empty | Same reliability and cost reasons. |
| §4 broad market-development scan by searching | **`market_ledger_seed.py` first**, then verify the seeded items at first-hand sources | The relevance gate, Tier 1 standard, and ledger fields in §4 all still apply in full. |

Everything else in the skill applies as written, including the Tier 1
source standard, the verification protocol, the original-analysis
requirement, the Wise Peer voice, the banned formulaic phrases, the
abbreviation rule, the no-inline-citation rule, and the Evidence Source
Notes handling.

## Canonical inputs and paths

Two locations matter, and they behave differently:

* **`$PROJ`** = the mounted project directory (the one holding
  `ARPI_Content_Calendar_Strategy_v6.xlsx`). It is RE-MATERIALIZED from
  the project's uploaded files at the start of every session, under a new
  directory hash each time. Only files uploaded to the project survive
  there. Anything a session writes into it does NOT come back.
* **`$WORK`** = `/home/ubuntu/arpi_topic`, a scratch directory this run
  creates. Everything the pipeline needs is unpacked here at the start of
  the run and thrown away at the end. That is fine and expected.

Resolve `$PROJ` by searching, never by assuming a hash:

```
ls -d /home/ubuntu/projects/*/ 2>/dev/null
ls /home/ubuntu/projects/*/ARPI_Content_Calendar_Strategy_v6.xlsx 2>/dev/null
```

## Bootstrap (runs every time, takes seconds)

Do this before anything else. It is idempotent: running it twice is
harmless, and it replaces the old separate setup session entirely.

```
PROJ=<the directory found above>
WORK=/home/ubuntu/arpi_topic
mkdir -p $WORK && cd $WORK
unzip -o $PROJ/arpi_topic_bundle_20260806.zip -d $WORK
mkdir -p $WORK/heroes $WORK/scan_history
python3 -c "import openpyxl" 2>/dev/null || pip3 install -q openpyxl
python3 -c "import docx" 2>/dev/null || pip3 install -q python-docx
python3 preflight_check.py --pipeline topic --calendar $PROJ/ARPI_Content_Calendar_Strategy_v6.xlsx
```

If `arpi_topic_bundle_20260806.zip` is not in `$PROJ`, STOP and report:
"bundle zip missing from the project files — upload
arpi_topic_bundle_20260806.zip to the project, then re-run." Never
rebuild, rewrite, or improvise the scripts.

If the preflight exits non-zero, report its exact errors and STOP.

Seed the hero archive if the project carries one: copy any
`$PROJ/heroes/*.jpg` into `$WORK/heroes/` before the differentiation
check. If it is empty, the run falls back to at most 3 page fetches, and
you should deliver this run's hero for upload to `$PROJ/heroes/` so the
archive grows.

All later commands run from `$WORK`. The calendar is always read from
`$PROJ` and never modified.

## Preflight (deterministic)

1. Resolve the assignment:
   `cd $WORK && python3 assignment_lookup.py --calendar $PROJ/ARPI_Content_Calendar_Strategy_v6.xlsx --out assignment.json`
   For a manual rerun with a user-specified date, add `--date YYYY-MM-DD`.
   The script resolves RUN_DATE in Asia/Shanghai, exact-matches Tab 4,
   derives the Post Slot, and extracts the Tab 5 framework.
   Exit 3 = no post scheduled for RUN_DATE: report that and stop.
   Exit 4 = framework section missing: report that and stop.
   Log the returned week label, asset class, title, and post slot as the
   preflight record.
2. Duplicate gate: call the `coverage_check` tool on the RobotAIGeek MCP
   connector with the scheduled title. If the same topic is already
   published or in the pipeline, report the match and stop (unless the
   user explicitly requested a revision). Do not browse the live site's
   archive for this — besides costing steps, the site is a single-page
   application and direct article navigation returns a loading shell in
   the sandbox browser (observed in the Aug 6 run), so browsing is also
   unreliable evidence.
3. Series continuity: `assignment.json` lists `series_prior_posts` from
   the calendar. Confirm which are live with ONE `articles_search` MCP
   call; record their titles, dates, and URLs as the continuity anchors.
   Write the new article as the next chapter: build on the series' prior
   analytical ground without repeating it, keep previews of later
   scheduled posts concise, and never contradict published series figures
   without explicitly citing the newer source.
4. Hero differentiation: review the local `$WORK/heroes/`
   archive (copies of previous heroes are saved there in step "Assets").
   Only if that folder is empty, fetch the hero images of the latest 3
   published articles (maximum 3 page fetches) and note the visual
   patterns the new hero must avoid.

## Market-Development Scan (seeded, not browsed)

5. Seed the ledger:
   `python3 market_ledger_seed.py --assignment assignment.json --keywords "<topic keywords incl. synonyms and spelled-out abbreviation forms>" --registry registry_v4_20260805.csv --scan-dir $WORK/scan_history --out ledger_seed.json`
   The daily news pipeline lives in a DIFFERENT Manus project, so its scan
   deltas are not reachable from here unless copies have been placed in
   `$WORK/scan_history/` at bootstrap. If that folder is empty the seed runs
   in RSS-only mode, which is expected and acceptable. Record which mode
   ran in the run log, and never let an empty scan history become a reason
   to fall back to broad manual browsing — the caps in step 7 still apply.
6. Apply the v8 relevance gate to the seed entries: retain a development
   only if it materially affects the topic's buyer economics, technical
   capability, safety or regulatory requirements, use cases, market
   structure, supplier position, or geographic competition.
7. Verify every retained development at its first-hand source. Prefer
   fetching the page as text; use the browser only when a page requires
   it. Hard cap for this whole phase: 10 browser-opened pages plus at
   most 5 targeted web searches for material gaps the seed missed.
8. Record the final Market-Development Ledger (date, development, source
   tier, direct URL, verified claim, relevance, evidence limitation,
   inclusion decision). This is an article-relevance scan, not a news
   roundup; do not pad it.

## Source and originality standards (unchanged from v8)

* Tier 1 sources for every pricing, market size, shipment, wage, tariff,
  revenue, and procurement figure: IFR, World Bank, ILO, IMF, OECD,
  national statistical agencies and customs authorities, central banks,
  official procurement portals, listed-company filings. Tier 2 research
  and peer-reviewed work for context only. Never LinkedIn, blogs, Medium,
  Substack, Reddit, Quora, AI-generated content, press-release
  aggregators, SEO pricing guides, or vendor marketing for factual
  claims; vendor documentation for technical specifications only.
* For every key figure confirm value, period, units, currency, geographic
  scope, and disclosure scope at the primary URL, and record it in the
  Evidence Source Notes. Unverifiable figures are omitted or labeled
  directional with an Editor Note. Never invent a value. Treat a company
  announcement as proof of its own announcement only.
* Include at least one original analytical layer (country comparison,
  buyer decision matrix, scope-adjusted ranking, TCO model, procurement
  scenario, or sensitivity analysis); state the method and limitations;
  never present unlike disclosure scopes as directly comparable.

## Drafting artifacts

Write these files (they are the build inputs, not deliverables):

* `body.md` — the publishable body ONLY. 1,200–1,600 words, Wise Peer
  voice, opens with a specific commercial insight, uses the framework
  subheaders from `assignment.json` as `## ` H2 headings, flowing
  paragraphs (bullets only in a labelled checklist/questions section),
  no dashes as parenthetical breaks, every abbreviation spelled out at
  first use with the short form in parentheses (ISO currency codes,
  company names, and product model numbers exempt), NO inline citation
  markers of any kind, no workflow or publication names, and a definitive
  forward-looking close tied to the procurement or investment thesis.
  CURRENCY: every monetary amount carries an explicit currency prefix
  (US$, RMB, EUR, GBP, KRW, SGD, JPY); never a bare "$". Non-USD amounts
  include an approximate US$ conversion in parentheses. This applies to
  illustrative model inputs too, not only sourced figures — the Aug 6
  package shipped 25 bare "$" amounts and zero "US$", which this rule and
  the lint now prevent.
  Embed table graphics with `{{table:filename.png}}` on its own line.
* `evidence.md` — the numbered Evidence Source Notes: each entry names
  the source, its direct primary URL, and the exact claim it supports.
* `meta.json` — headline, slug, summary, category, tags, meta_title,
  meta_description, hero_credit, and `"author": "Aeon (user ID 211)"`.
  Every package publishes under Aeon; if you submit through the
  RobotAIGeek MCP connector the byline comes from the API key, so verify
  the key resolves to Aeon and stop and report if a submission lands
  under any other user.
* Hero image — photorealistic generic true JPG, 16:9, no logos, branding,
  text, or watermarks, visually distinct from the heroes reviewed in
  preflight, saved under the exact `hero_filename` from
  `assignment.json`. Copy it into `$WORK/heroes/` and ALSO deliver it as a file the
  user can upload into the project so the archive survives future runs.
* Table PNGs from deterministic code, and the Excel workbook with
  underlying values, formulas, source ledger, and analytical notes.

## Assembly and QC (deterministic)

9. Build the Word deliverable:
   `python3 build_docx.py --assignment assignment.json --body body.md --evidence evidence.md --meta meta.json --hero <hero file>`
   It assembles the cover page, metadata table, styled body, embedded
   PNGs, the internal-only Evidence Source Notes closing page, and the
   disclaimer, then re-opens the file and prints `RENDER TEST: PASS`.
   Anything other than PASS: fix and rebuild.
10. Lint:
    `python3 article_lint.py body.md --run-date <RUN_DATE> --hero <hero> --docx <docx> --exempt "<company/product short forms used>"`
    Fix all ERRORs (maximum 2 revision passes; if errors persist, stop
    and report rather than shipping). Judge each warning and note the
    judgment in the QC report.
11. Complete the non-mechanical QC yourself: every key figure maps to an
    Evidence Source Notes entry, no prohibited source supports a factual
    claim, the original analytical layer and its limitations are stated,
    all required framework headings are present, and the article is
    consistent with the published series posts.

## Delivery

Deliver the `.docx` package, hero JPG, table PNGs, Excel workbook, final
Market-Development Ledger, and a QC report that includes: the preflight
record, seed mode (scan-history or RSS-only), series-continuity anchors,
source tiers used, limitations, the original analytical layer, hero
differentiation notes, and the lint output. Do not publish; wait for
editorial review.

## Stop conditions

Missing canonical input; assignment_lookup exit 3 or 4; coverage_check
reports the topic already covered; a material factual claim cannot be
adequately verified; lint errors persist after 2 revision passes. On any
stop, explain clearly and do not draft an alternative topic.
