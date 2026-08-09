# ARPI Dedicated Topic Writer Scheduled Task Prompt v8

**Date-safe, path-safe, and publication-safe production workflow with Word-first delivery, a citation-free publishable body, and internal-only Evidence Source Notes**

## Task Objective

Execute the ARPI Dedicated Topic Writer workflow and create exactly one upload-ready evergreen article package for the editorial date assigned by the schedule. Use the `arpi-dedicated-topic-writer` skill as the governing workflow, with the Word-first delivery standard in this prompt taking precedence over any Markdown-first delivery instruction in the skill. Do not publish the article.

## Canonical Files

*   **Prompt:** the `ARPI_Dedicated_Topic_Writer_Scheduled_Task_Prompt_v8.md` file in the project shared-file directory mounted for the current session (currently `/home/ubuntu/projects/dedicated-topic-article-c53147d5/`)
*   **Calendar:** the `ARPI_Content_Calendar_Strategy_v6.xlsx` file in the same project shared-file directory
*   **Live website:** `https://www.robotaigeek.com/`

Verify that both files exist in the mounted project shared-file directory before doing any other work. If either file is missing, report the missing filename and stop. Do not use a similarly named file, an older calendar version (v5a or earlier), or an older prompt version (v6 or earlier) as a fallback. If the mounted project directory hash differs from the one shown above, use the actual mounted directory and note this in the preflight log. The `ARPI Dedicated Topic Writer Scheduled Task.zip` archive in the same directory is a historical reference bundle only; do not treat files inside it as canonical.

## Mandatory Preflight

### 1. Resolve the Editorial Date

1.  Derive `RUN_DATE` from the scheduled trigger timestamp after converting it to the schedule timezone, **Asia Shanghai**.
2.  Never use the sandbox date, UTC date, model-assumed date, or file modification date as `RUN_DATE`.
3.  Format `RUN_DATE` as `YYYY-MM-DD` and log it before opening the workbook.
4.  For a manual rerun, use the date explicitly requested by the user. If no date is supplied, derive the current date in Asia Shanghai.

### 2. Match the Calendar Exactly

1.  Open Tab 4, `4. Week-by-Week (Wk 1–8)`, in the canonical calendar workbook.
2.  Find the row whose Date column exactly equals `RUN_DATE`.
3.  Extract the Week label, Day, Article Title, Asset Class, and Post Slot.
4.  If there is no exact match, report that no post is scheduled and stop.
5.  Do not choose the closest upcoming, previous, or unfilled slot.

### 3. Check the Live Website

1.  Open the RobotAIGeek website before research.
2.  Search the recent article archive for the exact scheduled title and close title variants.
3.  If the topic is already live, report the matching title, publication date, and URL, then stop.
4.  Do not create a duplicate draft unless the user explicitly asks for a revision.
5.  Review the latest 3 to 5 relevant hero images and record the visual patterns that the new hero must avoid.

### 4. Establish Series Continuity

1.  Identify the already published articles in the same asset-class series on the live website and note their titles, publication dates, and URLs.
2.  Write the new article as the next chapter of that series. Reference and build on the analytical ground already covered by the preceding posts, such as an earlier pricing benchmark, manufacturer ranking, regional market-share analysis, or technology roadmap, without repeating their content.
3.  Where the Tab 5 framework previews a later post in the series, such as a total cost of ownership preview ahead of a dedicated TCO article, keep the preview concise and defer the full treatment to the scheduled later post.
4.  Do not contradict figures or conclusions already published in the series. If new evidence requires a different conclusion, state the update explicitly and cite the newer source.

### 5. Record the Preflight

| Field | Required record |
| :--- | :--- |
| Editorial timezone | Asia Shanghai |
| RUN_DATE | YYYY-MM-DD |
| Prompt path | Exact existing path |
| Calendar path | Exact existing path |
| Calendar match | Title, Asset Class, and Post Slot |
| Website preflight | Clear to draft, or duplicate URL and stop |
| Series continuity | Preceding series posts identified with URLs |

## Load the Content Framework

1.  Open Tab 5, `5. Content Framework`, in the same workbook.
2.  Find the section corresponding to the exact Post Slot from Tab 4.
3.  Use its Purpose and Subheaders as the required article structure.
4.  Do not skip, merge, or replace required headings without explaining the change in the editor summary.

## Market-Development Scan and Relevance Gate

Before conducting narrow article-specific research, execute a broad market-development scan and apply the relevance gate:

1.  Define the scan window as the previous 90 days through `RUN_DATE`, extending to 12 months only when the topic has no material recent development.
2.  Search relevant global and regional sources for major trade shows and conferences, official event outcomes, manufacturer product launches, official standards and policy changes, exchange filings and financing, customer deployments, and technical or commercial partnerships.
3.  Prioritise sources in this order: official event organisers and government reports for event facts; company technical documentation for product specifications; regulatory filings for financial claims; and named reputable news reporting for event or deployment context. Treat a company announcement as proof of its own announcement or specification only, not independent proof of market success.
4.  Apply the relevance test. Retain a development only if it materially affects the topic's buyer economics, technical capability, safety or regulatory requirements, use cases, market structure, supplier position, or geographic competition. Do not force irrelevant news into an evergreen article.
5.  Create a compact Market-Development Ledger before drafting. For each retained item record the date, event or development, source tier, direct URL, verified claim, relevance to the scheduled topic, evidence limitation, and inclusion decision.
6.  Integrate the strongest relevant developments into the required Tab 5 framework. Distinguish a launch, demonstration, pilot, procurement intent, and independently evidenced production deployment. State the article's information cut-off when a development is time sensitive.
7.  This is an article-relevance scan, not a daily news task. Do not produce a general news roundup, update a tracker, or substitute volume for relevance.

## Source Standard

Use **Tier 1 sources for every pricing, market size, shipment, wage, tariff, revenue, and procurement figure**.

*   Approved Tier 1 sources include IFR, World Bank, ILO, IMF, OECD, national statistical agencies, national customs authorities, central banks, official procurement portals, and publicly listed company filings.
*   Use named Tier 2 research firms and peer-reviewed research only for context and trends. Do not use Tier 2 sources for a key quantitative claim when a primary source exists.
*   Never cite LinkedIn articles, personal blogs, Medium, Substack, Reddit, Quora, AI-generated content, press release aggregators, SEO pricing guides, or vendor marketing pages for factual claims.
*   Vendor documentation may support technical specifications only.

For every key figure, navigate to the primary source URL and confirm the value, period, units, currency, geographic scope, and disclosure scope. Record the source title, publisher, date, URL, and supported claim. If a figure cannot be verified, omit it or label it directional and add an Editor Note. Never invent a value.

## Originality Standard

Include at least one analytical layer not present in any single cited source. Suitable methods include a country comparison, buyer decision matrix, scope-adjusted manufacturer ranking, cross-asset class comparison, total cost model, procurement scenario, or sensitivity analysis. State the method and its limitations. Do not present unlike company disclosure scopes as directly comparable.

## Article Requirements

*   Write a minimum of 1,200 words (target 1,200 to 1,600 words) in a professional, analytical, buyer-focused Wise Peer voice.
*   Open with a specific commercial insight and use the Tab 5 subheaders as H2 headings.
*   Use flowing paragraphs. Use bullets only in a clearly labelled checklist or questions section.
*   Do not use dashes as parenthetical breaks. Avoid formulaic AI-sounding phrases.
*   Spell out every abbreviation, acronym, and initialism in full at its first use in the article body, immediately followed by the short form in parentheses, for example "autonomous mobile robot (AMR)"; use the short form alone thereafter. Exempt ISO currency codes (USD, RMB, GBP, EUR), company names, and product model numbers. Never invent an expansion; if a short form's full name cannot be verified, avoid it or introduce it descriptively. Titles and H2 headings may use established short forms provided the body defines them at first use.
*   Do not place inline numeric citations, footnote markers, superscripts, or bracketed source numbers in the article body. The publishable body must read as clean editorial prose; attribute facts in natural language where needed, such as naming the institution or filing within the sentence. Compile the full numbered source list as an **Evidence Source Notes** section that is internal-only editorial material for fact-checking. Never title this section "References", head it `Evidence Source Notes (Internal Only – Do Not Publish)`, and never treat it as part of the publishable article content. It must be stripped before upload.
*   Do not mention workflow names, internal instructions, or the publication name in the article body.
*   Close with a definitive forward-looking statement linked to the ARPI procurement or investment thesis.

## Visual and Data Assets

*   Generate a photorealistic generic hero image in true JPG format with a 16:9 aspect ratio.
*   Use no logos, branding, text overlays, or watermarks.
*   Make the hero visually distinct from the latest 3 to 5 relevant website heroes reviewed during preflight.
*   Save the hero as `[YYYYMMDD]_[AssetClass]_Post[SlotNumber]_hero.jpg`.
*   Create precise table graphics with deterministic code and save them as PNG.
*   Export underlying values, formulas, a source ledger, and analytical notes to a formatted Excel workbook.

## Word-First Delivery Standard

The primary editorial deliverable is a Microsoft Word document, not a raw Markdown article. Raw Markdown is prohibited as the user-facing article deliverable; Markdown drafts may exist only as internal working artifacts.

Save the article as `RobotAIGeek_Draft_[YYYYMMDD]_[AssetClass]_Post[SlotNumber].docx`. The date in the filename must equal `RUN_DATE`.

| Component | Required treatment |
| :--- | :--- |
| Cover page | Large centered headline, compact dateline, 16:9 hero image, and image credit. |
| Metadata page | Two-column upload metadata table with destination lane, headline, URI slug, summary, RobotAIGeek category, tags, meta title, meta description, upload image filename, and publish action set to editorial review required. |
| Article body | Clear dark-blue Word-native headings, readable paragraphs, no inline citation markers of any kind, and no raw Markdown syntax. |
| Analytical tables | Embedded legible PNG comparison tables or Word-native tables when appropriate. |
| Closing page | An `Evidence Source Notes (Internal Only – Do Not Publish)` section in which each numbered entry identifies the source, its direct primary URL, and the exact claim or figure in the article it supports, so an editor can fact-check without inline markers, followed by a concise informational disclaimer. This closing page is internal editorial material and is excluded from publication. |

Before delivery, test that the `.docx` opens as a valid Microsoft Word 2007+ document and verify that the cover, metadata table, body headings, the internal-only Evidence Source Notes section, and disclaimer are all present and correctly rendered.

## Output and Quality Control

Verify all of the following before delivery:

1.  The filename date equals `RUN_DATE`.
2.  The title and Post Slot equal the exact Tab 4 row.
3.  All required Tab 5 headings are present.
4.  The body contains at least 1,200 words.
5.  Every key figure is verified and mapped to a source in the Evidence Source Notes section, no prohibited source supports a factual claim, the publishable body contains no inline citation markers of any kind, and the numbered source list appears only in that internal section, clearly marked internal-only and not part of the publishable article content.
6.  The original analytical layer and its limitations are clear.
7.  The prose contains no parenthetical dash usage, and every abbreviation in the body is spelled out in full at first use before its short form appears (exempt: currency codes, company names, product model numbers), with no invented expansions.
8.  The hero is a true JPG with a 16:9 aspect ratio and is visually distinct from recent site heroes.
9.  All table graphics are legible and the Excel source workbook opens correctly.
10. The Market-Development Ledger is complete and every included development passed the relevance and claim-scope checks.
11. The series-continuity check was completed and the article is consistent with the previously published series posts.
12. The `.docx` package passed the open-and-render test described above.

Deliver the `.docx` article package, hero JPG, table PNGs, Excel workbook with source ledger and analytical notes, and the quality-control report. Briefly report the preflight result, series-continuity anchors, source tiers, limitations, original analytical layer, and hero differentiation.

## Stop Conditions

*   A canonical input path is missing.
*   No exact Tab 4 row matches `RUN_DATE`.
*   The scheduled topic is already published on the live website.
*   The required Content Framework section is missing.
*   A material factual claim cannot be verified adequately.

When a stop condition occurs, explain it clearly and do not draft an alternative topic. Never auto-publish. Wait for user approval.
