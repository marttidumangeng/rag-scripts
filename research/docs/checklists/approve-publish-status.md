---
type: checklist
title: Content Queue — Approve / Publish Status
status: draft
version: 1.2
owner: AI
last_updated: 2026-07-22
tags:
  - content-queue
  - moderation
  - approve
---

# Content Queue — Approve / Publish Status

Living checklist of enriched companies ready (or nearly ready) for public view.

**Product rule:** for robots, **Approve = Publish** (one action → `status=published`).

**Baseline audit:** 2026-07-19 via `_audit_ready_to_approve.py`  
**Source JSON:** [../staging/reports/ready-to-approve.json](../staging/reports/ready-to-approve.json)  
**Must-clear gates:** photo · features (≥40 chars) · country · categories · uses  
**Soft-required (must try every enrich):** availability · typed specs (`payload_kg` / dims / `speed` km/h / … via PATCH)  
**Soft OK to publish if absent after a real pass:** video / tags / price / release year / specs with no OEM numbers

## How to update this doc

When you approve, publish, or clean a company:

1. Change **Status** to `approved` / `published` / `partial` / `blocked` / `done` (0 pending).
2. Update **Pending** to the remaining `pending_review` count (or `0`).
3. Move the row to [Cleared](#cleared--zero-pending) when the company queue is empty.
4. Add newly cleaned companies under the right section (or [Needs cleanup](#needs-cleanup--not-ready)).
5. Bump `last_updated` in frontmatter and append a line under [Change log](#change-log).

Admin queue pattern:

`https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=<ID>`

Re-audit snapshot (optional):

```bash
cd scripts/research
python -u _audit_ready_to_approve.py
```

---

## Approve tonight (priority)

Smaller clean fleets — best volume for a focused session. Pangolin country was fixed after the audit (company `country_id` + robot `manufacturer_countries`).

| Status | Company | ID | Pending | Soft notes | Queue |
|--------|---------|---:|--------:|------------|-------|
| ready | Foshan Tefude Automation | 1404 | 7 | Approve **2503, 1972, 2504, 1973, 1975, 1974, 1978** (TFD-RD4×4 + TFD-RP4×2 + joint-parallel). **4** SEO/packaging shells rejected. RD4 heroes = DETAIL DISPLAY crops (not packing-line banners). CDN **7/7** distinct. Scripts: `fix_tefude_1404_robots.py`, `fix_tefude_1404_rd4_heroes.py`. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1404) |
| ready | Draganfly Innovations | 1444 | 4 | Apex + Commander 3XL + Heavy Lift + Tango2 | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1444) |
| ready | Glydways | 1454 | 1 | Glydcar Announced; soft dims/speed absent | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1454) |
| ready | Nitto Seiko America | 1415 | 5 | SR375/580/780 + PD400UR; heroes restored | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1415) |
| ready | Formic Technologies | 1450 | 8 | Distinct model-specific OEM heroes restored; CDN 8/8; moderation publish 8/8 | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1450) |
| ready | Briggo (Costa Coffee) | 406 | 1 | Smart Café official Costa hero restored; dispensing use fixed; moderation publish 1/1 | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=406) |
| partial | FANUC | 189 | 1 | Stakeholder approved all but imageless **M-810iA/45 (4117)** IMAGE TO-DO | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=189) |
| ready | EVE Energy | 975 | 3 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=975) |
| ready | Beijing Humanoid Robot Innovation Center | 834 | 2 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=834) |
| ready | Cleanfix | 368 | 2 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=368) |
| ready | Fraunhofer IPA | 133 | 2 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=133) |
| ready | AnyWit Robotics | 13 | 1 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=13) |
| ready | Astribot | 15 | 1 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=15) |
| ready | Fauna Robotics | 837 | 1 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=837) |
| ready | Furhat Robotics | 39 | 1 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=39) |
| ready | Oversonic Robotics | 826 | 1 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=826) |
| ready | Roborock | 223 | 1 | | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=223) |
---

## Big fleets (gates pass — spot-check first)

Must-clear cleared for all pending rows. Spot-check a few heroes/URLs before bulk approve.

| Status | Company | ID | Pending | Soft notes | Queue |
|--------|---------|---:|--------:|------------|-------|

---

## Partial (approve clean subset only)

Approve robots that pass must-clear; leave blocked IDs in queue until fixed.

| Status | Company | ID | Clean / pending | Blockers on remainder | Queue |
|--------|---------|---:|----------------:|-----------------------|-------|
| partial | REEMAN | 1421 | 10 / 22 | Approve only **2305, 2316, 2326, 2330, 2332, 2334, 4658, 4659, 4661, 5083**. Hold **12** imageless IMAGE TO-DO (forklift banners / food-delivery callouts / Big Dog / Chengying / R1D1 infographic / HUSSAR PRO factory / Moon Knight square). **12** CN/SEO/chassis duplicates rejected. Company website → `https://reemanbot.com/`. Script: `fix_reeman_1421_robots.py`. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1421) |
| partial | Huayan Robotics | 1490 | 0 / 27 | Stakeholder approved the nine image-backed current models; API shows **18 published / 27 pending** across all 45 company records. Exact official renders are now staged for all **26** imageless current models as external, non-primary `review_required` candidates: 26/26 HTTPS image bodies, dimensions, robot identities, URLs, and SHA-256 hashes validated with no collisions. Production is unchanged because its serializer still omits rights metadata on 61 published photos; apply is held until the new rights workflow deploys. Legacy S35 `3679` is the separate 27th pending record. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1490) |
| partial | MiR | 370 | 0 / 7 | Seven canonical products scalar-curated but held for image rights. MiR/Teradyne permits only noncommercial informational use; written permission required. Four imageless; three existing restricted galleries require authenticated detachment. Four duplicate/invalid rows rejected; MC250/MC600 reparented to Enabled Robotics. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=370) |
| partial | Enabled Robotics | 1532 | 0 / 2 | ER-FLEX (MC250) + ER-MAX (MC600) reparented from MiR; exact specs/identity applied. OEM terms require written approval for image copying; existing galleries require authenticated detachment. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1532) |
| partial | DELTA Electronics (Shanghai) | 1206 | 9 / 17 | Approve only **5199, 3663, 3664, 2943, 2933, 3661, 2935, 2937, 2941**. Hold 8 exact-SKU media collisions/undocumented R65 suffixes. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1206) |
| partial | Mujin | 810 | 8 / 10 | Approve only **3763, 3762, 3760, 3759, 3757, 3756, 3754, 3753**. Hold Pallet Changer 3758 + MujinRCP 3755; duplicate-language Depalletizer 3761 rejected. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=810) |
| partial | Geek+ | 1398 | 14 / 17 | Approve only **1782, 1783, 1784, 1791, 1793, 1794, 1795, 1796, 2776, 2778, 2779, 3582, 3583, 4136**. Hold P800H 1785, S100C 1792, RS11-DA 4950 for exact media; 38 duplicate/solution/configuration/alias shells rejected. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1398) |
| blocked | Yamaha Robotics | 1484 | 0 / 7 | Do not approve pending **3325, 3326, 4386–4389, 4391**: their CADENAS-derived heroes lack republication permission. Three published records (**4385, 4392, 4393**) also use Yamaha catalog-derived renders and require authorized removal/unpublish review; published B5 `4390` does not use the known restricted upload. Cleanup attempts were blocked by both S3 `DeleteObject` and admin-photo `403` permissions. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1484) |
| partial | Stäubli Robotics | 1475 | 0 / 19 | Scalar-curated **19** keepers (TS2×4, TX2×7, MedX, HE×5, TP80 Discontinued, PF3); **26** duplicate/legacy RX rejected. All keepers deliberately imageless: Stäubli imprint forbids website image republication without written authorization. Approve allowlist empty until rights clearance. Company website → `https://www.staubli.com/global/en/robotics.html` + Switzerland. Script: `fix_staubli_1475_robots.py`. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1475) |

---

## Needs cleanup (not ready)

Do not bulk-approve. Fix blockers first, then move the row up.

| Status | Company | ID | Pending | Blockers | Queue |
|--------|---------|---:|--------:|----------|-------|
| blocked | ACY Automation | 1369 | 0 | **Pending EOAT rejected** as `non_robot` overnight. **~35 published EOAT** still need reject-or-keep decision. | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=1369) |
| blocked | inVia Robotics | 397 | 0 | Two published records are the same inVia Picker: keep fully enriched **2977**, reject legacy CJK/incomplete **272**; PickerWall 2978 already rejected | [open](https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/?company_id=397) |

**Country write tip:** company field is `country_id` (e.g. China = `3`). Robot fields are `manufacturer_country_ref` + `manufacturer_countries: [<id>]`. String `"China"` alone often does not stick via the research API.

---

## Cleared (zero pending)

| Status | Company | ID | Cleared at | Notes |
|--------|---------|---:|------------|-------|
| done | Hitbot Technology (Shenzhen) | 976 | 2026-07-22 | Stakeholder approved all **7** Z-Arm robots after hero fix (nav icons/drawings/HIWIN S922 replaced); **7 published / 0 pending** |
| done | Bluesword | 997 | 2026-07-21 | Stakeholder approved 9 canonical robots; 8 category/family/phantom rows rejected; 0 pending |
| done | Balyo | 242 | 2026-07-21 | 6 canonical robots published / 11 duplicates rejected / 0 pending; legacy TUGGY 372 + REACHY 373 retired after approval |
| done | Dobot (Yuejiang) | 1161 | 2026-07-21 | 13 published / 0 pending |
| done | Gurki | 974 | 2026-07-21 | 8 published / 0 pending |
| done | Intamsys | 1073 | 2026-07-21 | 5 published / 0 pending |
| done | Intuitive Surgical | 52 | 2026-07-21 | 5 published / 0 pending (3 newly approved + 2 prior) |
| done | 6 River Systems | 1373 | 2026-07-21 | Chuck AMR published / 0 pending |
| done | Auris Health | 1511 | 2026-07-21 | MONARCH QUEST published / 0 pending |
| done | Infinium Robotics | 783 | 2026-07-21 | Infinium Scan published / 0 pending |
| done | Plus One Robotics | 254 | 2026-07-21 | 0 pending — PickOne (3793) rejected as `non_robot_software`; OEM defines it as vision software for third-party robots |
| done | Freefly Systems | 1452 | 2026-07-21 | 4 published / 0 pending |
| done | Dusty Robotics | 1510 | 2026-07-21 | FieldPrinter 2 published / 0 pending |
| done | Flytrex | 1448 | 2026-07-21 | Sky2 + Sky published / 0 pending; Sky had an IMAGE TO-DO before approval |
| done | Liquid Robotics (Boeing) | 429 | 2026-07-21 | Wave Glider published / 0 pending |
| done | Asensus Surgical | 328 | 2026-07-21 | Senhance + ISU published / 0 pending; CJK dupe rejected; one unrelated draft remains |
| done | Harvest Automation | 1502 | 2026-07-21 | HV-100 published / 0 pending |
| done | Diversey / Solenis (TASKI) | 367 | 2026-07-21 | 3 published / 0 pending |
| done | Auris Health / J&J | 383 | 2026-07-21 | 3 published / 0 pending; CJK dupe rejected |
| done | Globus Medical | 432 | 2026-07-21 | ExcelsiusFlex published / 0 pending |
| done | Shift Robotics | 856 | 2026-07-21 | Moonwalkers + Moonwalkers Aero published / 0 pending |
| done | Jiangsu DINGS | 1512 | 2026-07-20 | 0 pending — rejected Gripper (5209) as EOAT `non_robot` |
| done | AGV Network | 1322 | 2026-07-20 | 0 pending — rejected AGV Reach Truck (615) media-directory shell |
| done | Canvas Technology (Amazon) | 805 | 2026-07-20 | 0 pending — rejected phantom Canvas AMR 3612; cleared wrong Instructure LMS website |
| done | NASA | 174 | 2026-07-20 | 0 pending — rejected 22 Xiaomi/CyberDog misfiles |
| done | Bluefin Robotics (GDMS) | 160 | 2026-07-20 | 4 published / 0 pending (Bluefin-9/12/HAUV + Bluefin-21 EN soft-fill); rejected BF-21 dupe 5044 |
| done | Lumos Robotics | 70 | 2026-07-20 | 5 published / 0 pending (LUD + LUS 2 + MOS 2 + NIX S3 + Touch R1) |
| done | SMP Robotics | 212 | 2026-07-20 | 15 published / 0 pending (13 S-series configs + Argus S5.2 + Bird Control soft-filled) |
| done | Jaten Robot | 1461 | 2026-07-20 | 9 published / 0 pending; restored SDM300-339-MGD (5185) + MN30-164 (5190, hero swap); kept 5× `*-335-MG0` phantoms rejected (dead shared 404 image) |
| done | Ekso Bionics | 147 | 2026-07-20 | 5 published / 0 pending (EksoNR + Indego Personal + EVO + EksoGT/Vest Discontinued); rejected Indego dupe 436 + family shell 179 |
| done | VisionNav Robotics | 807 | 2026-07-20 | 16 published / 0 pending (VNE/VNK/VNP/VNQ/VNR/VNSL/VNST/VNT fleet) |
| done | Accuray Inc. | 1378 | 2026-07-20 | 6 published / 0 pending (Radixact + TomoTherapy Hi-Art/HD/HDA approved; keepers CyberKnife S7/M6 222/368); trademark shells 1477/1478 rejected |
| done | Dephy | 814 | 2026-07-20 | 2 published / 0 pending (Sidekick + Sidekick Starter Pack $4,500; family `dephy:sidekick`) |
| done | Blue River Technology | 423 | 2026-07-20 | 3 published / 0 pending (See & Spray Ultimate + See & Spray + LettuceBot Discontinued) |
| done | Cobalt Robotics | 213 | 2026-07-20 | published Cobalt Security Robot (399) EN soft-patched; pending CJK dupe **1659** rejected |
| done | Foundation Robotics | 851 | 2026-07-20 | 2 published / 0 pending (Phantom + Construction Layout Robot) |
| done | XRobotics | 114 | 2026-07-20 | 1 published / 0 pending (xPizza Cube) |
| done | Piaggio Fast Forward | 236 | 2026-07-20 | 3 published / 0 pending (gitamini + gita plus + Grogu™ gitamini; family `piaggio:gita`) |
| done | iRobot | 342 | 2026-07-20 | 31 published / 0 pending (17 rejected); verify-chip fixes included; j9 (2031) published alongside j9+ |
| done | Bear Robotics | 198 | 2026-07-20 | 11 published / 0 pending (Servi Plus/mini/Q + Servi Clean + Carti 100/LP/400/600/1000/1500) |
| done | IIT (Italian Institute of Technology) | 50 | 2026-07-20 | 11 published / 0 pending (iCub/ErgoCub/HyQ family + soft/plant research platforms) |
| done | FarmBot Inc. | 34 | 2026-07-20 | 4 published / 0 pending (Genesis v1.8 + XL + Express v1.0/v1.1) |
| done | Aethon | 7 | 2026-07-20 | 4 published / 0 pending (T3/T3 XL/Zena RX/Zena); 10 rejected with expanded reasons |
| done | Gecko Robotics | 806 | 2026-07-20 | 3 published / 0 pending (TOKA 3/4/Flex; photo hold fixed then stakeholder Approve) |
| done | SIASUN | 1424 | 2026-07-20 | 82 published / 0 pending (bulk Approve after CDN heroes + purpose rewrite); 64 rejected off-catalog stubs |
| done | EFORT | 1479 | 2026-07-20 | 67 published / 0 pending (full fleet bulk Approve after China country + purpose/family/specs soft patch) |
| done | Locus Robotics | 69 | 2026-07-20 | 4 published / 0 pending (Origin + Vector + Array + LocusBot) |
| done | Seegrid | 209 | 2026-07-20 | 5 published / 0 pending (Lift RS1/CR1/EL1 AMR + Tow Tractor S7 + Palion series); 3 same-URL dupes rejected |
| done | Boston Dynamics | 18 | 2026-07-20 | 5 published / 0 pending (Stretch approved; Spot Enterprise + Stretch 2.0 + BigDog/LS3 + Atlas CJK already published); Atlas (1761) + Spot with Arm (1833) rejected |
| done | Trossen Robotics | 307 | 2026-07-20 | 10 published / 0 pending (WidowX AI last; Interbotix arms + ALOHA kits; families + typed specs) |
| done | AMP Robotics | 259 | 2026-07-20 | 2 published / 0 pending (Delta + Delta Compact); Clarity/Insight/SmartTons/Vision/Jet/MicroJet/Cortex/AMP ONE rejected |
| done | Figure AI | 36 | 2026-07-20 | 5 published / 0 pending (Figure 03 approved; 01/02/Helix/CJK shell already published) |
| done | Carbon Robotics | 266 | 2026-07-20 | 7 published / 0 pending (G2 200/300/400/600/1200 + prior LaserWeeder™ + ATK) |
| done | Stryker | 350 | 2026-07-20 | 5 published / 0 pending (Mako 4 + Total Knee/Hip/Partial Knee; MAKO SmartRobotics 225 already published) |
| done | Anduril Industries | 284 | 2026-07-20 | 5 published / 0 pending (Fury/Ghost/Altius/Barracuda/Dive-XL); Lattice+Menace+Barracuda-100/250 rejected |
| done | Diligent Robotics | 29 | 2026-07-20 | 2 published / 0 pending (Moxi + Moxi 2.0) |
| done | DAIHEN | 1402 | 2026-07-20 | 24 published / 0 pending (FD fleet + Flat Panel; Almega AX rejected) |
| done | Flexiv | 315 | 2026-07-20 | 5 published / 0 pending (Rizon 4/10 +F/T + Moonlight); Grav EOAT rejected |
| done | Realbotix | 311 | 2026-07-20 | 3 published / 0 pending (B/M/F Series; Aria already published) |
| done | Iron Ox | 271 | 2026-07-20 | 1 published / 0 pending (Grover Discontinued; company defunct) |
| done | Picnic Works | 274 | 2026-07-20 | 1 published / 0 pending (Pizza Station / Leo) |
| done | Harvest CROO Robotics | 268 | 2026-07-20 | 1 published / 0 pending (B8 Harvester) |
| done | Monarch Tractor | 265 | 2026-07-20 | 2 published / 0 pending (MK-V + Vineyard) |
| done | FarmWise | 263 | 2026-07-20 | 2 published / 0 pending (Vulcan + Titan FT-35); CJK dupes 459/456 rejected |
| done | Covariant | 257 | 2026-07-20 | RFM-1 (2710) rejected — foundation model / AI stack, not a robot SKU. Queue empty. |
| done | Glacier Robotics | 261 | 2026-07-20 | 2 published / 0 pending (Glacier Robot + Fiber QC); website → endwaste.io |
| done | Kawasaki Robotics | 773 | 2026-07-20 | 56 published / 0 pending (stakeholder bulk Approve = Publish) |
| done | Vecna Robotics | 208 | 2026-07-20 | 3 published / 0 pending (AFL, ATG, CPJ); CaseFlow + Agile Robots umbrella rejected |
| done | Berkshire Grey | 256 | 2026-07-20 | 4 published / 0 pending (Core, Scoop, Stride, Dispatch); dupe 4044 rejected |
| done | Nuro | 199 | 2026-07-20 | R2 Discontinued published; Lucid×Uber mashup rejected; R3 deferred |
| done | Skydio | 137 | 2026-07-20 | X10 + X10D published; X2 Discontinued; R1 rejected |
| done | UT Austin (Robot Perception Lab) | 1308 | 2026-07-20 | Harmon (605) rejected — CoRL method/paper, not a robot. No RPL OEM SKUs; DRACO 3 is Apptronik/HCRL. Queue empty. |
| done | RightHand Robotics | 258 | 2026-07-20 | RightPick 4 approved/published |
| done | ABB Robotics | 190 | 2026-07-19 | 141 published / 0 pending (stakeholder bulk Approve = Publish) |
| done | Shield AI | 285 | 2026-07-19 | V-BAT + X-BAT approved/published; Hivemind software skipped |
| done | Knightscope | 211 | 2026-07-19 | K5 + K7 published; K1 Hemisphere rejected (stationary ECD) |
| done | JAKA Robotics | 771 | 2026-07-19 | 13 published / 0 pending (Zu/S/Pro/Mini cobot arms). Shared lineup/QR gallery fixed earlier. |
| done | Ghost Robotics | 168 | 2026-07-19 | Vision 60 enriched/published; rejected Q-UGV dupe + Spirit 40 (off catalog) |
| done | Serve Robotics | 252 | 2026-07-19 | Gen2 + Gen3 approved/published; Moxi stays under Diligent 29 |
| done | Exail Robotics | 428 | 2026-07-19 | All approved incl. Cameleon LG/MK3/Iguana hi-res datasheet heroes |
| done | Richtech Robotics | 131 | 2026-07-19 | Stakeholder approved/published (Dex/Titan/Matradee+/Scorpion/DUST-E/F3300 + ADAM) |
| done | Apptronik | 14 | 2026-07-19 | Apollo + Apollo 2 approved/published |
| done | Agility Robotics | 9 | 2026-07-19 | Cassie approved; Digit already published |
| done | Sanctuary AI | 92 | 2026-07-19 | Phoenix (5513) approved/published by stakeholder |
| done | Realman | 882 | 2026-07-19 | 26 published + 2 new pending (ECO63 Std/Force). RX71 renamed Standard. ECO62/RX71/RX75 Force not separate SKUs. |
| done | Pangolin Robotics | 1413 | 2026-07-19 | Approved/published; names de-prefixed; Xiaoyu video title fixed |
| done | Universal Robots | 192 | 2026-07-19 | Published after enrich |
| done | Segway Robotics | 237 | ≤2026-07-19 | |
| done | KUKA | 1396 | 2026-07-19 | All approved/published; AVIF stubs repaired; variants audited |
| done | Unitree Robotics | 109 | 2026-07-19 | 49 published / 0 pending. Last 3 (R1-A7/Aliengo/A2-W) gates cleared + published_at set. A2 footed hero fixed; Go2-W uncontaminated; variant repairs applied. |
| done | Noblelift | 1028 | 2026-07-19 | 55 published / 0 pending. Forced missing PNG 1280 thumbs (repair skipped when WebP present). Family shared heroes intentional; AGV near-dupes 2210↔3336, 2214↔3335. |
| done | RobCo | 239 | 2026-07-19 | 15 published / 0 pending. Unique heroes (Alfie + 14 named arms). Mighty Martha PNG 1280 force-uploaded. |
| done | Epson (Seiko Epson) | 400 | 2026-07-20 | 51 published / 0 pending (14 rejected). Stakeholder merged duplicate company **Epson Robots (1445)** into 400 — 1445 company record gone. |
| done | Mitsubishi Electric | 73 | 2026-07-19 | 26 published / 0 pending. Forced 6 missing gallery 1280 thumbs. MELFA FR/CRH series family heroes intentional. |
| done | CTRL Robotics | 782 | 2026-07-21 | 1 published / 5 rejected / 0 pending. Box `5086` published; wrong-company OEM products were reparented before approval. |
| done | YASKAWA Electric / Motoman | 772 | 2026-07-21 | 75 published / 0 pending. API verified payload, reach, family, country, and valid features on 75/75; weight/repeatability on 67/75. |
| done | Hyundai Robotics | 49 | 2026-07-22 | 12 published / 11 rejected / 0 pending. Stakeholder approved remaining HC3303B / HDC25 / HDC35 / LABOT / Robot Barista after held-set clearance. |
| done | Bühler Group | 1507 | 2026-07-22 | 10 published / 0 pending. Stakeholder approved full SORTEX/SPARK set including prior R500 5 + SPARK Pro holds. |
| done | Wuxi BEWIS Sensing Technology LLC | 1225 | 2026-07-22 | 0 published / **62 rejected** / 0 pending. Entire queue rejected as `non_robot` inertial/attitude sensor components (inclinometer/compass/IMU/gyro/pressure valve), not robot platforms. Website kept `https://www.bwsensing.com/`. |

---

## Change log

| Date | Change |
|------|--------|
| 2026-07-22 | Foshan Tefude Automation (1404) curated full enrichment: **7 pending keepers / 4 rejects**; remapped SEO shells → TFD-RD4/RP4 SKUs; replaced shared banner + text-heavy RD4 packing-line heroes with robot-dominant DETAIL DISPLAY crops; CDN **7/7** distinct. Left `pending_review`. Scripts: `fix_tefude_1404_robots.py`, `fix_tefude_1404_rd4_heroes.py`. |
| 2026-07-22 | Stakeholder approved Hitbot (976); API verified **7 published / 0 pending**. Moved to Cleared. Next: Foshan Tefude Automation (1404). |
| 2026-07-22 | Hitbot (976) heroes fixed: replaced nav icons + dimensional drawings + wrong-brand HIWIN S922 with official HITBOT product renders (**7/7** distinct CDN). Script: `fix_hitbot_976_heroes.py`. |
| 2026-07-22 | Stäubli Robotics (1475) curated: **19 pending / 26 rejected / 0 publishable**. Deduped TS2/TX2 triple imports; enriched family/specs/tags from Product-range + TS2/TX2 leaflets + HE/PF3 pages; TP80 → Discontinued (Food Flash: TS2 replaces FAST picker); all heroes held for imprint rights (`robot.mkg@staubli.com`). Script: `fix_staubli_1475_robots.py`. |
| 2026-07-22 | Wuxi BEWIS Sensing (1225) queue cleared: rejected all **62** `pending_review` as `non_robot` sensor components (IDs 2795–2804, 3597–3606, 4997–5038). Final **0 published / 62 rejected / 0 pending**. Website unchanged. |
| 2026-07-22 | Stakeholder approved Bühler Group (1507) all 10; API verified **10 published / 0 pending**. Moved to Cleared. Next target: BEWIS Sensing (1225). |
| 2026-07-22 | Bühler Group (1507) curated full enrichment: **8 publish / 2 hold**; company website → `https://www.buhlergroup.com/` + Switzerland; CDN **8/8** distinct heroes. Approve allowlist: **5069, 5070, 5071, 5073, 5074, 5075, 5076, 5077**. Hold R500 5 + SPARK Pro IMAGE TO-DO (stale CDN needs staff detach). Script: `fix_buhler_1507_robots.py`. |
| 2026-07-22 | REEMAN (1421) curated full enrichment: **22 keepers / 12 rejects**; company website → `https://reemanbot.com/`; China + Available; CDN **10/10** distinct heroes. Approve allowlist: **2305, 2316, 2326, 2330, 2332, 2334, 4658, 4659, 4661, 5083**. Hold 12 IMAGE TO-DO. Script: `fix_reeman_1421_robots.py`. |
| 2026-07-22 | Stakeholder confirmed Hyundai Robotics (49) fully done; API verified **12 published / 11 rejected / 0 pending**. Moved to Cleared. Started full enrichment for REEMAN (1421). |
| 2026-07-21 | Staged exact official Huayan renders for all **26** imageless current models as candidate-only `review_required` metadata. Validation passed 26 unique URLs and content hashes, HTTPS/magic bytes/dimensions, live robot identity/status/media, and strict backend enums; **20 tests passed**. No production write or image copy occurred. Production readiness remains false until the rights workflow exposes `rights_status`. |
| 2026-07-21 | Stakeholder approved Huayan's nine image-backed current models; API verified company totals **18 published / 27 pending**. The remaining 26 current models are not blocked by image discovery alone: official exact/family imagery and downloadable CAD assets exist, but no reusable commercial license or written republication grant was found. Keep them held pending Huayan permission; legacy S35 `3679` is the separate 27th pending record. |
| 2026-07-21 | Stakeholder approved YASKAWA Electric / Motoman (772); API verified **75 published / 0 pending** and moved the company from Big fleets to Cleared. |
| 2026-07-21 | Huayan (1490) Task 5 production apply updated and individually verified all 42 current model records without creation, status drift, media/video-row changes, partial writes, blockers, or errors. Post-apply dry-run: 42 current / 0 missing / 0 unexpected, 26/26 licensing notes. Moderation dry-run: 10 publish / 0 reject / 26 hold; exclude legacy S35 `3679`, leaving the approved nine-model current allowlist. E10L-Pro exact official video remains a follow-up because no safe append endpoint exists. Huayan tests: 46/46; compilation clean. |
| 2026-07-21 | MiR (370) identity/specification pass: retained seven canonical MiR products; rejected two duplicate MiR1000 rows, duplicate MiR500, and invalid “MiR500 Shelf Carrier”; reparented MC250/MC600 to Enabled Robotics 1532 as ER-FLEX/ER-MAX. Applied exact specs, lifecycle, family/taxonomy/sources, and corrected videos. No approval recommendation: Teradyne permits only noncommercial informational use and Enabled requires written image-copy approval. Four MiR records are imageless; five existing pending galleries require authenticated detachment. |
| 2026-07-21 | Stakeholder approved CTRL Robotics (782); API verified **1 published / 5 rejected / 0 pending** and moved the company to Cleared. |
| 2026-07-21 | CTRL Robotics (782) ownership cleanup: retained only current CTRL-branded **Box 5086**, enriched it from the exact current offering page, and installed one exact 1200×858 owned-CDN hero. Reparented original PuduBot 5085 to Pudu Robotics and REEMAN WBOT11B/FBOT13B chassis 5083/5082 to REEMAN with exclusive OEM ownership. Rejected exact duplicate R1D1/KettyBot/BellaBot/LuckiBot rows and unverifiable dead Kiki. CTRL moderation: **1 publish / 0 hold**; tests **3/3**. |
| 2026-07-21 | Stakeholder approved Bluesword (997); API verified **9 published / 8 rejected / 0 pending** and moved it to Cleared. |
| 2026-07-21 | **Correction:** CADENAS/Yamaha terms do not permit public redistribution of the exact CAD/PDF renders. Reclassified seven pending Yamaha F/B rows as blocked and identified restricted catalog-derived heroes on published XBOT/JGX16-H/JGX16-V. Automated removal could not proceed: the configured AWS identity lacks `s3:DeleteObject`, and the admin photo-delete endpoint returned 403. No record was changed by the failed cleanup attempts. |
| 2026-07-21 | Bluesword (997) full catalog curation: retained nine named robot products and rejected eight conveyor/category/family/phantom shells. Replaced every keeper gallery with one exact official hero (654–2786 px), removed placeholder/third-party media, applied exact PDP/brochure specs, current names, family/taxonomy/sources, and exact or relevant official videos. Four-Way Shuttle's conflicting 1.5/1.6 t standard payload remains untyped. Distinct owned-CDN heroes **9/9**; moderation **9 publish / 0 hold**; tests **3/3**. |
| 2026-07-21 | Extended Yamaha LCMR200 media research to Yamaha's official configurable CAD catalog on CADENAS. Replaced banners for seven pending F/B modules (**3325, 3326, 4386, 4387, 4388, 4389, 4391**) with visually verified exact length/cable-entry renders; all seven CDN bodies are valid and hashes are distinct. B5 `4390` was already published and was not overwritten. Yamaha now has **8/10** pending rows ready; only JGX16-H/V remain held for missing features. |
| 2026-07-21 | Stakeholder approved Balyo (242); API verified all six canonical records published, then legacy published duplicates TUGGY 372 + REACHY 373 were retired. Final state: **6 published / 11 rejected / 0 pending**. |
| 2026-07-21 | Balyo (242) full catalog curation: collapsed 15 pending rows into six canonical current robots (VEENY, REACHY, LOWY CB, LOWY, LOWY HD, TUGGY), rejected nine exact duplicates, and replaced all keeper galleries with one exact current OEM cover each. Corrected LOWY HD's wrong LOWY application image and removed TUGGY's LOWY CB photo plus wrong REACHY/stacker videos. Applied exact PDP specs/family/taxonomy/sources and exact official videos or relevant official family overviews; distinct owned-CDN heroes **6/6** at 1200×900; moderation **6 publish / 0 hold**; tests **4/4**. Legacy published TUGGY 372 and REACHY 373 remain for post-approval retirement. |
| 2026-07-21 | Stakeholder approved Dobot (1161); API verified **13 published / 0 pending** and moved the company to Cleared. |
| 2026-07-21 | Dobot (1161) blocker cleared: enriched CR30H (4242) from the exact OEM PDP and launch release, replaced the blank media slot with a visually verified/cropped 1108×1200 OEM Standard Edition hero, and applied typed 30 kg payload / 1800 mm reach / 98.5 kg / ±0.05 mm / 6 DOF. Owned CDN verified; moderation dry-run **13 publish / 0 hold**; tests **2/2**. |
| 2026-07-21 | Yamaha LCMR200 image repair: replaced the shared text-heavy banner on XBOT 4385, JGX16-H 4392, and JGX16-V 4393 with three distinct exact clean renders extracted from Yamaha’s official catalog; CDN and hashes verified, one primary photo each, status preserved. Eight F/B module variants remain held because every model-linked Yamaha PDF reuses one generic render. |
| 2026-07-21 | Stakeholder approved 6 of Yamaha’s 17 unique merged rows and left 11 LCMR200 records in To Review because their primary images are text-heavy promotional/specification assets. Added a hard hero-image rule: the robot must dominate; promo banners, spec/design sheets, diagrams, and text-heavy cards cannot be primary images. Live API verified **45 published / 22 rejected / 11 pending**. |
| 2026-07-21 | Yamaha company 1477 was merged into canonical 1484 and removed by stakeholder. Audited all 39 merged To Review rows against 39 published Yamaha records; rejected **22 exact model-token duplicates** with coded reason `duplicate`. Preserved 17 unique pending rows: **14 must-clear pass** left for approval and **3 held** for missing features (4393, 4392, 4377). |
| 2026-07-21 | Stakeholder approved Gurki (974), Intamsys (1073), Intuitive Surgical (52), 6 River Systems (1373), Auris Health (1511), and Infinium Robotics (783); API verified **0 pending** for all. inVia audit found published **2977 inVia Picker robot** duplicates legacy published **272 inVia Picker**; keep 2977 (fully enriched), reject 272. |
| 2026-07-21 | Geek+ (1398) full catalog audit: 14 exact models fully enriched, 38 duplicate/solution/configuration/alias shells rejected, 3 exact-media holds. Typed-spec coverage across 17 retained: payload 16, weight 13, speed 16, dimensions 14–16, runtime 13, battery 15. Exact approval allowlist recorded under Partial; CDN/pixel verification 14/14. |
| 2026-07-21 | Yamaha (1484) media follow-up: replaced YK1200XG's text-heavy banner with Yamaha's clean 1000×618 launch-release product photo; rebuilt the only available exact YK400/610/710XEC OEM renders as 1200 px card assets; retained YK510XEC's suitable 1000 px release photo. Distinct hashes and owned CDN HTTP verification **5/5**; moderation dry-run **5 publish / 0 hold**; tests **4/4**. |
| 2026-07-21 | Full curated enrichment complete for Yamaha remaining 5, Gurki 8, inVia Picker, and 6 River Chuck; exact model specs/media/videos or documented dead searches. Yamaha video cleanup replaced sibling/off-product clips with one official YK-X family overview using `replace_videos=True` + `patch_existing=True`; tests 2/2 pass. Rejected inVia PickerWall (`non_robot_workflow`) and Plus One PickOne (`non_robot_software`); Plus One cleared. |
| 2026-07-22 | Hyundai (49) held-set clearance: rejected HH050 alias **3719** + industry/7 packages **3722–3726**; fixed **3709**→HC3303B Series, **3710/3711** distinct HDC heroes, **3729** LABOT + **3730** Robot Barista notice heroes. CDN/hash verified 5/5; HDC25≠HDC35. Approve allowlist pending **3709, 3710, 3711, 3729, 3730**. Script: `fix_hyundai_held_robots.py`. |
| 2026-07-21 | Curated full passes applied to Hyundai (49), DELTA (1206), and Mujin (810). Clean subsets: **7 / 9 / 8** respectively, with exact approval allowlists under Partial. Rejected 5 Hyundai duplicate shells + 1 Mujin language duplicate. Held exact-media collisions, aliases, package/category shells, and documented PDP/datasheet dead searches instead of substituting sibling data. |
| 2026-07-21 | Repaired Briggo/Costa (406) and Formic (1450) media from current model-specific OEM assets. Content-hash validation found 9/9 distinct images; copy-media succeeded; owned CDN verification is 1/1 Briggo and 8/8 Formic. Fixed Smart Café use taxonomy to `dispensing`. Moderation dry-run: **9/9 publish**, 0 hold. |
| 2026-07-21 | Full curated enrichment complete for Intamsys (1073), Intuitive Surgical (52), Auris Health (1511), and Infinium Robotics (783): OEM PDP/docs/FDA/whitepapers, typed specs where available, exact-model media + CDN verification, videos, sources, and explicit dead searches. Moderation dry-run: **10/10 publish**, 0 hold. Moved to Approve tonight. |
| 2026-07-21 | **Correction:** retracted the overnight “soft-enriched → ready” recommendation. Gate-filling country/uses/family/availability is not full enrichment. Moved Geek+, Yamaha, Hyundai, DELTA, Mujin, Gurki, Intamsys, Intuitive, inVia, 6 River, Auris 1511, Infinium, and Plus One back to Needs cleanup pending curated OEM PDP/datasheet/spec/media passes. |
| 2026-07-21 | Stakeholder approved Freefly (1452), Dusty (1510), Flytrex (1448), Liquid Robotics (429), Asensus (328), Harvest Automation (1502), Diversey/TASKI (367), Auris/J&J (383), Globus (432), and Shift (856). API verified all at **0 pending**; moved to Cleared. |
| 2026-07-20 | **Needs cleanup overnight:** rejected ACY pending EOAT ×55 + DINGS Gripper + AGV Network; soft-enriched Geek+/Yamaha/Hyundai/DELTA/Mujin/Gurki/Intamsys/Intuitive/inVia/6 River/Auris/Infinium/Plus One — families + uses + country arrays + Available; Geek+ CDN **55/55**. Report: `docs/reports/needs-cleanup-morning-report.md`. Script: `overnight_needs_cleanup_enrich.py`. |
| 2026-07-20 | YASKAWA / Motoman (772): full soft enrich ×75 — Japan; Available; families `yaskawa:{series}`; Spec Finder payload+reach; datasheet weight/repeatability (~67); Motoman-prefixed names cleaned; nav-junk features wiped; OEM application purposes. **must_clear_pass** ×75. Script: `discover_yaskawa_robots.py`. → Big fleets. |
| 2026-07-20 | Lumos Robotics (70) stakeholder approved → Cleared (5 published / 0 pending; LUD + LUS 2 + MOS 2 + NIX S3 + Touch R1). |
| 2026-07-20 | Lumos Robotics (70): full soft enrich ×5 (LUD / LUS 2 / MOS 2 / NIX S3 / Touch R1) — China; Available; families `lumos:lud|lus|mos|nix|touch`; OEM PDP typed specs; LUS 2 hero → OEM front.webp. **must_clear_pass** ×5; CDN 5/5. Script: `discover_lumos_robots.py`. → Approve tonight. |
| 2026-07-20 | Jaten (1461): restored + published **5185** SDM300-339-MGD + **5190** MN30-164 (hero swap → product render); kept 5× `*-335-MG0` phantoms rejected. Cleared (9 published / 0 pending). Scripts: `restore_jaten_5185_5190.py`, `_jaten_force_restore.py`. |
| 2026-07-20 | VisionNav Robotics (807) stakeholder approved all → Cleared (16 published / 0 pending; VNE/VNK/VNP/VNQ/VNR/VNSL/VNST/VNT). |
| 2026-07-20 | ACY Automation (1369): stakeholder flagged EOAT catalog is **not robots** (grippers/QC/cups/clamps/cylinders). Moved Big fleets → Needs cleanup. Reject pending as `non_robot` (Flexiv Grav precedent). **35 published** still need reject-or-keep decision. |
| 2026-07-20 | Bluefin (160) stakeholder approved 3 → Cleared; overnight US discover started (`overnight_us_discover.py` → `docs/reports/us-overnight-morning-report.md`). |
| 2026-07-20 | Bluefin (160): soft-filled published Bluefin-21 EN; rejected BF-21 dupe 5044; enriched Bluefin-9/12/HAUV. **must_clear_pass** ×3. Script: `discover_bluefin_robots.py`. → Approve tonight. |
| 2026-07-20 | SMP Robotics (212) stakeholder approved 13 → Cleared; soft-filled published Argus S5.2 + Bird Control. |
| 2026-07-20 | SMP Robotics (212): soft-enriched 13 pending S-series + published Argus S5.2 / Bird Control — families `smp:s5-argus|s2|s3|s4|s6|s7|s8|s11`; platform 4–6 km/h / 110 kg / 1420×780×1750 mm. **must_clear_pass** ×13. Script: `discover_smp_robots.py`. → Approve tonight. |
| 2026-07-20 | Ekso Bionics (147) stakeholder approved 5 → Cleared; rejected Indego dupe 436 + family shell 179. |
| 2026-07-20 | Ekso Bionics (147): enriched EksoNR / Indego Personal / EVO (Available) + EksoGT / EksoVest (Discontinued); rejected Indego dupe 436 + NR/GT family shell 179. **must_clear_pass** ×5. Scripts: `discover_ekso_robots.py`, `_fix_ekso_finish.py`. → Approve tonight. |
| 2026-07-20 | Accuray (1378) stakeholder approved → Cleared; re-rejected CyberKnife® S7/M6 trademark shells (1477/1478) that were bulk-published alongside keepers 222/368. |
| 2026-07-20 | Accuray (1378): enriched Radixact + TomoTherapy Hi-Art/HD/HDA; rejected CyberKnife® S7/M6 dupes of published 222/368; soft-filled published CyberKnife EN/URL/sources. **must_clear_pass** ×4. Script: `discover_accuray_robots.py`. → Approve tonight. |
| 2026-07-20 | Dephy (814) stakeholder approved Sidekick Starter Pack → Cleared (2 published / 0 pending). |
| 2026-07-20 | Dephy (814): soft-patched **Sidekick Starter Pack (5088)** — US; Available; family `dephy:sidekick` (aligned published 354); $4,500 kit. **must_clear_pass** ×1. Script: `discover_dephy_robots.py`. → Approve tonight. |
| 2026-07-20 | Blue River (423) stakeholder approved → Cleared (3 published / 0 pending). |
| 2026-07-20 | Cobalt (213): EN soft-patched published **Cobalt Security Robot (399)**; rejected pending CJK dupe **1659** → Cleared. Blue River (423): soft-patched Ultimate/See & Spray/LettuceBot → Approve tonight. |
| 2026-07-20 | XRobotics (114) + Foundation (851) stakeholder approved → Cleared. |
| 2026-07-20 | XRobotics (114) + Foundation (851): soft-enriched **xPizza Cube (5289)** + **Phantom (2883)** — US; Available; families; OEM typed specs; logo primaries → OEM product heroes. **must_clear_pass** ×1 each. Script: `discover_xrobotics_foundation.py`. → Approve tonight. |
| 2026-07-20 | Piaggio Fast Forward (236) stakeholder approved → Cleared (3 published / 0 pending; Grogu family linked). |
| 2026-07-20 | Piaggio Fast Forward (236): soft-patched **gitamini (3767)** + **gita plus (3765)** — US; Available; family `piaggio:gita`; OEM typed specs; purpose≠desc; scrubbed Humanoid/Drone tags. **must_clear_pass** ×2. Script: `discover_piaggio_robots.py`. → Approve tonight. |
| 2026-07-20 | Bear Robotics (198) stakeholder approved → Cleared (11 published / 0 pending). |
| 2026-07-20 | Bear Robotics (198): soft-patched all **10** pending Servi/Carti — US; Available; families `bear:servi|carti|carti-lp|servi-clean`; typed payloads on Carti 100–1500 + Servi Plus ~40 kg. **must_clear_pass** ×10. Script: `discover_bear_robots.py`. → Approve tonight. |
| 2026-07-20 | ACY Automation (1369): full soft enrich on all **90** pending EOAT SKUs — 24 `acy:*` families, purpose lines, `/en/`→live root URLs, Available, TW country; media fix promoted gallery/CDN heroes (truncated OpenCart primaries) — **90/90 owned CDN HTTP 200**. **must_clear_pass** ×90. Was wrongly marked cleared (502 audit). → Big fleets ready for bulk approve. Scripts: `fix_acy_enrich.py`, `fix_acy_media.py`. |
| 2026-07-20 | Epson: duplicate company **Epson Robots (1445)** merged into **Epson / Seiko Epson (400)** — 51 published / 0 pending; 1445 company 404. Removed 1445 from blocked. |
| 2026-07-20 | IIT (50) stakeholder approved → Cleared (11 published / 0 pending). |
| 2026-07-20 | ACY (1369) gallery fix: removed variant-thumb duplicate photo rows (w320/640/960 imported as separate photos); angular DA drawings → OEM AG*D/O product photos on CDN. Script: `fix_acy_gallery_cleanup.py`. |
| 2026-07-20 | iRobot (342) stakeholder approved remaining To Review → Cleared (31 published / 0 pending; 17 rejected). j9 (2031) published alongside j9+. |
| 2026-07-20 | iRobot (342): fixed verify chips on 5 pending — Combo i5 wrong 415X copy+hero → OEM i517020; 105/105X OEM catalog heroes; i4 purpose; j9 desc cleared + IMAGE TO-DO (reject dupe of j9+ 2029 in UI). |
| 2026-07-20 | FarmBot (34) stakeholder approved Genesis + Express → Cleared (4 published / 0 pending). |
| 2026-07-20 | FarmBot (34): Genesis v1.8 + XL + Express soft-patched; fixed broken Genesis heroes → Approve tonight (4 pending). |
| 2026-07-20 | Aethon (7) stakeholder approved T3/T3 XL/Zena RX/Zena → Cleared (4 published); expanded notes on 10 rejected; content-queue API now returns `notes`. |
| 2026-07-20 | Aethon (7): T3/T3 XL/Zena RX/Zena enriched; rejected 10 dupes/phantoms/wrong-media TUGs → Approve tonight (4 pending). |
| 2026-07-20 | Gecko Robotics (806) stakeholder approved TOKA 4 + Flex → Cleared (3 published / 0 pending). |
| 2026-07-20 | SIASUN (1424) stakeholder bulk approved → Cleared (82 published / 0 pending; 64 rejected). |
| 2026-07-20 | Locus Robotics (69) stakeholder approved Origin/Vector/Array → Cleared (4 published / 0 pending). |
| 2026-07-20 | Seegrid (209) stakeholder approved Lift RS1/CR1/EL1 + Tow Tractor S7 → Cleared (5 published / 0 pending; 3 same-URL dupes rejected). |
| 2026-07-20 | Gecko Robotics (806): photo hold — TOKA 4 → DVIDS 7463870 robot-only; Flex text marketing demoted; 2 pending → Approve. |
| 2026-07-20 | Gecko Robotics (806): TOKA 3 photo + TOKA 4 logo→Navy still; Flex OEM press; US/family/Available → Approve tonight (3 pending). |
| 2026-07-20 | Locus Robotics (69) stakeholder approved Array/Origin/Vector → Cleared (4 published / 0 pending); LocusBot taxonomy fixed. |
| 2026-07-20 | Seegrid (209): soft-patched Lift RS1/CR1 + Tow Tractor S7; discovered Lift EL1 (5558); rejected 3 same-URL dupes → Approve tonight (4 pending). |
| 2026-07-20 | Boston Dynamics (18) stakeholder approved Stretch (1760) → Cleared (5 published / 0 pending); Atlas + Spot with Arm rejected. |
| 2026-07-20 | Boston Dynamics (18): soft-patched US/family/Available + OEM specs on Stretch/Atlas/Spot with Arm → Approve tonight (3 pending). |
| 2026-07-20 | EFORT (1479) stakeholder bulk approved → Cleared (67 published / 0 pending). |
| 2026-07-20 | EFORT (1479): company country China + soft patch (purpose/family/typed specs/clean uses on 67 pending) → ready for bulk approve; soft: no_year/no_price/no_video, 5 cobots few_photos (OEM 1 image). |
| 2026-07-20 | Trossen Robotics (307) stakeholder approved WidowX AI (5273) → Cleared (10 published / 0 pending). |
| 2026-07-20 | Trossen Robotics (307): WidowX AI (5273) primary CDN 403 fixed (OEM arm-from-box + gallery + payload 1.5 kg / reach 700 mm); 8 others already published → partial 1 pending. |
| 2026-07-20 | Trossen Robotics (307): soft-patched family/US/typed Interbotix specs on 9 pending → Approve tonight. |
| 2026-07-20 | AMP Robotics (259) stakeholder approved Delta + Delta Compact → Cleared (2 published / 0 pending; 8 rejected). |
| 2026-07-20 | AMP Robotics (259): enriched Delta (1472) + Delta Compact (1474); rejected 8 software/pneumatic/facility/dupe rows → Approve tonight (2 pending). |
| 2026-07-20 | Figure AI (36) stakeholder approved Figure 03 → Cleared (5 published / 0 pending). |
| 2026-07-20 | Figure AI (36): Figure 03 enriched (OEM specs + F.03 hero; replaced F.02 mislabel) → Approve tonight (1 pending). |
| 2026-07-20 | Carbon Robotics (266) stakeholder approved LaserWeeder G2 200/300/400/600/1200 → Cleared (7 published / 0 pending). |
| 2026-07-20 | Carbon Robotics (266): LaserWeeder G2 200/300/400/600/1200 enriched with OEM Unit Specs → Approve tonight (5 pending). |
| 2026-07-20 | Stryker (350) stakeholder approved Mako 4 + Total Knee/Hip/Partial Knee → Cleared (5 published / 0 pending). |
| 2026-07-20 | Stryker (350): Mako 4 + Total Knee/Hip/Partial Knee enriched; shared hero hash fixed → Approve tonight (4 pending). |
| 2026-07-20 | Anduril (284) stakeholder approved Fury/Ghost/Altius/Barracuda/Dive-XL → Cleared (5 published / 0 pending; Lattice+Menace+Barracuda-100/250 rejected). |
| 2026-07-20 | Anduril (284): Fury/Ghost/Altius/Barracuda/Dive-XL enriched; Lattice Mesh + Menace-X + Barracuda-100/250 rejected → Approve tonight (5 pending). |
| 2026-07-20 | Diligent Robotics (29) stakeholder approved Moxi + Moxi 2.0 → Cleared (2 published / 0 pending). |
| 2026-07-20 | Diligent Robotics (29): Moxi + Moxi 2.0 enriched; zh overlay cleared via translation-sync → Approve tonight (2 pending). |
| 2026-07-20 | Flexiv (315) stakeholder approved Rizon 4/10 (+F/T) + Moonlight → Cleared (5 published / 0 pending; Grav EOAT rejected). |
| 2026-07-20 | Flexiv (315): Rizon 4/10 (+F/T) + Moonlight enriched; Grav EOAT rejected; Franka-like heroes replaced → Approve tonight (5 pending). |
| 2026-07-20 | Realbotix (311) stakeholder approved B/M/F → Cleared (3 published / 0 pending; Aria already published). |
| 2026-07-20 | Realbotix (311): B/M/F Series enriched; B bust hero fixed → Approve tonight. |
| 2026-07-20 | Iron Ox (271) stakeholder approved Grover → Cleared (1 published / 0 pending). |
| 2026-07-20 | Iron Ox (271): Grover Discontinued enriched from PR Newswire → Approve tonight. |
| 2026-07-20 | Picnic Works (274) stakeholder approved Pizza Station → Cleared (1 published / 0 pending). |
| 2026-07-20 | Picnic Works (274): Pizza Station (Leo) enriched from OEM fact sheet → Approve tonight. |
| 2026-07-20 | Harvest CROO (268) stakeholder approved B8 Harvester → Cleared (1 published / 0 pending). |
| 2026-07-20 | Harvest CROO (268): B8 Harvester enriched; aerial hero; soft no_specs → Approve tonight. |
| 2026-07-20 | Monarch Tractor (265) stakeholder approved MK-V + Vineyard → Cleared (2 published / 0 pending). |
| 2026-07-20 | FANUC (189): must-clear fixed — JP country on all pending; features ≥40; uses on 1750; IMAGE TO-DO on 4115/4117 → 109 ready / 2 hold. |
| 2026-07-20 | FANUC (189): family_key/name/url + variant/scope filled on 111/111 (`fix_fanuc_family.py`); hard rule 0b added to enrich/discover skills. |
| 2026-07-20 | FANUC (189): purpose rewritten 111/111 from OEM applications (one per line; `fix_fanuc_purpose.py`); skill rule 4b. |
| 2026-07-20 | FANUC (189) stakeholder approved all except imageless M-810iA/45 (4117) → 1 pending. |
| 2026-07-20 | FANUC (189): stakeholder approved most; photo holds — CRX-30iA/L (4119) CRX-30 labeled still; CRX-20iA/L (1754) beauty primary (PTS overlay demoted); M-800iA/60W (4115) labeled still; M-810iA/45 (4117) still IMAGE TO-DO. |
| 2026-07-20 | DAIHEN (1402) stakeholder approved all 24 → Cleared (24 published / 0 pending). |
| 2026-07-20 | DAIHEN (1402): family-7 banner primaries replaced (V80/V100/V130/V350/V400L/V600/V700) → ready for remaining To Review approve. |
| 2026-07-20 | DAIHEN (1402): enriched FD fleet + cleanroom transfer; created FD-V25/V25L/VC4; rejected 3 Almega AX; cropped 16 banner heroes (7 family still banners) → Approve tonight (24 pending). |
| 2026-07-20 | Monarch Tractor (265): MK-V + Vineyard enriched from OEM Spec Sheet → Approve tonight. |
| 2026-07-20 | FarmWise (263) stakeholder approved Vulcan + Titan → Cleared (2 published / 0 pending). |
| 2026-07-20 | FarmWise (263): Vulcan + Titan FT-35 enriched; rejected CJK dupes 459/456; Titan wrong Carbon-like hero replaced → Approve tonight. |
| 2026-07-20 | Covariant (257): RFM-1 rejected (software/foundation model) → Cleared. |
| 2026-07-20 | Glacier Robotics (261) stakeholder approved Robot + Fiber QC → Cleared (2 published / 0 pending). |
| 2026-07-20 | Vecna Robotics (208) stakeholder approved AFL/ATG/CPJ → Cleared (3 published / 0 pending). |
| 2026-07-20 | SIASUN (1424): staged 82 pending heroes to owned CDN (`fix_siasun_cdn_heroes.py`) — en.siasun.com (esp. Chinese filenames) blocked approve copy-media. |
| 2026-07-20 | SIASUN (1424): purpose rewritten on 82 pending (was exact description copies via soft enrich); `fix_siasun_purpose.py`. |
| 2026-07-20 | SIASUN (1424) soft gaps: short desc + availability cleared; specs filled where OEM-cited; rejected 15 more SR-SC/MR EN-404 stubs → **82 pending** (2 soft no_specs). |
| 2026-07-20 | Kawasaki Robotics (773) stakeholder approved all To Review → Cleared (56 published / 0 pending). |
| 2026-07-20 | SIASUN (1424): rejected 49 off-catalog stubs; created 23 live EN SKUs; enriched 6 mobiles; **97/97 must_clear_pass** → Big fleets (bulk approve). |
| 2026-07-20 | Glacier Robotics (261): Robot + Fiber QC enriched; website → endwaste.io → Approve tonight. |
| 2026-07-20 | Vecna Robotics (208) stakeholder cleared AFL/ATG/CPJ; rejected Agile Robots 271 → Cleared. |
| 2026-07-20 | Vecna Robotics (208): AFL/ATG/CPJ enriched; CaseFlow 4518 rejected → Approve tonight. |
| 2026-07-20 | Berkshire Grey (256) stakeholder approved Core/Scoop/Stride/Dispatch → Cleared. |
| 2026-07-20 | Berkshire Grey (256): Core/Scoop/Stride/Dispatch enriched; Dispatch dupe 4044 rejected → Approve tonight. |
| 2026-07-20 | Nuro (199) stakeholder approved R2 → Cleared. |
| 2026-07-20 | Nuro (199): created R2 Discontinued (5526); rejected Lucid×Uber mashup (3764); R3 deferred → Approve tonight. |
| 2026-07-20 | Skydio (137) stakeholder approved X10 + X10D (+ X2 Discontinued) → Cleared. |
| 2026-07-20 | UT Austin RPL (1308): rejected Harmon (method/paper); no OEM robots to create; company country_id=US → Cleared (0 pending). |
| 2026-07-20 | Skydio (137): created X10 (5524) + X10D (5525); enriched X2 (170); rejected R1 (wrong media/off-catalog) → Approve tonight. |
| 2026-07-20 | RightHand Robotics (258) stakeholder approved RightPick 4 → Cleared. |
| 2026-07-19 | ABB Robotics (190) stakeholder approved all To Review → Cleared (141 published / 0 pending). |
| 2026-07-19 | Shield AI (285) stakeholder confirmed Approve = Publish (V-BAT + X-BAT) → Cleared. |
| 2026-07-19 | RightHand Robotics (258): RightPick → RightPick 4 enriched; must_clear_pass → Approve tonight. |
| 2026-07-19 | Knightscope (211) published (K5/K7) → Cleared. |
| 2026-07-19 | Knightscope (211): K5/K7 enriched; K1 Hemisphere rejected → Approve tonight. |
| 2026-07-19 | Shield AI (285) stakeholder approved V-BAT + X-BAT → Cleared. |
| 2026-07-19 | Shield AI (285): created V-BAT (5522) + X-BAT (5523) pending; Hivemind skipped → Approve tonight. |
| 2026-07-19 | Ghost Robotics (168): Vision 60 EN+OEM specs; rejected Q-UGV dupe + Spirit 40 → Cleared (0 pending). |
| 2026-07-19 | JAKA (771) stakeholder approved all To Review cobots → Cleared (13 published / 0 pending). |
| 2026-07-19 | Serve (252) stakeholder approved Gen2 → Cleared (Gen3 already published). |
| 2026-07-19 | Serve Robotics (252): Gen3 enriched (286 published); Gen2 created (5521 pending) → Approve tonight. |
| 2026-07-19 | Exail (428) stakeholder approved all remaining UGVs → Cleared. |
| 2026-07-19 | Mitsubishi (73): also cleared (26 pub); forced gallery PNG/WebP 1280s → Cleared. |
| 2026-07-19 | Epson (400): stakeholder approved 51; variants 0 dead; family hero shares OK → Cleared. |
| 2026-07-19 | Noblelift (1028) + RobCo (239): stakeholder approved; forced missing PNG 1280 variants; hero QA OK → Cleared. |
| 2026-07-19 | Exail (428): replaced blurry Cameleon LG/MK3/Iguana catalog sprites with hi-res OEM datasheet photos; Pending=3. |
| 2026-07-19 | Exail (428): FR country + fixed shared UGV/UlyX heroes → Approve tonight. Rethink (195): OEM dead; Baxter/Sawyer → Wikipedia URLs + discontinued. |
| 2026-07-19 | Stakeholder approved Richtech (131), Apptronik (14), Agility Cassie → Cleared. |
| 2026-07-19 | Unitree (109): last 3 To Review approved/published; A2↔A2-W / A2↔Go2-W hero contamination fixed; 8 robots variant-repaired; moved to Cleared. |
| 2026-07-19 | KUKA (1396): all approved; variant deep-audit 255 robots / 4320 URLs — fixed KR 6 (62) missing primary JPG 640/960/1280; moved to Cleared. |
| 2026-07-19 | Apptronik (14): Apollo EN+specs+country; Apollo 2 narrative cleaned; pending Apollo → Approve tonight. |
| 2026-07-19 | Richtech (131): curated discover + labeled OEM heroes (Titan/MX/F3300); CDN 8/8; 7 must_clear_pass → Approve tonight. |
| 2026-07-19 | KUKA (1396): repaired published+pending AVIF stub heroes; tags on warn targets; Pending=201. |
| 2026-07-19 | Agility Cassie: filled model_name/year/availability/price from Spectrum+CNBC cites. |
| 2026-07-19 | Agility (9): Digit enriched; Cassie (5514) discovered — Approve tonight. |
| 2026-07-19 | Sanctuary AI (92) approved/published; moved to Cleared. |
| 2026-07-19 | Sanctuary AI (92): discovered Phoenix (5513); must_clear_pass → Approve tonight. |
| 2026-07-19 | Realman: created ECO63 Std/Force (5511/5512 pending); RX71→RX71 Standard; Force gaps closed as non-SKUs. |
| 2026-07-19 | Realman (882) published (all 26); moved to Cleared. Variant gap notes recorded. |
| 2026-07-19 | Clarified Approve=Publish for robots. Added moderation playbook + `moderate_robots.py`. |
| 2026-07-19 | Realman (882): multi-angle galleries applied; soft notes updated. |
| 2026-07-19 | Pangolin approved/published; names + video title polish. |
| 2026-07-19 | Initial status from ready-to-approve audit. Pangolin moved to Approve tonight after country fix. |

## Related

- [index.md](index.md)
- [log.md](log.md)
- Audit script: `scripts/research/_audit_ready_to_approve.py`
- Moderation playbook: [playbooks/approve-reject-robots.md](../playbooks/approve-reject-robots.md)
- Moderation script: `scripts/research/moderate_robots.py`
- Content-queue skill: [../../.cursor/skills/content-queue-robot-backfill/SKILL.md](../../.cursor/skills/content-queue-robot-backfill/SKILL.md)
- Moderation skill: [../../.cursor/skills/robot-moderation-queue/SKILL.md](../../.cursor/skills/robot-moderation-queue/SKILL.md)
- Status machine: [../../.cursor/skills/content-moderation-queue/SKILL.md](../../.cursor/skills/content-moderation-queue/SKILL.md)
