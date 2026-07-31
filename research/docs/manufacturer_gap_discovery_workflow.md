# Manufacturer & Robot Gap Discovery Workflow

A broad, multi-source discovery workflow whose goal is to find as many **robot
manufacturers and their robots as possible that are not yet present in the
prod database**, and stage them in review-ready JSON that matches the
`StagedCompany` / `StagedRobot` schemas used by the existing bulk-import
pipeline (`cli.py import`). It complements the existing discovery workflows:

| Workflow | Scope | Entry point |
|---|---|---|
| Competitor gap discovery | Companies listed on robolist.ai only | `competitor_gap_discover.py` |
| Greenfield import | Enrich + import a *known* list of companies | `overnight_greenfield_import.py` |
| **Manufacturer gap discovery (this)** | **Any manufacturer on any harvestable source, plus their robot catalogs** | `manufacturer_gap_discovery.py` |

Nothing is ever imported automatically. The output is a staging file for human
review, then import through the normal dry-run pipeline.

## Prerequisites

The workflow reads prod through the same `IMPORT_SYNC_*` API used by the other
research scripts (`load_env.py` pulls credentials from
`robotaigeek-server/.env`). The optional LLM screen and website search use
`GEMINI_API_KEY` and `SERPER_API_KEY` from the same file; both are fail-open,
so the workflow degrades to heuristics (with `confidence: low`) if they are
missing.

## Step 1 — Refresh the prod baseline

```
python dump_prod_baseline.py
```

Pages through `/api/import/companies/` and `/api/import/robots/` and writes
`staging/reports/prod_baseline.json` containing every prod company and robot
plus pre-normalized name indexes (`company_name_index`, `robot_name_index`,
website hosts). Every later dedupe decision is made against this file, so
refresh it before each discovery run. A full dump takes about 15 minutes at
the API's paging rate (695 companies / 4,533 robots as of 2026-07-29).

## Step 2 — Run the discovery pipeline

```
python manufacturer_gap_discovery.py                  # full run (stages A-E)
python manufacturer_gap_discovery.py --harvest-only   # stages A-C only
python manufacturer_gap_discovery.py --resume         # reuse harvest file
python manufacturer_gap_discovery.py --max-companies 40
python manufacturer_gap_discovery.py --min-score 60   # only multi-source hits
```

### Stage A — Baseline

Loads `prod_baseline.json` and builds three match indexes: company name
variants (see dedupe rules below), per-company robot keys
(`{company}::{robot}`), global robot names, and website hosts.

### Stage B — Multi-source manufacturer harvest

| Source | Method | Typical yield |
|---|---|---|
| robolist.ai | sitemap + category pages | ~1,280 companies |
| aparobot.com | humanoid directory | ~120 companies |
| Wikipedia | recursive category crawl (robotics companies by country, UAV manufacturers, medical/industrial/service robots), 429-aware with proper UA and retry | ~500 pages |
| Local source lists | `seeds/gap_sources/*.md|csv` extracted by `harvest_local_sources.py` (Gemini classifies manufacturer vs agency/VC/software) then loaded via the `local_sources` harvester | ~230 manufacturers from 7 lists |
| Manual seeds | `seeds/gap_discovery_seeds.txt`, one `Name \| website \| country \| category` per line | as provided |

To add a new list-page source (e.g. a VC portfolio or industry roundup): save the
page content as markdown into `seeds/gap_sources/`, run
`python harvest_local_sources.py` (updates
`staging/gap_discovery/local_sources_harvest.json`), then merge incrementally:

```
python manufacturer_gap_discovery.py --merge-source local_sources
```

`--merge-source` harvests just that source, merges it into the existing harvest
file, runs Stage D only for companies new to the harvest, and merges Stage E
output into the existing `staged_import.json` instead of overwriting it.

Raw harvest is checkpointed to `staging/gap_discovery/harvested_manufacturers.json`
so re-runs with `--resume` skip the scraping.

### Stage C — Merge and dedupe vs prod

Harvested names merge across sources (multi-source hits rank higher), then
each is tested against the baseline with progressively aggressive matching:

1. **Iterative suffix stripping** — corporate/domain suffixes (`Co., Ltd.`,
   `Robotics`, `Technologies`, `Heavy Industries`, …) are stripped repeatedly
   on both sides, so `Yamaha Robotics` matches
   `Yamaha Motor Co., Ltd. (Robotics Division)`.
2. **Parenthetical variants** — prod names like `Epson (Seiko Epson
   Corporation)` index both the outer and inner names.
3. **Known equivalents map** — `_KNOWN_PROD_EQUIVALENTS` handles conglomerates
   whose robotics arm is branded differently in prod (e.g. `Kawasaki Heavy
   Industries` → `Kawasaki Robotics`). Extend it as reviewers find more.
4. **Junk filter** — `_NON_MANUFACTURER_RE` drops countries, universities, and
   generic words; Wikipedia entries whose title matches a prod *robot* name
   are dropped as robot-model pages, not companies.

Output: `staging/gap_discovery/gap_manufacturers.json` (scored, sorted).

### Stage D — Website resolution and robot catalog discovery

For each gap company (highest priority first):

1. **Website resolution**, tiered: seed URL → Wikipedia infobox external links
   → robolist company page → serper.dev search. Every candidate passes
   `company_website_resolve.py` screening (aggregator/social/news domains
   rejected, domain-vs-name match, live HEAD/GET validation).
2. **Alias guard** — if the resolved domain already belongs to a prod company,
   the harvested name is an alias of an existing record; it is skipped and
   logged in `skipped_alias_domains` rather than staged as a duplicate.
3. **Robot link mining** — the homepage (and one product-listing page deep) is
   mined for product-like links using keyword heuristics.
4. **LLM screen (Gemini 2.5 Flash)** — mined candidates are classified
   robot-vs-junk in one JSON call per company: navigation text, components
   (servos, ballscrews, grippers), accessories, and third-party items are
   dropped; names are canonicalised and anglicised (`KXRシリーズ` → `KXR
   Series`). Fail-open: without the LLM the heuristic list survives with
   `confidence: low` and a note in `research_notes`.
5. **Robot dedupe** — surviving robots are checked against the prod robot
   index both per-company and globally.

### Stage E — Staging output

| File | Content |
|---|---|
| `staging/gap_discovery/staged_import.json` | Single review-ready file: `{companies: [StagedCompany], robots: [StagedRobot], skipped_alias_domains: [...]}` |
| `staging/gap_discovery/robots/{company-slug}/*.json` | Per-robot files in the exact layout `cli.py import --dir` consumes |
| `staging/gap_discovery/gap_discovery_summary.md` | Human-readable summary table |

Every staged record carries `sources` (where it was found), `confidence`, and
an `[AI Research]` note explaining provenance and what still needs enrichment.
Staged robots are name+URL candidates only — specs, images, and descriptions
must come from the enrichment workflow (`overnight_queue_enrich.py`) after
import, per the no-hallucinated-specs rule.

## Step 3 — QA passes

The harvest is intentionally broad, so run the QA scripts (each supports
`--dry-run`) before handing the file to reviewers:

| Script | What it does |
|---|---|
| `gap_staging_qa.py` | Drops robolist hash-slug artifacts; moves companies with no website and no robots to a `low_signal_companies` bucket; drops navigation-junk robot names. Preserves the pre-QA file as `staged_import.raw.json`. |
| `gap_staging_qa2.py` | Merges same-domain duplicate companies (keeping the canonical name and reassigning robots), demotes wrong-domain resolutions (domain shares no tokens with the name, minus a `DOMAIN_EXCEPTIONS` allowlist like `fbr.com.au` → Fastbrick Robotics), and drops robot-model/artifact names staged as companies. |
| `gap_staging_qa3_names.py` | Translates residual CJK robot names to official English/romanized names via Gemini, annotating `research_notes`. |
| `gap_staging_qa4_junk.py` | Drops "robots" that are actually blog posts, news items, FAQs, or category pages. |
| `gap_alias_cull.py` | Human-judgment cull of `possible_prod_aliases.json` suspects. Verdicts (cull / demote / keep, with reasons) live in its `VERDICTS` map — roughly half the suspects are false positives (Boschung ≠ Bosch), so never blind-delete. Cull-verdict entries are purged from `low_signal_companies` too. |
| `gap_staging_qa5_deep.py` | Deep sweep: retailer/placeholder companies, multilingual nav noise ("À propos", "会社概要"), non-robot products (testers, resins, cables), and a Gemini rescreen of every company holding ≥35 robots (the mining cap concentrates noise; expect 50–100% drops there). |
| `gap_staging_qa6_brands.py` | Brand-duplicates and residual CTA junk. `BRAND_DUPLICATES` (e.g. Motoman → prod YASKAWA Electric) drops the company row but parks its robot leads under `parked_for_enrichment` tagged with `prod_company_name` — brand domains evade both name and domain guards, so this map is reviewer-fed. Also strips leading-CTA robot names ("View all…", "Learn more…", "Compare…") and marketing tokens (whitepaper, newsletter, catalog). Agencies/institutes (ESA, KIST) are deliberately kept. |
| `gap_staging_qa7_final.py` | Final residue: non-company culls via `COMPANY_CULL` (article-style Wikipedia pages, marketplaces like HowToRobot), language-switcher names and 2-letter language codes, bare pagination digits, bare spec fragments (">1000kg"), list-item fragments, and trailing-CTA names — with a short-model-name whitelist (M9, Z4) to avoid false positives. Companion fix: `domain_matches_company` no longer accepts stopword tokens ("an" ~ animenewsnetwork.com bug). |
| `gap_staging_qa8_entities.py` | Human-judgment wrong-entity culls (`WRONG_ENTITY` map with reasons): robot names staged as companies then token-resolved to unrelated domains (FEDOR → pool merch, MABEL → T-shirts, Ee/Fi/Us → telecom/wi-fi.org/usa.gov), plus mojibake-lead drops with a RE-MINE flag (`REMINE_LEADS`). Companion code guards in `company_website_resolve.py`: domain-family skip-list (linkedin.*), `name_too_generic_to_resolve`, and the `page_looks_like_robot_company` landing-page sniff. |
| `gap_sync_import_dirs.py` | **Mandatory after any change to `staged_import.json`.** Rebuilds `robots/{slug}/` dirs from the JSON — the JSON is the single source of truth and the dirs are a build artifact; unsynced dirs resurrect culled junk at import time. |
| `gap_summary_regen.py` | Regenerates `gap_discovery_summary.md` from the final cleaned file (the in-run summary only reflects the last batch). |
| `gap_final_verify.py` | Integrity checks: dup slugs/domains, orphan robots, nav/CJK residue, prod-domain residue, dir/JSON sync. Must end `SYNC OK` before review/import. |

Everything dropped or demoted is retained inside `staged_import.json` under
`qa_dropped` and `low_signal_companies` so reviewers can rescue entries.

## Step 4 — Review and import

1. Review `staged_import.json`; delete or fix entries as needed, then re-run
   `gap_sync_import_dirs.py` and `gap_final_verify.py` (must report `SYNC OK`).
2. **One company at a time, never the whole file**: import the company, then its
   robots with `python cli.py import --dir staging/gap_discovery/robots/{slug}/ --dry-run`,
   inspect the dry-run, then rerun without `--dry-run` once clean.
3. Imported robots land with `status=pending_review` and flow through the
   normal moderation queue and enrichment passes.

Run results 2026-07-29 (first full run): baseline 695 companies / 4,533 robots;
harvested 1,769 manufacturers across all sources; 1,428 not in prod; after all
QA passes, the alias cull (23 culled, 6 demoted, 21 false positives kept), and
all QA rounds **978 staged companies (all with validated websites) and 4,007
staged robots**, plus 332 low-signal companies, 37 alias-domain skips, and 22
Motoman robot leads parked for Yaskawa enrichment. Institute entries (ESA,
KIST) and off-category products at diversified manufacturers are deliberately
left for per-company review at import time.
Side finding: prod 'Unity Robotics' is missing its website (unityrobots.com)
— backfill it on the prod record.

## Re-running

The workflow is idempotent per baseline: re-run `dump_prod_baseline.py` after
each import wave so newly imported companies drop out of the gap list, then
`manufacturer_gap_discovery.py` again. New sources can be added as
`harvest_*(sess)` functions registered in `HARVESTERS`; manual leads go in
`seeds/gap_discovery_seeds.txt`.
