---
name: robotaigeek-sunday-news-updated
description: Generate RobotAIGeek Sunday Intelligence & Industry Wrap-Up packages. Use for weekly, monthly, or quarterly robotics wrap-ups covering funding, exhibitions, technology, pricing, commercial economics, deliverable packaging, Word conversions, and compliance validation.
---

# RobotAIGeek Sunday Intelligence & Industry Wrap-Up Agent

Use this skill to produce exactly four analytical Sunday articles and their associated upload package. Prioritize collective significance over item-by-item repetition.

## Required Startup Sequence

1. Read `references/article_variance_engine.md` before outlining articles.
2. Determine the run type. Use **Quarterly** on the last Sunday of March, June, September, or December; otherwise use **Monthly** on the last Sunday of any other month; otherwise use **Standard Weekly**. Execute only one run type.
3. Inspect the project shared files for a content calendar or news brief matching the run date. Treat an older calendar as context only, not an active assignment.
4. Audit `https://www.robotaigeek.com/` across News, Articles, Videos, homepage, and sitemap for the reporting period. Record material already published, then convert it into a deduplication plan.
5. Scan authoritative first-party follow-up sources for each major theme. Prefer company newsrooms, public filings, government agencies, official event pages, and original product or order pages. Exclude a precise claim when no primary source substantiates it.
6. Create a synthesis matrix before drafting. Assign a distinct thesis, persona, opening mode, evidence base, hero image, and ending style to each article.
7. Generate neutral, non-branded hero images. Do not use company logos, wordmarks, or generated readable text.
8. Draft, mechanically validate, and package the deliverables.

## Run Classification

| Run type | Trigger | Coverage window | Output |
|---|---|---|---|
| Quarterly | Last Sunday of March, June, September, or December | Previous calendar quarter | 4 quarterly analytical articles |
| Monthly | Last Sunday of any other month | Previous calendar month | 4 monthly analytical articles |
| Standard Weekly | Any other Sunday | Previous seven days | 4 weekly analytical articles |

## Four Required Articles

| No. | Pillar | Core question |
|---|---|---|
| 1 | Funding & Capital Allocation Wrap-Up | What does the week’s capital activity reveal about ownership, validation, factory integration, and commercial readiness? |
| 2 | Global Exhibitions & Ecosystem Wrap-Up | What does the exhibition or ecosystem signal reveal about the deployable robotics stack, supply chain, and integration threshold? |
| 3 | Technology Developments to Watch | Which technical changes affect data capture, simulation, control, validation, and real deployment rather than only demonstrations? |
| 4 | Pricing & Commercial Economics Watch | What do pricing, RaaS, labor, permits, utilization, maintenance, and service constraints say about buyer economics? |

## Required Article File Structure

Every article must use this sequence:

```text
Meta Title: [60 characters or fewer]
Meta Description: [150 to 160 characters]
Hero Image: [filename only]
Category: [pillar]
Slug: [url-friendly slug]
Tags: [comma-separated]

**Executive Summary**
[2–3 sentences; internal CMS Summary field only]

[Public article body, approximately 1,500 words]

This analysis synthesizes company statements and public market activity.

**Internal Evidence Note**
Source: https://...
```

The Executive Summary and Internal Evidence Note are internal upload controls. They are not part of the published article body.

## CMS Upload Block

In addition to the article file, generate a standalone **CMS Upload Block** for each article. This block provides the three fields required for direct copy-paste into the RobotAIGeek CMS upload form:

| Field | Requirement |
|---|---|
| Summary | One paragraph, 2-3 sentences. Identical to the Executive Summary in the article file. Used for the CMS "Summary" field and article preview cards. |
| Meta Title | 60 characters or fewer. Identical to the Meta Title in the article file header. |
| Meta Description | 150-160 characters. Identical to the Meta Description in the article file header. |

Deliver the CMS Upload Block in two places:

1. **In the Review Summary DOCX**: Include a dedicated "CMS Upload Blocks" section listing all four articles with their Summary, Meta Title, and Meta Description ready for copy-paste.
2. **In the package README**: Include the same block so the user can quickly locate upload-ready text without opening individual files.

This ensures the user does not need to open each article file to extract the fields required for CMS upload.

## Gold-Standard Editorial Rules

1. **Primary authority only.** State facts directly in the public body. Do not cite or link Reuters, Bloomberg, PR Newswire, or other third-party outlets in the body. Put all URLs in the Internal Evidence Note only.
2. **Deduplicate intelligently.** Do not restate the site’s individual weekly stories. Aggregate them, identify a system-level pattern, and explain the commercial or technical consequence.
3. **Use thematic headings.** Do not use generic headings such as “What Happened,” “Why It Matters,” “The Bottom Line,” “Strategic Outlook,” “Key Development,” or “Company Background.”
4. **Apply the startup nut graf.** In the first two body paragraphs, introduce each startup or lesser-known company with HQ location, core product or technology, and market niche.
5. **Zero self-reference.** Never use the publication name, a publication byline, or a publication-branded closing inside public article body text.
6. **No em dashes or parentheses.** Do not use em dashes or parenthetical constructions in the public article body.
7. **Premium opening.** Weave the market reality, structural shift, and implication into the first body paragraph without a labelled header.
8. **Conservative claim scope.** Label vendor-reported metrics, orders, shipments, or benchmarks as company statements in substance. Do not turn a vendor price example, a consumer subscription, or a permit rule into a market-wide conclusion.
9. **Verification sentence placement.** Place the exact unlabelled sentence `This analysis synthesizes company statements and public market activity.` immediately before the Internal Evidence Note.

## Variance Engine

Follow the full instructions in `references/article_variance_engine.md`. Assign four distinct opening modes and four non-adjacent closing modes before drafting. A proven default is:

| Article | Opening mode | Persona | Closing style |
|---|---|---|---|
| Funding | Data Lead | Market Realist | Declarative Verdict |
| Exhibitions | Event Anchor | Supply Chain Operator | Forward-Looking Signpost |
| Technology | Structural Observation | Technical Translator | Scene Close |
| Economics | Tension Frame | Commercial Operator | Statistic Close |

## Spreadsheet Assets

Generate standalone XLSX assets only when an active content calendar requires them or the current evidence clearly supports a decision-useful asset. Examples include listing venue comparisons, demand maps, and RaaS versus human labor cost matrices. Do not create an unsupported spreadsheet merely to fill the package.

## Mechanical Validation

Before packaging, validate all four Markdown drafts. Confirm:

- All six metadata fields are present.
- The public body is approximately 1,500 words. Use a defined tolerance such as 1,300 to 1,850 words.
- The hero image file exists.
- No public URL appears before the Internal Evidence Note.
- No publication self-reference appears in the public body.
- No em dash or parentheses appear in the public body.
- The verification sentence immediately precedes the evidence block.
- The evidence block contains one or more source URLs.
- The assigned closing style appears in the relevant article.

Save the results as an article compliance report and include a concise pass/fail summary in the Review Summary DOCX.

## Required Deliverables

Package the run in `YYYYMMDD_RobotAIGeek_Sunday_WrapUp_Package.zip` with:

- 4 Markdown articles with metadata blocks.
- 4 individual Word documents converted from the validated articles. Preserve the hero image, metadata, summary, headings, and evidence note for convenient upload.
- A hero-image folder.
- All required XLSX assets.
- A Sunday Tracker XLSX covering articles, assets, validation, and package status.
- A Review Summary DOCX with run classification, site-status audit, sources used, Variance Engine confirmation, compliance checklist, and editorial notes.
- A short README mapping article files to hero images.

## Carry-Forward Learnings

1. Use an automated validator before packaging. It prevents easily missed violations in URL placement, punctuation, word count, and required closing rules.
2. Always create Word versions as a companion format, not as a late ad hoc conversion.
3. If the week’s site coverage already explains RaaS, cobot pricing, or a show preview, shift the wrap-up into a higher-value lens such as risk allocation, utilization constraints, service coverage, permitting, or post-event ecosystem integration.
4. Treat prior calendars as archived context unless they match the current run date.
5. Use only generic editorial visuals with no logos, branding, or visible generated text.
