# Local-document intake plan (WAIC brochure trove)

**Source:** `C:\Users\tramk\Downloads\Robots and Companies\Robots & Companies record - July 27 to July 28`
~110 files (PDF / PPTX / images / 2 videos), ~45 mostly-Chinese embodied-AI vendors,
collected at WAIC late July 2026. Samples scanned 2026-08-12 (Flexiv Rizon datasheet,
Kepler product manual): spec density is higher than most OEM websites, family/variant
structure is explicit.

**Goal:** company + robot records extracted as completely and as correctly as possible,
flowing through the EXISTING staging → validate → bulk-import → verify pipeline. No
parallel machinery; documents become one more acquisition tier.

**Design principles**

- Extraction reports what the source says; catalogue mapping is separate
  (`extractors/base.py` doctrine — reuse `ExtractedProduct`, don't invent a new shape).
- Vendor brochures are CLAIMS. Conflicts inside a doc (Kepler: header 150 kg vs table
  135 kg) get recorded as conflicts, never silently resolved. OEM website wins over a
  doc on any disagreement; the doc fills gaps.
- Every paid Gemini call goes through `spend_guard.client()` with the run capped —
  hard caps + spend logging land in the SAME change as the caller.
- One company at a time through staging review (no mass import). New robots only for
  companies that already have records; gaps on live robots are reported for the
  enrichment pipeline, not patched here.

---

## Phase 0 — Inventory & triage (deterministic, no LLM)

New script `intake_local_files.py`:

1. Walk the folder; md5-hash to collapse the "(1)" duplicate copies.
2. Classify: pdf / pptx / image / video. Probe PDFs with pypdf for page count and
   text-layer presence (text-extractable vs image-only → vision required).
3. Map file → company (filename + page-1 text), tag doc type
   (datasheet / product manual / company profile / catalogue / investor deck),
   language (EN / CN / pair).
4. **Exclusions:** investor/BP material (`星动纪元BP 1025 EN.pptx` and any deck with
   funding slides) is flagged `excluded: true` — never extracted from, never uploaded.
   Loose photos/videos are routed to media candidates, not data sources.
5. Cross-check prod (`company_search`, `robot_search`): does the company exist, which
   robots are already live, what's genuinely new.

Output: `staging/intake/manifest.json` + a ranked staging order
(famous greenfield first, per standing backfill priority).

## Phase 1 — Provenance (the citation problem)

Our trust chain is URL-based (release-year citation gate, verify_content wants the
robot named at a fetchable URL). Per document, in order:

1. **Trace to OEM-hosted copy** — search the vendor site/download section for the same
   document (title + filename heuristics, Serper for search — never Gemini grounding).
   Found → that URL is the citation and `source_url`.
2. **No hosted copy** → upload the PDF as a `RobotInformationSource` attachment
   (public CDN — acceptable for marketing collateral, which is what booth handouts
   are; excluded material never reaches this step). `source_url` = product page if
   one exists, else company site.
3. Record doc version/date (e.g. Rizon datasheet V2.0, 2024-09) with the facts —
   staleness rule: website supersedes document.

## Phase 2 — Extraction (vision-first, budgeted)

New rung `extractors/pdf_document.py` → emits `ExtractedProduct` objects:

- Render pages with PyMuPDF at ~2x scale; send page batches to Gemini multimodal
  via `spend_guard.client()` with a structured-output schema:
  `company{name, website, hq, founded}` + `products[]{name, family, variant_of,
  specs (typed), applications, availability, stated_release_year}`.
- These are design-heavy brochures — plain text extraction mangles the styled
  tables/infographics; vision is the load-bearing path. Text-layer PDFs still get a
  pypdf pass as a cross-check against vision hallucination: numbers the vision pass
  claims must appear in the text layer when one exists.
- CN docs: same pass, English output, original name kept in `alias`/`extra.zh_name`
  (zh-dedupe risk). When an EN/CN pair exists, EN is primary, CN is cross-check.
- Intra-doc numeric conflicts → `extra.conflicts`, surfaced in the staging report.
- Embedded images: `fitz` extraction with the size/aspect/pictogram filters learned
  on Daihen; staged as photo candidates per robot (4-photo minimum). Hero choice
  stays a review step, not automatic.
- Cost envelope: ~1,100 page renders on Flash vision, no grounding — cents, well
  inside the $10/day guard; still set an explicit per-run file cap.

## Phase 3 — Mapping & staging

Reuse the existing path unchanged:
`ExtractedProduct` → staged robots → `staging/companies/<slug>.json` →
`validate_staging` → `import_staging.py` (bulk-import API).

- Fill ALL fields the doc supports: category, uses, industries, tags (M2M, not
  free-text), payload/reach/DOF columns, battery/speed into structured specs,
  family/variant links (Rizon 4→4s→10→10s; K2 Biped / K2 AGV / K3 are explicit).
- Company records: most of these vendors are new → create with website, country
  (company property), description, logo + profile data where a company-profile doc
  provides it.
- Per-company flow: stage → review staged JSON → import → next company.

## Phase 4 — Post-import verification

- Prod `verify_content` per imported robot (server key), then AI-verify + moderation
  via the MCP tools; approve at ≥70.
- Docs traced to an OEM URL should verify normally. File-only robots may score low
  and park in draft (promote gate = required-set + verify ≥70). That parking is
  ACCEPTED behaviour for v1.

**Open questions for Martti**
1. File-only sources: fine to let those robots sit in draft until the OEM publishes a
   web page, or do we extend server-side verify_content to read RobotInformationSource
   attachments (small server change, follow-up)?
2. Confirm: uploading booth-handout brochures to the public CDN as sources is
   acceptable by default (investor material always excluded).
3. Pilot order: propose Kepler (thin/greenfield, EN, clean tables) first, then Flexiv
   (exists in DB — exercises the new-robots-only path), then one CN-only vendor
   (exercises translation path), before opening the queue.
