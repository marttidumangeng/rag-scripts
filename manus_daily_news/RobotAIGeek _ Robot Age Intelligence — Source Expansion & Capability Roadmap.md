# RobotAIGeek / Robot Age Intelligence — Source Expansion & Capability Roadmap

**Date:** July 30, 2026 | **Prepared by:** Manus AI | **Companion files:** `RAI_FirstHand_Source_Registry_Combined_20260730.xlsx` (master registry, 448 sources), `tier1_firsthand_source_registry_combined_20260730.csv` (skill drop-in), `benchmark_competitors.csv` (raw benchmark data)

---

## Part 1 — What the RobotAIGeek Site Review Found

A full crawl of [robotaigeek.com](https://www.robotaigeek.com/) was performed on July 30, covering the News section (~288 items), Articles (~107 items including the ARPI series and monthly wrap-ups), the Robots database (2,424 robots), and the Companies directory (715 listed companies, 528 fully captured). The review confirms the user's Genki intuition and generalizes it: **the site's own coverage history is the single best predictor of which first-hand sources the desk needs**. Nearly every recent story originated from an entity that was *not* in the Tier 1 source registry — meaning the desk found these stories late, through intermediaries, rather than early, through the primary source itself.

The pattern across the July 2026 news cycle is unambiguous. Stories came from company disclosures (Teradyne earnings, Kawasaki's CORLEO investor briefing, Stabilus–Synapticon partnership, Virtuix's Tesla sale, Ecovacs' Bajie open-sourcing), exchange filings (KOSDAQ-listed KNR Systems, HKEX-listed Giant Star Legend, Horizon Robotics' convertible bond), regulators (the FCC's Chinese-humanoid equipment-authorization ban), regional governments (South Gyeongsang's KRW 21 trillion physical-AI plan, Kumamoto Prefecture's PASTEC chip hub), research institutes (Shanghai Innovation Institute's τ0-VLA release), and funding disclosures (Morphi's Alibaba–Tencent angel round, Delta Intelligence's sixth round). **Genki Robotics** — Andy Rubin's Tokyo humanoid-OS startup, confirmed via its Nikkei interview and now verified at [genki.com](https://genki.com/) — is exactly the class of source the registry was missing: a pre-IPO, category-defining company whose every product and funding announcement is guaranteed front-page material.

The Companies directory itself proved to be an underused strategic asset. It already contains hundreds of organizations that the registry ignored, including entire regional clusters (a 12-company Singapore cluster anchored by government agency HTX and the National Robotics Programme; Canadian humanoid maker Sanctuary AI; Israeli defense-robotics firms; Australian agricultural autonomy), entire vertical clusters (surgical robotics majors Stryker, Medtronic, Zimmer Biomet, J&J MedTech, CMR Surgical, MicroPort MedBot; marine robotics from Saildrone to Kongsberg Maritime; agricultural robotics from Carbon Robotics to SwarmFarm), and the fast-moving Chinese humanoid second wave (Kepler, Booster, MagicLab, NOETIX, Galaxea, PsiBot, Spirit AI). One honest caveat: roughly a third of the directory consists of small commodity component suppliers (casters, cables, gearboxes) with no news output; these were deliberately excluded from the registry to keep the daily scan efficient.

## Part 2 — The Combined Registry: 448 Verified First-Hand Sources

The 124 new sources extracted from the site review were each individually verified (working newsroom URL, RSS/API availability, listing status, update frequency) and merged with the 324-source registry delivered on July 28. All 124 verified successfully; only one (South Gyeongsang Provincial Government) carries a JS-rendering caveat. There were zero duplicates against the existing registry.

| Region | v1 (Jul 28) | New from site review | Combined total | P0 daily-scan |
|---|---|---|---|---|
| United States | 55 | 34 | 89 | 21 |
| China | 50 | 32 | 82 | 26 |
| Europe | 48 | 22 | 70 | 13 |
| Japan | 39 | 10 | 49 | 11 |
| Taiwan | 40 | 4 | 44 | 8 |
| South Korea | 40 | 3 | 43 | 12 |
| International | 21 | 17 | 38 | 6 |
| Hong Kong | 31 | 2 | 33 | 5 |
| **Total** | **324** | **124** | **448** | **102** |

The additions rebalance the registry in four ways. First, they add the **coverage-proven layer**: every entity that generated a RobotAIGeek story in July 2026 is now a registered source with a monitored newsroom (Genki, Virtuix, Synapticon, Stabilus, Morphi, Delta Intelligence, Chaowei Dynamics, KNR Systems, Mitsui Fudosan, IFA Berlin, Ecovacs, Giant Star Legend, Shanghai Innovation Institute, FCC, Kumamoto Prefecture, South Gyeongsang Province). Second, they close the **vertical gaps** the v1 registry acknowledged but did not fill: surgical/medical robotics (7 sources), defense and security robotics (8), marine and underwater (7), agricultural (3), logistics/AMR (12), and consumer robotics (5). Third, they open **new geographies** under the International sheet: Singapore/SEA (12 sources), Canada (3), Israel (1), Australia (2) — regions where RobotAIGeek's own directory already lists companies but the news desk had zero collection capability. Fourth, they deepen the **China humanoid second wave**, adding 15+ startups that aggregators like 36Kr will only cover after funding events, whereas direct WeChat-account and website monitoring catches product launches days earlier.

Every row carries the operational fields the scanning workflow needs: news URL, RSS/API availability, collection route (page scrape, RSS, WeChat, IR calendar, exchange filings), watch keywords in the source language, priority tier, ticker where listed, and an `origin` column distinguishing v1 sources from site-review additions so the two batches can be audited separately.

## Part 3 — Honest Benchmark: RAI vs. the Top 20

Twenty competitors were researched in parallel across four strategic groups. The full dataset is in `benchmark_competitors.csv`; the table below compresses the findings into what matters for strategy.

| Group | Players | Their moat | Their exploitable weakness |
|---|---|---|---|
| Global newswires & terminals | Bloomberg (~$13B rev, 2,700+ journalists, $30K/seat), Reuters/LSEG (2,600 journalists, ~$22K/seat), Dow Jones ($2.33B rev, Factiva 33K sources), S&P Global ($14.2B rev, Capital IQ Pro), CNN (37 bureaus) | Entrenched daily-workflow terminals fed by proprietary data pipelines and giant newsrooms | Robotics is a rounding error for all of them: broad macro/large-cap framing, no robot product data, no private-robotics depth, no pricing indices |
| Private-market data platforms | PitchBook (~$450-500M ARR, 1,100 researchers, $12-70K/yr), Crunchbase (600K contributors), CB Insights (~$146M rev, Mosaic Score) | Curated deal archives, contributor networks, predictive scores | Generalist taxonomies; robotics data verified by humans and therefore lagging; no technical product layer |
| Market research firms | Interact Analysis (boutique, interview-driven), Mordor (~18K reports, Synapse $999/mo), ABI (~$68M rev, Ask ABI), Grand View/MarketsandMarkets (volume publishers), IoT Analytics/STIQ (freemium AGV/AMR reports) | Primary-interview methodology (Interact), scale of report production, AI query layers (Ask ABI, Synapse) | Periodic static PDFs, no daily cadence, top-down forecasts often shallow in robotics specifics; Mordor's depth is openly questioned by practitioners |
| Robotics-native media & data | The Robot Report (events moat: Robotics Summit, RoboBusiness), IEEE Spectrum (450K circulation, Robots Guide ~240 robots), IFR (World Robotics, direct manufacturer pipeline, €2.5K reports, 7 staff), robolist.ai (3,700 robots, Robo Index), Nikkei Robotics (¥49,800/yr newsletter), 36Kr/QbitAI (36.6M/3.5M followers) | Brand authority, event access, IFR's exclusive manufacturer statistics pipeline, robolist's structured catalog | The Robot Report is qualitative and event-driven with no data products; IEEE's guide covers only ~240 robots; IFR is annual, hardware-only, humanoid-conservative; robolist has specs but no newsroom, no funding layer, no China depth; 36Kr/QbitAI are the aggregators RAI is escaping |

The honest structural read: **no competitor combines a daily first-hand newsroom, a structured robot/company database, and pricing/funding indices in one platform.** Bloomberg-class players have the newsroom-plus-terminal model but ignore robotics; robotics-native players have domain focus but lack either the data layer (Robot Report, Nikkei Robotics) or the news layer (robolist, IFR). RAI's existing assets — 288 originated news items, 2,424-robot database, 715-company directory, the ARPI price architecture, and now a 448-source first-hand registry — already constitute the raw material of exactly that missing combination. What is missing is the machinery that turns sources into structured, queryable, sellable intelligence.

Equally honest is the gap assessment. RAI today has no API product, no subscription revenue engine, no analyst-verified private-company financials, no proprietary survey program, no events platform, and a robot database that is large (2,424 vs. robolist's 3,700 and IEEE's 240) but not yet monetized as structured data. Scale asymmetry is extreme — Bloomberg spends more on its newsroom in a week than RAI's likely annual budget — which is precisely why the strategy must be *depth in a vertical the giants ignore*, the same wedge PitchBook used against Bloomberg in private markets and IFR used with its manufacturer statistics monopoly.

## Part 4 — What RAI Needs to Access and Keep Track Of

The combined registry defines *who* to watch. The following access layer defines *what infrastructure and subscriptions* are needed to watch them at machine speed. Items are ordered by return on effort.

| # | Access / tracking need | What it unlocks | Cost / effort |
|---|---|---|---|
| 1 | **Exchange disclosure APIs**: SEC EDGAR full-text search API, Korea DART OpenAPI, HKEXnews scraper, CNINFO (SSE/SZSE) polling, Japan TDnet/EDINET, Taiwan MOPS | Earnings, IPO filings, convertible bonds, M&A — the layer that generated the Teradyne, KNR, Horizon, and AgiBot-IPO stories. All free; EDGAR and DART have documented APIs | Free; 2–3 weeks engineering |
| 2 | **RSS/scrape pipeline for all 448 sources**: scheduler polling P0 sources 2–4x daily, P1 daily, P2 weekly, with LLM triage scoring each item for newsworthiness against the Article Variance Engine | Converts the registry from a list into a live wire service; catches announcements within hours instead of after 36Kr covers them | Free; the core build, 4–6 weeks |
| 3 | **WeChat public-account monitoring** for ~40 Chinese company accounts (Morphi, Galaxea, PsiBot, Booster, MagicLab, etc. publish there first) | First-hand China startup coverage without aggregator dependence — the exact 36Kr escape the user demanded | Low cost via WeChat RSS bridges; ongoing maintenance |
| 4 | **Patent feeds**: CNIPA, USPTO Patent Public Search API, EPO OPS, WIPO PatentScope, J-PlatPat, KIPRIS — weekly robotics-classification (B25J) sweeps | Forward-looking R&D signals 18 months ahead of product launches; nobody in robotics media does this systematically | Free APIs; 2 weeks |
| 5 | **Procurement and tender feeds**: SAM.gov API, EU TED, CCGP China, plus FCC equipment-authorization database and FDA 510(k) | Deployment and regulatory stories (the FCC ban story class); government robot purchases are original, verifiable, and exclusive | Free; 2 weeks |
| 6 | **Funding-event pipeline**: Crunchbase API (from $49/mo tier) or ITjuzi for China, cross-verified against company announcements and exchange filings | Feeds the funding tracker and monthly wrap-ups with same-day rounds | ~$1–5K/yr |
| 7 | **IFR World Robotics data package** (€2,500/yr) plus national association statistics (JARA monthly, KAR, CRIA quarterly, A3, VDMA) | The authoritative baseline every market-size claim must reconcile against; cheap credibility | €2.5K/yr |
| 8 | **Exhibition press-office accreditation**: WRC, WAIC, CES, IFA, Hannover Messe, automatica, iREX, IROS/ICRA/CoRL | Press badges give embargoed releases and exclusive access — the cheapest form of the Robot Report's events moat | Free; application effort |
| 9 | **Conference preprint monitoring**: arXiv cs.RO daily, CoRL/RSS/ICRA acceptance lists, Hugging Face robotics model releases, GitHub trending (VLA models, τ0-class releases) | Catches the τ0-VLA story class at release time; adoption metrics (stars, downloads) become original evidence | Free; 1 week |
| 10 | **Human source network** (phase 2): systematic exec-interview program per Interact Analysis's model, expert commentary bench from the site's Experts section, reader-tip channel | The layer no scraper replicates; turns RAI from monitor into interviewer — required for Bloomberg-class scoops | Editorial time; start with 2 interviews/week |

## Part 5 — What to Build: The Capability Roadmap to No. 1

The roadmap translates the benchmark takeaways into four build horizons. The consistent principle, drawn from every competitor's moat analysis: **news attracts the audience, structured data retains it, and indices/APIs monetize it.**

**Horizon 1 (0–3 months) — Wire-service machinery.** Build the 448-source polling pipeline with LLM triage (items 1–5 above), formalize the disclosure-portal watchers, and stand up the WeChat bridge. Target output: 80% of published news items originating from a primary source within 12 hours of disclosure, with the source URL cited — the operational definition of "being like Reuters" at desk scale. Simultaneously, adopt STIQ's freemium distribution trick: publish one free, data-rich quarterly PDF (e.g., "State of Humanoid Pricing") to build the top-of-funnel audience and email list.

**Horizon 2 (3–9 months) — Data products on existing assets.** The 2,424-robot database becomes the **Robot Product Master File**: normalized specs, launch dates, prices, and availability, with a robolist-style objective index (call it the *RAI Robot Index*) whose methodology is published and never sold. The ARPI price series becomes a **monthly published index** with a fixed release calendar — the Platts/OPIS playbook: a benchmark that gets cited becomes infrastructure. The company directory becomes a **funding and financials tracker** cross-verified against the exchange-filing pipeline, with a CB Insights-style commercial-maturity score per company. These three structured products are what none of the 20 competitors possesses in combination.

**Horizon 3 (9–18 months) — Monetization rails.** Launch a paid tier modeled on Nikkei Robotics' proven price point (~$300–500/yr individual; $5–15K enterprise): daily intelligence briefing, full database access, index back-data, and quarterly deep-dive reports. Add the **machine-readable layer** per the Dow Jones takeaway: a REST API and licensed data feed of news, robot specs, and indices, positioned for quant funds, corporate strategy teams, and GenAI training licensees. Add an ABI-style **"Ask RAI"** natural-language query interface trained exclusively on RAI's own corpus — a genuine differentiator at low cost given the structured foundation.

**Horizon 4 (18–36 months) — Authority moats.** An annual **RAI 100** ranking (CB Insights' AI 100 playbook) and an annual *State of AI Robotics* flagship report; a small owned event or summit co-located with WRC or CES (the Robot Report's moat, rented cheaply at first); a systematic executive-interview program producing weekly exclusive quotes; and expansion of the analyst bench for the enterprise custom-research tier where Interact Analysis demonstrates boutique firms can win against giants.

**KPIs that define "No. 1":** share of stories originated from primary sources (target >85%), median time from disclosure to publication (<12h), robots in the master file (>5,000, surpassing robolist), companies tracked with verified funding data (>1,500), ARPI citations in third-party media (the benchmark-status metric), paid subscribers, and API customers. When ARPI is quoted the way IFR's installation counts are quoted today, the market-intelligence position is won.

---

*All 448 sources in the companion Excel were individually URL-verified during July 28–30, 2026. The CSV file is formatted as a drop-in replacement for the skill's `tier1_source_registry.csv`. Benchmark figures marked "est." are estimates from public sources; full per-competitor detail including business models, sourcing methods, and scale metrics is in `benchmark_competitors.csv`.*
