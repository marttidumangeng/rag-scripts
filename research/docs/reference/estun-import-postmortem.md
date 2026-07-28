---
type: reference
title: Estun Robotics Import — What Worked and What Failed
status: published
version: 1.0
owner: AI
last_updated: 2026-07-10
tags:
  - research
  - estun
  - postmortem
  - s3
---

# Estun Robotics Import — What Worked and What Failed

Company: **Estun Robotics** — id **220**, slug `estun-robotics`, **61 robots** on prod.

Use this as a pattern library when importing similar catalog OEMs (e.g. UBTECH, other Chinese industrial brands with English subsites).

## What worked

| Approach | Outcome |
|----------|---------|
| English catalog list pages (`en.estun.com/?list_*`) | 54/61 robots matched with correct product URL + hero image |
| Dedicated `estun_english_catalog.py` parser | No Gemini/Apify cost for list-page OEM |
| `apply_estun_english_catalog.py --force-overwrite` | Fixed prod `url` fields that patch import left wrong |
| Local preview (`--local`) before prod | Caught browser CDN 502 vs good server-side copy |
| Server: `replace_media` + versioned S3 keys | Prevented re-copying phone icon from our own CDN |
| Server: allow `*-estun-*.img.addlink.cn` | Estun images redirect to addlink CDN; generic block broke copy |
| `trigger_estun_copy_media.py` after deploy | **61/61** `s3_image` set; avoided bulk-import 502 timeouts |
| Content queue: prefer `s3_image` over hotlink `image` | Admin shows owned media, not broken OEM proxy |

## What failed (and why)

| Mistake | Symptom | Root cause |
|---------|---------|------------|
| `auto robots --refresh-media` after catalog apply | Phone icons, footer assets in staging/prod | Crawl picks site chrome, not catalog heroes |
| Patch import to fix URLs/images | API reported "updated" but prod unchanged | Patch skips non-empty fields |
| Re-import without S3 recopy fix | Same phone icon on CDN | Copy downloaded from `cdn.robotaigeek.com` (old object) |
| Same S3 object key after bad upload | Hard refresh still showed phone | CDN cached stale bytes |
| Blocking all `addlink.cn` hosts | `s3_image` stayed null after recopy | Estun legitimately serves via `img.addlink.cn` |
| `recopy_estun_images.py` with large batches on prod | HTTP **502** gateway timeout | Sync S3 copy per robot in bulk-import request |
| copy-media before csrf/auth fix | HTTP **403** on all 54 robots | Endpoint required Django admin session |
| Gemini/Apify for full Estun catalog | Wasted API spend | English list HTML was sufficient |
| Multiple prod imports "to be sure" | Race with async copy, duplicate load | One force-overwrite + one copy pass is enough |

## Final prod state (2026-07-10)

- **61/61** robots have `s3_image` on CDN with versioned keys.
- **54** had English catalog heroes; **7** retained prior CDN image (no catalog match).
- **8 unmatched** model names documented for manual follow-up (e.g. `iER10-2010-HI`, `iER220-2700`, marketing "AI" entry).

## Verification commands

```powershell
cd scripts/research
python -c "
from load_env import load_research_env; load_research_env()
from api_client import ResearchApiClient
robots = ResearchApiClient().list_robots_for_company(220)
print('s3_image set:', sum(1 for r in robots if r.get('s3_image')), '/', len(robots))
"
```

Spot-check robot **2471** (`iER8-720-MI`): hero ~31 KB, not phone icon.

## Reusable rules for next OEM

1. **Identify catalog lists first** — if heroes exist in HTML, write a parser; skip full enrich.
2. **Never patch-fix wrong prod media** — use force-overwrite + replace_media.
3. **Deploy S3 fixes before expecting prod images to self-heal.**
4. **Prefer copy-media endpoint** over heavy bulk-import recopy on prod (502 risk).
5. **Allowlist OEM CDN redirects** narrowly — do not globally trust `addlink.cn`.
6. **Local preview once** — then single prod import + single copy pass.
7. **Document catalog gaps** — do not re-run Apify for entire fleet when only a few models miss.

## Related

- [../playbooks/catalog-oem-import.md](../playbooks/catalog-oem-import.md)
- [../checklists/prod-manufacturer-import.md](../checklists/prod-manufacturer-import.md)
- [../concepts/catalog-vs-enrich-pipeline.md](../concepts/catalog-vs-enrich-pipeline.md)
