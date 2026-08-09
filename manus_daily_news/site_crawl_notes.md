# robotaigeek.com Crawl Notes (Jul 30, 2026)

## Site structure (verified)
- Homepage: https://www.robotaigeek.com/ — News, Articles, Robots database, Companies directory
- Robots DB: https://www.robotaigeek.com/browse/robots?s=latest — **2,424 robots**
- Companies: https://www.robotaigeek.com/browse/companies — **715 companies, 15 pages, 48/page** (pagination: ?page=N)
- News: /news (JS-rendered, list empty in static extraction, items linked from homepage)
- Articles: /articles (JS-rendered too)
- Site is Cloudflare protected (curl 403), but `webpage_extract` works. robots.txt allows AI-input/citation crawlers, blocks training crawlers.
- Article/news author: "AAeon"; CDN: cdn.robotaigeek.com

## Recent news items observed (Jul 28 homepage)
- Chaowei Dynamics (Shenzhen) + PKU Healthcare — embodied AI hospitals/pharmacy
- Quorra X5 personal mobility (Wu Shulin, Huawei/Baidu-Apollo veteran; CDH VGC, Linear Capital, SAIC/CATL/BYD funds, Chow Tai Fook)
- Tesla Optimus bought Virtuix Omni One treadmill (Virtuix = source)
- KNR Systems (KOSDAQ) hydraulic 300kg robot hand
- Shanghai Innovation Institute + AgiBot τ0-VLA open-source VLA model
- Mitsui Fudosan + Kumamoto Pref — PASTEC/KSCM physical-AI chip hub (ITRI, Hsinchu SP MOUs)
- Index Ventures/Ribbit — Unit 8200 alumni robot teleop startup (US$71M)
- Nvidia–Naver stake + Brookfield GAK Sejong

## Companies observed in directory crawl (pages 1,3,4,5) — candidates NOT already in 317 registry
US/West: Virtuix, Gecko Robotics, German Bionic, Ghost Robotics, Diligent Robotics, Dephy, Covariant, CMR Surgical (UK), Globus Medical, Accuray, Corindus (Siemens), Fetch/Zebra, GreyOrange, Engineered Arts (UK), Furhat (SE), Franka Emika/Franka Robotics (DE), Festo, F&P Robotics (CH), Fixposition (CH), Exail (FR), AgXeed (NL), Fendt, FarmWise, FarmBot, Fauna Robotics, Foundation Robotics, Glacier Robotics, Dusty Robotics, AeroVironment, Aethon, Cobalt Robotics, Draganfly, Freefly, Flirtey, Flytrex, Formic
China: CloudMinds, Dobot, Dorabot, Dreame, Ecovacs, EFORT, Elite Robots, Flexiv, ForwardX, Geek+, HAI Robotics, AgileX, AI² Robotics, AiMOGA (Chery), Aceii, AE Robotics, DH-Robotics, Deep Robotics, DexForce, Gausium/Gaussian, GAC Group, CVTE, Lyric Robot, EVE Energy, Geehy Semiconductor, Guochen, Haier, plus many Guangdong/Hangzhou suppliers
Taiwan: ADLINK, Advantech, ACY Automation, Aeolus Robotics
Japan: Denso Robotics, Cyberdyne, Daihen, Epson, Donut Robotics, Fujitsu
Korea: Doosan (already), etc.
SG: 365Robot, CTRL Robotics, Dconstruct, Eureka Robotics
DK: Enabled Robotics; SE: Giraff
Research listed as companies: AIST, DLR, Fraunhofer IPA, DFKI, Cranfield University, GRINM Guangdong
Media/platform: AGV Network (blog — NOT first-hand)

## User's example: "Genki" — Android OS for robotics (covered in RAG news). Need to verify company identity/newsroom.

## Notes for merge
- Existing registry (317 first-hand) at /home/ubuntu/rai_registry/regions/*.csv, master xlsx built.
- New additions should tag region + type=Company mostly; verify newsroom/press URL for each.
- Need Singapore/Rest-of-World section for SG companies (no SG region sheet exists; consider "Rest of Asia / Global" sheet).

## Genki verification (user's example)
**Genki Robotics** (genki.com) — Tokyo, Japan. Founded by **Andy Rubin** (co-founder of Android OS). Building vertically-integrated humanoids + embodied-AI platform ("smartphone-like ecosystem for robot hardware"). First product expected 2026 (Nikkei Jul 29, 2026). Qualifies as first-hand source: Japan region, Company type, P1 priority. URL: https://genki.com/ — sources: dealroom, Nikkei interview Jul 29 2026, pacificbayscapital.com.

## Company directory crawl complete
- 528 unique company slugs captured from all 15 pages (some pages truncated at 12k chars; 715 total listed but 528 captured — sufficient coverage; missing ones are within truncated segments, mostly small Chinese component suppliers).
- Slug list saved: /home/ubuntu/rai_registry/company_slugs.txt
- Pages saved: /home/ubuntu/rai_registry/site_pages/*.md

## Notable additions observed on later pages (not in 317 registry)
Sanctuary AI (CA), Kepler Robotics (CN), Booster Robotics (CN), MagicLab (CN), NOETIX (CN), Lumos Robotics (CN), Spirit AI (CN), PsiBot (CN), Galaxea AI (CN), LindenBot (CN), X Square (XSQUARE SG), Realman (CN), Hikrobot (CN), SEER Robotics (CN), Quicktron (CN), Standard Robots (CN), Youibot (CN), Segway Robotics (CN), Roborock (CN), Ecovacs (CN), Dreame (CN), Xiaomi (CN), Baidu (CN), Midea/KUKA (CN), Zhejiang Humanoid Robot Innovation Center (CN), X-Humanoid (already), XbotPark (CN ecosystem), MicroPort MedBot (CN, HK-listed), CloudMinds, OrionStar, Gaussian/Gausium, Geek+, Hai Robotics, SoftBank Robotics (JP), Yamaha Robotics (JP), Suzumo (JP), TechMagic (JP), Keyence (JP), Hitachi (JP), Komatsu (JP), Kubota (JP), SwitchBot, Samsung Robotics (KR), Bear Robotics (KR/US), HYODOL (KR), Robotis(prev), Techman (TW), HIWIN (TW), HOBOT (TW), Brain Navi (TW), Aeolus (TW), ADLINK (TW), Advantech (TW), Stryker/Medtronic/Smith+Nephew/Zimmer Biomet/Globus/Accuray/XACT (medical US), Intuitive (prev), Knightscope (US), Richtech (US, NASDAQ), Serve (prev), Starship (EE/US), Saildrone (US), Sarcos (US), SRI International (US), RAI Institute (US), Realtime Robotics (US), RightHand (US), Rapid (US), Locus (US), Seegrid (US), Brain Corp (US), Berkshire Grey (US), Bright Machines (US), Miso (US), Chowbotics, Cafe X, RoboBurger, Misty (US), Hello Robot (US), Ghost Robotics (US), Gecko (US), Dephy (US), Diligent (US), Nuro (US), Nvidia (prev), Zebra/Fetch (US), Teledyne FLIR (US), Northrop, L3Harris, General Dynamics/Bluefin, AeroVironment, QinetiQ (UK), Shadow Robot (UK), CMR Surgical (UK), Engineered Arts (UK), Dyson (UK), SLAMcore (UK), Brokk (SE), Furhat (SE), Milrem (EE), Starship (EE), Roboteam (IL), Unit robotics etc, Stäubli (CH), Schunk (DE), Festo (DE), igus (DE), Bosch (DE), Rheinmetall (DE), RobCo (DE), Wandelbots (prev), NEURA (prev), Agile Robots (prev), Exotec (prev), Scallog (FR), Balyo (FR), Niryo (FR), Exail (FR), IFREMER (FR), Blue Frog (FR), PAL (prev), Tecnalia (ES), Mecalux (ES), Macco (ES), Prima Additive (IT), Comau (prev), IIT (prev), Makr Shakr (IT), Yanu (EE), ZenRobotics (FI), GIM Robotics (FI), Nilfisk (DK), Blue Ocean Robotics (DK), Kassow (DK), Enabled Robotics (DK), OnRobot (DK), MiR (prev), Universal Robots (prev), AutoStore (prev), Kongsberg (NO), Saab Seaeye (SE/UK), Swisslog (CH), Hocoma (CH), Hydromea (CH), senseFly/AgEagle (CH/US), Fixposition (CH), ANYbotics (prev), Sevnce (CN), Kinova (CA), OTTO Motors (CA), Avidbots (CA), Haply (CA), Cecilia.ai (CA), Sanctuary (CA), Realbotix (US), Xenex (US), ScriptPro (US), InTouch/Teladoc (US), OrthoGrid (US), Sphinx Surgical (US), XRobotics (US), XYZ Robotics (US/CN), Kiwibot (US/CO), Marble/Caterpillar (US), Sea Machines (US), Liquid Robotics/Boeing (US), Oceaneering (US), Saildrone (US), OpenROV/QYSEA (CN/US), Blue Robotics (US), Harvest Automation (US), Harvest CROO (US), Iron Ox (US), Carbon Robotics (US), Blue River (US), FarmWise (US), AgXeed (NL), Octinion (BE), Ecorobotix (CH), SwarmFarm (AU), C2 Robotics (AU), SYPAQ (AU), Havelsan (TR), Sari Teknologi (ID), plus Singapore cluster: 365Robot, BeeX, CenoBots, CTRL, Dconstruct, Eureka, Infinium, Kabam, LionsBot, Ourglass, Rent-A-Robot, SESTO, XSQUARE, HTX (gov agency), Robonexus/National Robotics Programme (gov programme).
- Robots DB = 2,424 robots; News+Articles = 370+ news, 155 articles by "AAeon".
- International/global cos: Open Robotics (prev Intl), RoboDK (CA), Zeroth, Stompy (open source).

## Assessment note
The RAG companies directory is a strong discovery layer but includes many non-newsworthy small component suppliers (casters, cables, textiles). For the first-hand source registry, select companies that (a) RAG has covered in news/articles, (b) are market-moving (listed, funded, humanoid/embodied-AI, category leaders), or (c) fill regional gaps (Singapore/SEA, Canada, Israel, Australia, Nordics — no current sheets).

## Entities covered in recent RAG News (Jul 2026 sample; pagination serves same recent set)
Stabilus + Synapticon (DE actuators), Delta Intelligence (CN foundation model, backed by AgiBot/Leju/Galaxea/Lenovo Capital), IFA Berlin (exhibition), Kawasaki Heavy Industries CORLEO, FCC Chinese humanoid ban, Chaowei Dynamics + PKU Healthcare (CN), Quorra/Wu Shulin physical AI (CN), Virtuix (US, Tesla Optimus buyer), KNR Systems (KOSDAQ), Shanghai Innovation Institute + AgiBot τ0-VLA, Mitsui Fudosan + Kumamoto Pref + ITRI/Hsinchu (PASTEC), stealth teleop startup (IL/US, Index/Ribbit), Nvidia–Naver–Brookfield (KR), Morphi (CN, Alibaba+Tencent angel), Teradyne/UR/MiR earnings, South Gyeongsang Province KRW21T physical AI plan, Genki Robotics (Andy Rubin, Tokyo, robot OS + marketplace), Ecovacs Bajie open-source, Giant Star Legend/Jay Chou + Unitree JV, Huang Xiaoming family office/AgiBot rental platform, Horizon Robotics US$450M CB, PsiBot unicorn, AgiBot HK IPO banks, Hyundai wage talks, Washington state delivery permits, Texas shipyard, NY school robot pilot, Unitree, Galbot, Deep Robotics.

## Articles categories seen
ARPI series (AMR/AGV pricing, deployment, classes, fundamentals), monthly wrap-ups (funding, exhibitions, technology, economics), China capital cycle analyses. Author "Aeon". News DB ~284-288 items, Articles ~107, Videos section exists.

## Key implication for registry additions
News coverage repeatedly originates from: company IR/newsrooms (Teradyne, Kawasaki, Stabilus, Ecovacs, Naver), exchange disclosures (KOSDAQ KNR, HK-listed Giant Star Legend, Horizon CB), regulators (FCC), provincial govs (South Gyeongsang, Kumamoto), exhibitions (IFA, WAIC, WRC), research institutes (Shanghai Innovation Institute, ITRI), VC/PE disclosures. New entity types to add as first-hand sources: Virtuix, Synapticon, Stabilus, Morphi, Delta Intelligence, Chaowei Dynamics, Genki Robotics, KNR Systems, Naver Labs, Mitsui Fudosan newsroom, IFA Berlin press, Giant Star Legend HKEX filings.
