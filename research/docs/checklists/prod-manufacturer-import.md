---
type: checklist
title: Prod Manufacturer Import Guardrails
status: published
version: 1.0
owner: AI
last_updated: 2026-07-10
tags:
  - research
  - import
  - prod
  - s3
  - checklist
---

# Prod Manufacturer Import Guardrails

Short checklist so catalog OEM imports (e.g. Estun) do not repeat wasted enrich runs, bad S3 copies, or patch imports that leave wrong URLs/images on prod.

## 1. Pick the right pipeline first

- [ ] **Server-rendered product list with hero images?** (e.g. `en.estun.com/?list_13/`) → use a **catalog apply script**, not `auto robots --refresh-media`.
- [ ] **No catalog list pages?** → use `auto pipeline` with plain HTTP first; escalate `--stealth` / `--playwright` only on failure.
- [ ] **Do not run** `auto robots --all-robots --refresh-media` on a company that already has a catalog apply path — it re-scrapes footers and can overwrite good staging.

## 2. Staging quality (before any import)

- [ ] Spot-check **3 robots** in staging JSON: `url` is a **per-model** page (not `/solute/`, `tel:`, or company home).
- [ ] `image` / `images[]` use **`/upload/image/`** or product heroes — not `f-phone.png`, social icons, or shared footer assets.
- [ ] `sources[0].url` matches `url` (catalog product page).
- [ ] Run `python cli.py validate --dir staging/robots/{slug}/`.

## 3. Local preview (recommended)

- [ ] Import locally: `--local` + `replace_media` / force-overwrite (see `apply_estun_english_catalog.py --local`).
- [ ] Run **copy-media** locally so admin does not hotlink OEM CDN (avoids browser proxy 502s).
- [ ] Confirm **one robot** in content queue: correct source URL + robot photo (not phone icon).

## 4. Prod import (once)

- [ ] **Stop** any in-flight `auto robots` / import shell for this company.
- [ ] Use **`--force-overwrite`** (full update), not `--patch`, when fixing wrong URLs/images/sources.
- [ ] Pass **`replace_media=True`** so photos are replaced, not merged with junk.
- [ ] Import **once**; do not chain a second full enrich import after catalog apply.

```powershell
cd scripts/research
python apply_estun_english_catalog.py --apply-import --force-overwrite --created-by-id 1 --batch-size 5
```

(Replace with the manufacturer’s catalog script when one exists.)

## 5. S3 / CDN images (critical)

- [ ] **Deploy** server changes for sync recopy + versioned S3 keys before expecting prod images to fix themselves.
- [ ] **Estun:** `en.estun.com` image URLs redirect to `*-estun-*.img.addlink.cn` — server must allow that OEM CDN host (generic `addlink.cn` stays blocked).
- [ ] Re-copy heroes **once** from external OEM URLs (not from `cdn.robotaigeek.com`):

**Preferred on prod** (avoids bulk-import 502 from sync copy):

```powershell
python trigger_estun_copy_media.py
```

**Alternative** (full staging rows via bulk-import; use smaller `--batch-size` if 502):

```powershell
python recopy_estun_images.py --apply --created-by-id 1 --batch-size 5
```

- [ ] Verify **one prod robot** via API:
  - `url` = OEM product page
  - `image` / `s3_image` = new CDN path (versioned key) or valid hero
  - Photo is not a footer/phone asset

## 6. What not to do

| Mistake | Why it wastes resources |
|---------|-------------------------|
| Patch import to fix bad URL/image | Patch skips non-empty prod fields |
| Re-import without S3 recopy fix | Copy may download from **our CDN** (old phone icon) |
| Same S3 object key after bad upload | CDN cache serves stale bytes |
| Background `auto robots` after catalog apply | Overwrites staging; Apify/Gemini cost |
| Multiple prod imports “to be sure” | Duplicate API load; race with async copy |
| Gemini/Apify for Estun-style list pages | English catalog parse is enough |

## 7. Expected gaps

- [ ] Document robots **not** on OEM English (or local) catalog — do not force Apify search for all 61 if only 8 are missing.
- [ ] Flag non-physical products (e.g. marketing “AI robot” entries) for reject/skip in admin.

## 8. Sign-off

- [ ] User reviewed **≥1 robot** on prod content queue after recopy.
- [ ] `state mark --type company --id {id}` only after sign-off.

## Related

- [../index.md](../index.md)
- [../../AUTOMATION.md](../../AUTOMATION.md)
- Estun scripts: `apply_estun_english_catalog.py`, `recopy_estun_images.py`, `trigger_estun_copy_media.py`, `estun_english_catalog.py`
- Playbook: [../playbooks/catalog-oem-import.md](../playbooks/catalog-oem-import.md)
- Postmortem: [../reference/estun-import-postmortem.md](../reference/estun-import-postmortem.md)
