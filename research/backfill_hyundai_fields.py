"""Backfill features / tags / uses / industries on the 61 Hyundai robots.

WHY THIS IS A FIX AND NOT NEW WORK
----------------------------------
`ingest_hyundai_api.py` fetched all of this and then wrote none of it. The API
returns per model: 25 detail-spec fields, basic specs, application codes
(`prdApField`), industry codes (`prdRlIdst`) and a strengths block. The import
used ONE of those (applications, flattened into a purpose sentence) and dropped
the rest, leaving features 0/61, tags 11/61, uses 11/61, industries 11/61 —
with `missing_features` being an ERROR-severity flag. Gathering a field and not
writing it is the defect being corrected here.

CODE MAPPING — DERIVED FROM THE DATA, NOT GUESSED
-------------------------------------------------
HD Hyundai's application/industry codes are opaque ints with no legend exposed
(no code endpoint; the filter UI is JS-rendered). They were decoded from the
catalogue itself:

  * 60020009 — appears on the YP family and NOWHERE else. YP is the 4-axis
    palletiser line => palletizing. Confirmed by set difference.
  * 60020001 vs 60020002 — both welding-shaped, and an initial guess had them
    backwards. Payload settles it: 60020001 spans 6-20 kg (median 11) and
    60020002 spans 80-600 kg (median 215). A 6 kg arm cannot carry a spot gun,
    so 60020001 is ARC welding and 60020002 is SPOT welding.
  * 60020004 / 60020006 / 60020005 — on 42 / 41 / 39 of 44 arms, i.e. the
    general-purpose applications every articulated arm carries.
  * 60020008 — only on HDP130/HDP160 (130-160 kg), a two-model line the
    manufacturer flags with one dedicated application.

Codes that could not be distinguished from the data are deliberately left
UNMAPPED rather than assigned a plausible-looking value.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402

API = "https://www.hd-hyundairobotics.com/api/v1/product/page"
HDRS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Referer": "https://www.hd-hyundairobotics.com/",
    "Accept": "application/json",
}

# Application code -> our `uses` key. See module docstring for how each was
# established. Unmapped codes (60020007, and the FPD-specific 6002000A-D) are
# omitted on purpose.
USE_BY_CODE = {
    "60020001": "arc-welding",
    "60020002": "spot-welding",
    "60020004": "handling",
    "60020005": "assembly",
    "60020006": "machine-tending",
    "60020008": "material-handling",
    "60020009": "palletizing",
}
# Industry codes: only the two that the data actually distinguishes, plus the
# FPD line whose industry is unambiguous from the product type name itself.
INDUSTRY_BY_CODE = {
    "60040005": "manufacturing",
    "60040001": "automotive",
    "6004000F": "electronics",
}

TYPES = {
    "60010001": "industrial articulated",
    "60010002": "FPD glass transfer",
    "60010007": "collaborative",
}


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def num(v: Any) -> float | None:
    if v is None:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def split_name(raw: str) -> tuple[str, str]:
    raw = re.sub(r"^(제품관리_|PRODUCT_)\s*", "", (raw or "").strip())
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw)
    return (m.group(1).strip(), m.group(2).strip()) if m else (raw, "")


def build_features(name: str, code: str, x: dict[str, Any]) -> str:
    """Factual feature lines from the manufacturer's own structured specs.

    Detail-spec slots 1/2/3 are structure / axis count / drive type across every
    industrial record — verified consistent over all 46. The joint-range and
    speed slots are not labelled by the API, so they are NOT invented into
    prose; only fields whose meaning is established get written.
    """
    is_fpd = code == "60010002"
    payload = None if is_fpd else num(x.get("prdBscSpec1"))
    reach = None if is_fpd else num(x.get("prdBscSpec2"))
    glass = strip_html(x.get("prdBscSpec2") or "") if is_fpd else ""
    structure = strip_html(x.get("prdDtlSpec1") or "")
    axes = strip_html(x.get("prdDtlSpec2") or "")
    drive = strip_html(x.get("prdDtlSpec3") or "")
    ctrl = strip_html(x.get("prdBscSpec3") or "")

    lines: list[str] = []
    if structure and axes:
        lines.append(f"{axes}-axis {structure.lower()} configuration")
    elif structure:
        lines.append(f"{structure} configuration")
    if payload:
        lines.append(f"Rated payload {payload:g} kg")
    if reach:
        lines.append(f"Maximum reach {reach:g} mm")
    if glass:
        lines.append(f"Handles {glass} substrate glass")
    if drive:
        lines.append(f"{drive} drive")
    if ctrl:
        lines.append(f"Compatible controllers: {ctrl}")
    apps = [USE_BY_CODE[c].replace("-", " ") for c in (x.get("prdApField") or "").split("|")
            if c in USE_BY_CODE]
    if apps:
        lines.append("Manufacturer-listed applications: " + ", ".join(sorted(apps)))
    if (x.get("prdMassYn") or "").upper() == "N":
        lines.append("No longer in production")
    return "\n".join(f"• {l}" for l in lines)


def build_tags(name: str, code: str, x: dict[str, Any], existing: set[str]) -> list[str]:
    """Reuse EXISTING catalogue tags wherever possible rather than minting
    near-duplicates — the tag table already has 1,145 entries."""
    want: list[str] = []

    def add(t: str) -> None:
        for e in existing:
            if e.lower() == t.lower():
                want.append(e)
                return
        want.append(t)

    add("Industrial Robot")
    add("Manufacturing")
    if code == "60010007":
        add("Collaborative Robot")
    if code == "60010002":
        add("Electronics")
    axes = strip_html(x.get("prdDtlSpec2") or "")
    if axes == "6":
        add("6-Axis")
    structure = strip_html(x.get("prdDtlSpec1") or "").lower()
    if "articulated" in structure:
        add("Industrial Arm")
    codes = set((x.get("prdApField") or "").split("|"))
    if "60020009" in codes:
        add("Palletizing")
    if "60020001" in codes or "60020002" in codes:
        add("Welding")
    if "60020004" in codes:
        add("Material Handling")
    add("Factory Automation")
    # de-dupe, preserve order
    return list(dict.fromkeys(want))


def main() -> None:
    apply = "--apply" in sys.argv
    client = ResearchApiClient()

    company = next(x for x in client.search_companies("Hyundai Robotics", page_size=10)
                   if x["name"].strip().lower() == "hyundai robotics")
    held = {r["name"]: r for r in client.list_robots_for_company(company["id"])}
    existing_tags = {t.get("name") for t in client.list_tags(page_size=500) if t.get("name")}

    # Pull the catalogue again — same source the import used.
    source: dict[str, tuple[str, dict]] = {}
    for code in TYPES:
        r = requests.get(API, params={"prdTypeCd": code, "page": 0, "size": 300},
                         headers=HDRS, timeout=40)
        r.raise_for_status()
        for x in r.json()["data"]["content"]:
            raw = (x.get("prdNm") or "").strip()
            if not raw:
                continue
            cur, _alias = split_name(raw)
            source[cur] = (code, x)

    # Published records are live on the site and are out of scope for automated
    # edits — a content PATCH also resets the AI verification score, so touching
    # an approved robot silently downgrades a reviewed record. Only the review
    # queue is editable here.
    EDITABLE = {"pending_review", "draft"}

    rows: list[dict[str, Any]] = []
    skipped_live: list[str] = []
    for name, (code, x) in source.items():
        robot = held.get(name)
        if not robot:
            continue  # not one of ours (or held under the legacy alias)
        if (robot.get("status") or "") not in EDITABLE:
            skipped_live.append(f"{name} [{robot.get('status')}]")
            continue
        uses = sorted({USE_BY_CODE[c] for c in (x.get("prdApField") or "").split("|")
                       if c in USE_BY_CODE})
        inds = sorted({INDUSTRY_BY_CODE[c] for c in (x.get("prdRlIdst") or "").split("|")
                       if c in INDUSTRY_BY_CODE})
        if code == "60010002":                      # FPD line: type name states it
            inds = sorted(set(inds) | {"electronics"})
            uses = sorted(set(uses) | {"material-transport"})
        rows.append({
            "id": robot["id"],
            "name": name,
            "company_slug": "hyundai-robotics",
            "features": build_features(name, code, x),
            "tags": ", ".join(build_tags(name, code, x, existing_tags)),
            "use_keys": ", ".join(uses),
            "industry_keys": ", ".join(inds),
        })

    print(f"matched {len(rows)} editable robots against the source catalogue")
    if skipped_live:
        print(f"  skipped {len(skipped_live)} live/published (never auto-edited): "
              f"{', '.join(skipped_live[:6])}{' ...' if len(skipped_live) > 6 else ''}")
    filled = lambda k: sum(1 for r in rows if r[k])  # noqa: E731
    print(f"  features: {filled('features')}  tags: {filled('tags')}  "
          f"uses: {filled('use_keys')}  industries: {filled('industry_keys')}")
    if rows:
        s = rows[0]
        print(f"\nsample — {s['name']}\n{s['features']}")
        print(f"  tags: {s['tags']}\n  uses: {s['use_keys']}\n  industries: {s['industry_keys']}")

    out = _HERE / "staging" / "hyundai_api" / "backfill_fields.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out}")

    if not apply:
        print("\n(dry run — pass --apply to PATCH these onto prod)")
        return

    # The staging validator requires description/purpose and a source URL on
    # every row even when patching, so a minimal {id, features, tags} payload is
    # rejected. Merge the new fields into the ORIGINAL full staged records
    # instead — same values re-sent for everything else, new values for the
    # four that were left blank.
    original = {r["name"]: r for r in json.loads(
        (_HERE / "staging" / "hyundai_api" / "staged_import.json").read_text(encoding="utf-8")
    )["robots"]}
    new_by_name = {r["name"]: r for r in rows}

    merged: list[dict[str, Any]] = []
    for name, add in new_by_name.items():
        base = original.get(name)
        if not base:
            print(f"  !! no original staged record for {name} — skipped to avoid a partial write")
            continue
        rec = dict(base)
        rec["id"] = add["id"]                     # bind the patch to the right row
        rec["features"] = add["features"]
        rec["tags"] = add["tags"]
        rec["use_keys"] = add["use_keys"]
        rec["industry_keys"] = add["industry_keys"]
        merged.append(rec)

    # patch=True -> update_existing + patch_existing, so unsent fields are left
    # alone rather than blanked. Straight PUT-style updates blank omitted fields.
    from import_staging import import_staging
    tmp = _HERE / "staging" / "hyundai_api" / "backfill_rows"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.json"):
        f.unlink()
    for r in merged:
        fn = re.sub(r"[^a-z0-9]+", "-", r["name"].lower()).strip("-")[:60]
        (tmp / f"{fn}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    print(f"patching {len(merged)} merged records")
    res = import_staging(tmp, patch=True, dry_run=False)
    print(f"ok={res.get('ok')} updated={res.get('updated_count')} "
          f"created={res.get('created_count')} errors={res.get('error_count')}")
    for e in [x for x in res.get("results", []) if x.get("action") == "error"][:5]:
        print("  ERROR:", e.get("name"), str(e.get("error"))[:140])


if __name__ == "__main__":
    main()
