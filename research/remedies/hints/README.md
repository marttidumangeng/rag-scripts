# Remedy hints

**Why this exists:** an audit of the 149 legacy `fix_*.py` scripts (2026-07-30)
found ~76% of them re-implement what the shared remedy registry already does
generically (fill photos/description/tags/specs/family) — just by hand, with
hardcoded per-product URL/image dicts, because automated discovery underperformed
on that particular company (weird nav, attribution landmines, CMS/date image
names, a software product with no physical spec sheet). Full audit:
`fix_scripts_audit.md` (sent to Martti 2026-07-30).

Hints close that gap without a full custom script: hand-verified facts as
**data**, still flowing through the shared remedy engine's merge / no-op /
write / persistence-verify / ledger pipeline (`remedies/engine.py:run_reresearch`).
Only the "how do we get the researched value" step changes — a hint is used
in place of the live web/Gemini research call, nothing else.

## Format

One file per company: `hints/<company_id>.json`. Absent file = no hints, zero
behavior change (the overwhelming majority of companies should never need one).

```json
{
  "<robot_id>": {
    "url": "https://oem.example.com/products/widget/",
    "image": "https://oem.example.com/media/widget-hero.jpg",
    "images": "https://.../1.jpg, https://.../2.jpg",
    "description": "...",
    "purpose": "line one\nline two",
    "features": "...",
    "tags": "Industrial|Autonomous|Service Robot",
    "family_name": "Widget", "family_key": "acme:widget", "variant_label": "Pro",
    "_note": "free text, stripped before use — why this needed a hint"
  }
}
```

- Keys are `StagedRobot` field names (`scripts/research/schema.py`) — anything
  else is silently dropped by `StagedRobot.from_dict`.
- Any key starting with `_` (e.g. `_note`) is stripped before use — put your
  reasoning there, it's for humans reading the file, not the pipeline.
- Only include fields you actually verified. A hint only overrides what it
  names — unset fields fall through to normal automated research on the NEXT
  remedy pass for a different flag, or just stay as current DB state for this
  one. You do not need to fill every StagedRobot field, only the ones the
  remedy you're targeting will read (see `REMEDY_ORDER` / `REMEDY_REGISTRY` in
  `remedies/registry.py` for which flag touches which fields).
- `image`/`images` blank-but-present (`"image": ""`) is a valid, deliberate
  statement — "verified no real product photo exists," not "forgot to fill
  this in." The merge logic treats blank as "don't touch," so an empty string
  here just means that field won't be forced from the hint (same as omitting
  it) — if you need to explicitly CLEAR an existing bad value, that's still
  outside what a hint alone can do; write a one-off script for that.
- The no-op detector still applies: if a hint's fields already match what's in
  prod, the remedy reports `no_op`, not `fixed`. Hints are inputs, not a
  bypass of the pipeline's honesty checks.

## When to write one vs. a full custom script

| Situation | Use |
|---|---|
| Automated discovery keeps missing/mis-scoring a company's product pages, but you can hand-verify the right URLs/images/facts | **Hint** |
| Company needs a new company record, robots reassigned/reparented, fabricated robots rejected | Custom one-off script (irreducible — see `ONE_OFF_SURGERY` bucket in the audit) |
| A field the registry doesn't cover yet (manufacturer_country, release_year, hash-based duplicate-image dedup) | Custom script, or propose extending the registry if it keeps recurring |

## Worked example

`1621.json` (Palladyne AI) — built from `fix_palladyne_1621_robots.py`'s
hand-verified `ROBOT_FIXES` dict as a proof this mechanism reproduces the
same result through the shared path. Only 2 of that script's ~15 robots are
included here (SwarmOS, SwarmStrike) as a worked example, not a full port —
the original script also does company-record edits and an attribution-hold
workflow (IAI partner SKUs) that are out of scope for a remedy hint.
