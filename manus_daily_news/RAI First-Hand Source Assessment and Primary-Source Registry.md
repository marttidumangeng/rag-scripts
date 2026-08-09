# RAI First-Hand Source Assessment and Primary-Source Registry

**Prepared:** July 28, 2026 | **Author:** Manus AI | **Scope:** Honest audit of the current Tier 1 source inventory (20260728_RAI_Source_List_Review.xlsx and the Korea/US/Europe/Taiwan/HK/Japan review document) plus a newly researched, URL-verified registry of first-hand sources for China, Japan, South Korea, the United States, Europe, Taiwan, Hong Kong, and international governing bodies.

---

## 1. The Honest Assessment

The direct answer first: **the current source system cannot support a Bloomberg-style origination desk.** It is a competent *media-monitoring* system, not a *news-origination* system. Roughly two-thirds of the China registry consists of secondary aggregators, the non-China lists lead with wire services and trade media, and the highest-value source class in professional journalism — disclosure portals, ministries, statistics offices, and company IR pages — is either missing or used ad hoc. The good news is that the July 28 review document already diagnosed part of this correctly (it flagged DART, EDGAR, and HKEXnews as "where the Nvidia–Naver and AgiBot stories actually originated"), so the direction below is an extension of your own findings, executed to the depth the ambition requires.

### 1.1 What the current inventory actually is

| Inventory | Sources | Honest characterization |
| --- | --- | --- |
| tier1_source_registry.csv (China) | 30 | ~19 of 30 are secondary media/aggregators (36Kr, nine OFweek sections, QbitAI, Jiqizhixin, GGII, Leader Robot, IT Juzi). Only MIIT, NDRC, CNIPA, CNINFO, Tianyancha qualify as primary. The CSV itself is currently **missing from project shared files and the local skill folder** — it exists only as prose references. |
| SKILL.md prose lists (Japan/Korea) | ~12 | Media-led (Nikkei, Japan Times, Korea Herald, Korea Times) with a handful of company newsrooms. No ministry, disclosure, patent, or statistics layer. |
| June 2026 XLSX directory | 74 | US trade-media heavy; APAC thin (7 rows). Strong on research media, weak on government and filings. |
| July 28 review (xlsx + docx) | +38 proposed | Correct instinct, insufficient depth: post-addition totals are Japan 16, Korea 18, US 14, Europe 18, Taiwan 8, HK 6 — all below the 30 first-hand bar, and still counting wires and media toward the totals. |

### 1.2 The seven structural problems

**Problem 1 — The China desk is an aggregator client, not an originator.** When RobotAIGeek's lead China story traces to 36Kr or OFweek, the desk is publishing derivative content on a 4–24 hour delay, exposed to their framing errors and their editorial selection. Every one of those aggregators is itself reading MIIT notices, CNINFO filings, company WeChat accounts, and CCGP procurement awards. The registry should read what they read.

**Problem 2 — Zero direct Chinese company sources.** The current registry contains not a single company newsroom for the market it covers most. Unitree, UBTECH (HK-listed, with an IR obligation to disclose), AgiBot, Fourier, Galbot, EngineAI, Estun, Siasun, Inovance, DJI, Pudu, Keenon — all absent. This is the single largest gap between the current system and a Reuters-grade desk.

**Problem 3 — The disclosure layer is informal everywhere.** DART (Korea), EDGAR (US), HKEXnews (HK), TDnet/EDINET (Japan), MOPS (Taiwan), and CNINFO/SSE/SZSE (China) are the venues where funding, M&A, capacity expansion, and IPO stories legally must appear first. Three of the desk's own best recent stories (Nvidia–Naver placement, Hyundai 30k-robot plan, AgiBot IPO pipeline) originated in filings. Yet no disclosure portal is a formal P0 source today.

**Problem 4 — Taiwan and Hong Kong are single-source regions**, and the single source in each case (DigiTimes, SCMP) is itself secondary. For a publication covering the robotics supply chain and China robotics IPOs, this is the equivalent of covering Wall Street without EDGAR.

**Problem 5 — No statistics, procurement, or patent layer.** Machinery-order statistics (JARA quarterly, METI, A3, VDMA, KOSIS, MOEA statistics), procurement portals (ccgp.gov.cn, SAM.gov, TED, KONEPS), and patent offices (J-PlatPat, KIPRIS, USPTO, EPO, WIPO) generate scheduled, exclusive, data-rich stories that top agencies convert into recurring franchises. The desk currently has only CNIPA.

**Problem 6 — No preprint/conference layer as a formal source.** Technical breakthroughs surface on arXiv cs.RO and at ICRA/IROS/CoRL/RSS weeks before trade media coverage. IEEE Spectrum writes from these; the desk should too.

**Problem 7 — Registry fragility.** Three overlapping inventories with no canonical file, and the canonical CSV absent from shared storage. The July 13 lesson (SKILL.md not persisting) already demonstrated the failure mode.

### 1.3 What "being like Bloomberg/Reuters" operationally means

Top agencies do not out-write competitors; they **out-source** them. Their advantage comes from four repeatable practices, all reflected in the new registry: (1) filings-first coverage — every listed-company story starts at the exchange portal, not at a media report about it; (2) calendar journalism — statistics releases, policy consultation deadlines, conference programs, and earnings dates are known in advance and staffed in advance; (3) direct-to-source relationships — company newsrooms, ministry press offices, and lab news pages are polled directly, so the desk sees the release at minute zero; and (4) wires as confirmation, never as origin — Yonhap, Kyodo, Focus Taiwan, and Xinhua are used to corroborate and to catch what direct polling missed, and are never the citation of record when the primary document is available.

---

## 2. The New First-Hand Registry

Every source below was checked against a live URL during this build (HTTP-verified or content-extracted on July 28, 2026), with dead links repaired across four correction passes. The registry counts **only originating sources** toward the minimums; wire services appear as clearly-labeled verification-only rows and are excluded from the totals.

### 2.1 Registry summary

| Region | First-hand sources | Verification wires | P0 daily-scan sources | Where news breaks first |
| --- | --- | --- | --- | --- |
| China | 47 | 3 | 18 | MIIT press releases; CNINFO/SSE/SZSE filings; Unitree/UBTECH/AgiBot newsrooms |
| Japan | 36 | 3 | 8 | TDnet timely disclosure; EDINET; METI press releases |
| South Korea | 40 | 0 | 10 | DART filings; MOTIE press releases; KAIST news |
| United States | 55 | 0 | 12 | SEC EDGAR full-text search; FDA 510(k) database; arXiv cs.RO |
| Europe | 48 | 0 | 9 | EC digital-strategy news; Fraunhofer/DLR releases; ABB/KUKA newsrooms |
| Taiwan | 40 | 0 | 6 | TWSE MOPS filings; NSTC announcements; ITRI news |
| Hong Kong | 31 | 0 | 6 | HKEXnews filings; ITC press releases; HKSTP news |
| International bodies | 20 | 1 | 4 | IFR releases; arXiv cs.RO; ISO/TC 299 standards tracker |
| **Total** | **317** | **7** | **73** | |

Every region meets or exceeds the 30-source minimum, and each is balanced across the source classes a professional desk requires: government/regulators, disclosure portals, patents, procurement, statistics, associations, standards bodies, companies, research institutes/universities, and exhibitions.

### 2.2 China (47 first-hand) — the priority rebuild

The China sheet replaces the aggregator-led registry with five pillars: **central government** (MIIT, NDRC, MOST, CNIPA, SAMR, State Council policy database), **municipal government** (Beijing, Shanghai, Shenzhen — the three humanoid-policy engines), **disclosure and procurement** (CNINFO, SSE, SZSE, BSE, CCGP government procurement), **eighteen direct company newsrooms** (Unitree, UBTECH IR, AgiBot, Fourier, Galbot, EngineAI, Estun, Siasun, Inovance, Leju, DJI, Pudu, Keenon, Orbbec, RobotEra, Astribot, LimX, Deep Robotics), and **research/ecosystem** (CAS Institute of Automation, BAAI, Tsinghua, Zhejiang, SJTU, HIT, Peking, the Beijing Humanoid Robot Innovation Center/X-Humanoid, the National-Local Joint Humanoid Robot Innovation Center/OpenLoong, CRIA, CAA, CMRA, WRC, WAIC, CIIF). 36Kr, Jiqizhixin, and QbitAI remain in the sheet but are explicitly demoted to verification-only wire rows.

Practical caveats the desk must plan for: Chinese primary sources almost never offer RSS, so monitoring is page-scrape or API (CNINFO has a usable API); several .cn government sites are slow or intermittently unreachable from overseas IPs and may need retry logic or a China-region relay; and company channels are frequently WeChat-first, meaning the official WeChat account is the true newsroom for firms like the OpenLoong center.

### 2.3 Japan (36 first-hand)

Anchored by the disclosure pair every Japanese listed-company story flows through — **TDnet** (timely disclosure, same-minute) and **EDINET** (securities filings) — plus METI, NEDO, MIC, the Cabinet Office Moonshot program, e-Stat machinery statistics, and J-PlatPat patents. The corporate layer covers twenty newsrooms/IR pages spanning the industrial-arm incumbents (FANUC, Yaskawa, Kawasaki, Mitsubishi Electric, Denso Wave, Epson, Omron, Nachi-Fujikoshi), the research-led entrants (Toyota Research Institute, Honda, Sony AI, Preferred Networks, Telexistence, Mujin, GITAI, Cyberdyne, Kawada), and the critical components oligopoly (THK, Harmonic Drive Systems, Nabtesco) whose order books are a leading indicator for global robot production. JARA, JEMA, and the Robot Revolution Initiative provide the statistics and association layer; AIST, RIKEN, and university labs (JSK Tokyo, Waseda, Osaka) provide research; iREX and Japan Robot Week provide the event calendar. Kyodo remains a wire for confirmation only, with the known weekend-recap trap noted.

### 2.4 South Korea (40 first-hand)

Korea is the region where the filings-first model has already proven itself for this desk (the Nvidia–Naver story). The registry formalizes **DART** (with its free OpenAPI — the single highest-leverage integration available to the desk) and **KIND/KRX** alongside MOTIE, MSIT, KIRIA, KIAT, and KOSIS statistics. The company layer covers twenty names including Hyundai Motor Group/Boston Dynamics, Rainbow Robotics, Doosan Robotics, HD Hyundai Robotics, Hanwha Robotics, Samsung, LG (both newsroom and LG AI Research), Naver Labs, Neuromeka, Robotis, Wonik Robotics (Allegro Hand), Bear Robotics, Angel Robotics, and WIRobotics. Research coverage spans KAIST, KIST, ETRI, KIMM, KITECH, DGIST, POSTECH, SNU, UNIST, and KIRO. KIPRIS covers patents; RobotWorld covers the event calendar.

### 2.5 United States (55 first-hand)

The largest sheet, reflecting the depth of the ecosystem. The government layer is the standout upgrade: **SEC EDGAR full-text search API** (S-1/S-4/8-K robotics filings, the Agility–Churchill SPAC watch), the **FDA 510(k) database** (surgical/medical robot clearances — a systematically underexploited exclusive-story generator), NIST, DARPA, NSF award announcements, ARPA-E, NASA, DIU, USPTO, SAM.gov procurement, Census M3 machinery data, and BIS export controls. Twenty-five company newsrooms/IR pages cover the humanoid cohort (Figure, Boston Dynamics, Agility, Apptronik, Physical Intelligence, Skild, 1X US ops, Tesla IR), platform giants (Nvidia, Google DeepMind, Amazon Science, OpenAI, Meta FAIR, Microsoft Research), and listed pure-plays whose filings move the sector (Intuitive Surgical, Symbotic, Serve Robotics, Teradyne/Universal Robots). Research spans CMU RI, MIT CSAIL, Stanford, Berkeley BAIR, Georgia Tech, UMich, USC, UT Austin, Caltech/JPL, TRI, and AI2, plus the preprint/conference layer (arXiv cs.RO, CoRL, RSS). A3, ARM Institute, MassRobotics, Silicon Valley Robotics, and AUVSI complete the association layer.

### 2.6 Europe (48 first-hand)

Built around three engines: **EU institutions** (EC digital-strategy/AI Office news, CORDIS project results, TED procurement, Eurostat, EPO patents, ADRA, euRobotics), **national research powerhouses** (Fraunhofer IPA, DLR Robotics and Mechatronics — Europe's most under-monitored high-yield lab — DFKI, ETH RSL, EPFL, TUM MIRMI, Oxford ORI, Imperial, Edinburgh, IIT Genoa, LAAS-CNRS, INRIA, TU Delft, KU Leuven, Odense cluster), and **fourteen company newsrooms** (ABB, KUKA, Universal Robots, MiR, NEURA, 1X, PAL, Agile Robots, Wandelbots, Exotec, Ocado, AutoStore IR, Comau, ANYbotics). National agencies (BMWK/Plattform Industrie 4.0, UK DSIT/AISI/EPSRC, Bpifrance, Vinnova, Innovation Norway), VDMA and Make UK statistics, and the automatica/Hannover Messe/ERF event calendar complete the sheet.

### 2.7 Taiwan (40 first-hand) — from one source to forty

The fragile single-source region becomes a full desk: government (MOEA IDA — with RSS — NSTC, Hsinchu/Southern/Central science parks, MODA, Executive Yuan, TIPO patents), **MOPS/TWSE disclosure** (where Foxconn, Delta, and Techman material events must appear first), associations (TAIROA, TEEMA, SEMI Taiwan, TCA), research (ITRI, III, NARLabs, Academia Sinica, NTU/NTHU/NCKU/NYCU), and seventeen company newsrooms across the humanoid supply chain now forming around Foxconn, TSMC fab automation, Delta, Advantech, Techman Robot, HIWIN, Solomon, and the ODM cohort (Quanta, Compal, Wistron, Pegatron), plus MediaTek and the compute vendors. Computex/TAITRA, TAIROS, and the Taipei automation show cover events, with the recycled-clip caution retained.

### 2.8 Hong Kong (31 first-hand) — from one source to thirty-one

Anchored on **HKEXnews** — arguably the single most important source for China robotics capital-markets coverage given the AgiBot/Unitree IPO pipeline — plus SFC, ITIB, ITC (ITF funding decisions), HKSTP, Cyberport, InvestHK, HKPC, and info.gov.hk press releases. The InnoHK research clusters and the five universities (HKUST including its Guangzhou campus, HKU, CUHK T Stone/medical robotics, PolyU, CityU) plus ASTRI form the research layer. The company layer exploits HK's listing-venue role: UBTECH IR, Horizon Robotics, Black Sesame, XPeng IR (humanoids), Dobot, and Hai Robotics-adjacent filings. HKTDC fairs and InnoEX cover events.

### 2.9 International bodies (20 first-hand)

IFR (World Robotics statistics), IEEE RAS conference intelligence, ISO/TC 299 and IEC standards (safety-standard revisions move procurement budgets), WIPO PATENTSCOPE, ITU AI for Good, OECD.AI, WEF C4IR, ILO and World Bank automation research, GPAI, RoboCup, CEN/CENELEC, Open Robotics/ROS Discourse, and the global fair circuit (automatica, Hannover Messe, CES, GTC — where Nvidia's robotics announcements originate).

---

## 3. How to Operate the Registry (the Bloomberg mechanics)

**Priority discipline.** The 73 P0 sources are the daily scan; P1 sources run two to three times per week; P2 sources are event-driven. The P0 set is deliberately weighted toward disclosure portals and ministries because that is where same-day, defensible, first-to-publish stories live. A daily run that opens with DART, TDnet, MOPS, HKEXnews, CNINFO, and EDGAR before touching any media site will structurally out-run the current workflow.

**Automation reality.** RSS is plentiful only in the US and Europe (10 feeds each); Asia primary sources are overwhelmingly scrape-or-API. The three integrations worth building first, in order of return: **DART OpenAPI** (free, keyword-filterable, real-time Korean filings), **SEC EDGAR full-text search API** (free, supports "robotics"/"humanoid" queries across all filings), and a **CNINFO API poll** for the China A-share robotics cohort. These three alone convert the desk's proven filings stories from lucky finds into a repeatable franchise.

**Language handling.** Roughly 40% of the registry publishes only in local language (zh, ja, ko). This is a feature, not a bug — the language barrier is precisely why these sources are under-exploited by English-language competitors. The scan workflow should translate at ingestion and preserve the original-language quote for verification.

**Wires demoted, not deleted.** Yonhap, Kyodo, Focus Taiwan, Xinhua, 36Kr, Jiqizhixin, and QbitAI stay in the system as verification-tier sources: they confirm what direct polling found, catch what it missed, and provide context — but they are no longer citation-of-record when a primary document exists, and they never count toward source minimums.

**Registry hygiene.** The master file should become the single canonical registry, stored in project shared files, replacing the three overlapping inventories. Recommend a monthly URL-health check (the verification script from this build is reusable) since roughly 5% of primary-source URLs move per quarter — during this build alone, 14 initially proposed URLs returned 404 and were repaired.

## 4. Known Limitations (stated honestly)

First, URL verification was performed programmatically on July 28, 2026; a small number of IR pages (Intuitive Surgical, Symbotic, Serve Robotics, XPeng) block automated requests and were verified only to the level of "correct canonical URL, loads in a browser" — they will need browser-based or API-based collection rather than simple scraping. Second, several Chinese government and association sites (CAA, CRIA, HIT lab pages) are intermittently unreachable from overseas infrastructure; the registry notes flag each case, but sustained monitoring may require a relay or cached-scrape approach. Third, WeChat-first companies cannot be polled by URL at all — the registry lists their accounts, but collection depends on the existing WeChat monitoring layer. Fourth, this registry deliberately excludes secondary media from the counts; the desk will still want the existing media list for discovery of stories outside the registry's coverage, which is a legitimate secondary function.

---

*Deliverables accompanying this report: `RAI_FirstHand_Source_Registry_Master_20260728.xlsx` (nine sheets: summary plus one per region, filterable, P0 rows highlighted), `tier1_firsthand_source_registry_20260728.csv` (flat file, drop-in replacement format for `references/tier1_source_registry.csv`), and eight per-region research memos with top-10 priorities and access caveats.*
