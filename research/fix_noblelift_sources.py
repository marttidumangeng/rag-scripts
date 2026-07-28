"""Source-extension + spec/availability gap-fill for 6 Noblelift (1028) robots.

Companion to fix_noblelift_robots.py. That script seeds heroes/features/videos/tags
from the OEM ASPX PDPs. THIS script does the "extend sources" pass the coordinator
asked for on the 6 most-gapped pending_review robots:

  * Generic spec-table parse of the noblelift.com PDP → typed columns that actually
    persist (weight_kg, length_mm/width_mm/height_mm + text, speed, voltage,
    battery_capacity). payload has no Robot column (server packs it into notes).
  * availability_status_key='available' (commercially sold; cited by OEM PDP).
  * Credible third-party sources (official Noblelift regional subsidiaries, spec
    databases, trade press, distributor datasheets) added ALONGSIDE the OEM PDP +
    nobleliftgroup.com corporate site into sources/information_source_urls so the
    server upserts RobotInformationSource and stamps Robot.enriched_at.
  * release_year LEFT BLANK — no credible launch-year citation exists for these
    material-handling models (only promo videos / distributor post-dates, which the
    playbook explicitly rejects as evidence). Never invented.

PATCH mode only (fills blank columns; never overwrites existing photos/features/
videos/tags/notes). One robot per import. No media replace. status stays
pending_review for human review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from html import unescape
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from fix_noblelift_robots import (
    COMPANY_NAME,
    COMPANY_SLUG,
    HEADERS,
    resolve_url,
    trigger_copy_media,
)
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name

COMPANY_ID = 1028
GROUP_SITE = "https://www.nobleliftgroup.com/en/product/material-handling.htm"

# Rows whose MODEL NAME cannot be tied to Noblelift at all, so even `availability`
# ("this product is currently sold") is unverifiable. Flagged for human review
# rather than stamped. Everything else in the fleet resolves to a live Noblelift
# product page in a current category, incl. the three "Non-standard Customization"
# programmes (3378-3380), which are genuine OEM offerings.
EXCLUDE: dict[int, str] = {
    3373: "OPL10 — no OPL10 in the OEM catalog; its PDP documents OPL12N/OPL25N only",
    3381: "ES15 — PDP is the generic 'Stacker Truck' customization page; 'ES15' as a "
          "Noblelift model is unverified (web hits are EP Equipment / other brands)",
}

# The 6 most-gapped pending_review robots (6 gaps each: year/price/avail/weight/
# payload/dims), chosen for the richest fillable OEM spec tables + a real spread of
# families. Each carries curated CREDIBLE third-party sources verified HTTP 200 and
# confirmed to be about that exact model (or its documented family, noted as such).
TARGETS: dict[int, dict[str, Any]] = {
    # Rejected for RT20G: https://zeppelin.pl/.../RT20G.pdf — HTTP 200 and named for the
    # model, but it is a 10 MB PDF whose text will not extract (font-subset encoding),
    # so its contents could not be confirmed to document RT20G. Not cited unverified.
    3346: {  # RT20G — sit-on reach truck
        "third_party": [
            ("https://www.noblelifteurope.com/index.asp?lng=en&k_id=32548", "website",
             "Noblelift Europe — reach truck range (official regional site)"),
        ],
    },
    3348: {  # RT16/20Pro-RT16/20B — sit-on reach truck
        "third_party": [
            ("https://nobleliftcanada.com/product/sit-on-1600-2000kg-rt16-20pro/", "website",
             "Noblelift Canada — RT16/20 Pro product page (official regional site)"),
            ("https://www.noblelifteurope.com/index.asp?lng=en&k_id=32548", "website",
             "Noblelift Europe — reach truck range (official regional site)"),
        ],
    },
    3344: {  # RRS-150/180 — stand-on reach truck
        "third_party": [
            ("https://www.noblelifteurope.com/index.asp?lng=en&k_id=32548", "website",
             "Noblelift Europe — reach truck range (official regional site)"),
        ],
    },
    3345: {  # RT16Li — sit-on lithium reach truck
        "third_party": [
            ("https://nobleliftcanada.com/product/sit-on-1600kg-rt16-li/", "website",
             "Noblelift Canada — RT16Li lithium reach truck (official regional site)"),
        ],
    },
    # NOTE: robot 3373 "OPL10" was evaluated and deliberately EXCLUDED. Its CRM URL
    # resolves to the OPL12-25N family page whose columns are OPL12N / OPL25N, and no
    # "OPL10" exists anywhere in the OEM list-page crawl (url map has OPL12-25N,
    # OLE-200, OPH01/01E, OVS-010, OPH12/12K, OPH10E/12EK). Sourcing that page's
    # 900 kg would attribute OPL12N's weight to OPL10. Flagged for human review.
    3343: {  # RT15Q — sit-on reach truck (single-model table)
        "third_party": [
            ("https://www.noblelifteurope.com/index.asp?lng=en&k_id=32548", "website",
             "Noblelift Europe — reach truck range (official regional site)"),
        ],
    },
    3377: {  # NR530 — ride-on floor scrubber
        "third_party": [
            # industrialsafety.com NR530 listing rejected: returns HTTP 403 to direct
            # fetch, so its content could not be verified.
            ("https://www.nobleliftna.com/nr530-ride-on", "website",
             "Noblelift North America — NR530 ride-on scrubber (official regional site)"),
        ],
    },
}

_NUM = re.compile(r"^\s*(\d+(?:\.\d+)?)")


def _cells(html: str) -> list[str]:
    out = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(c))).strip()
        for c in re.findall(r"<td[^>]*>(.*?)</td>", html, re.I | re.S)
    ]
    return [c for c in out if c]


def _page_name(html: str) -> str:
    m = re.search(r"var\s+name\s*=\s*'([^']+)'", html)
    return (m.group(1).strip() if m else "")


UNIT_RE = re.compile(r"^(Q\()?(kg|t|mm|m|km/h|m/s|kW|W|V/Ah|V|Ah|L|%|A|h|deg|°)\)?$", re.I)


def _is_unit(cell: str) -> bool:
    """Unit cells appear as 'kg', 'mm', but also 'Q（ kg ）' with FULL-WIDTH parens and
    stray spaces on the CN-authored tables. If such a cell isn't recognised as a unit
    it stays in the values list and shifts every value one column to the left — and
    when the shifted length coincidentally equals the column count, column-indexed
    picking silently maps each model to its NEIGHBOUR's number. Normalise first."""
    c = (cell or "").replace("（", "(").replace("）", ")").replace(" ", "")
    return bool(UNIT_RE.match(c))


def _norm_model(s: str) -> str:
    return re.sub(r"[^A-Z0-9/]", "", (s or "").upper())


def _parse_rows(html: str) -> tuple[list[str], list[tuple[str, str, list[str]]]]:
    """Return (model_columns, [(label, unit, [values...])]).

    Noblelift spec tables are often FAMILY tables with one column per model, e.g.
    'Model | RT16Pro | RT20Pro | RT16B | RT20B'. A flat (label, unit, value) scan
    silently grabs the FIRST column, which may belong to a sibling model — that is
    how a spec gets fabricated. Keep the columns so the caller can decide."""
    model_cols: list[str] = []
    rows: list[tuple[str, str, list[str]]] = []
    for raw in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S):
        cs = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(c))).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", raw, re.I | re.S)
        ]
        cs = [c for c in cs if c]
        if len(cs) < 2:
            continue
        head = cs[0].lower()
        if not model_cols and re.search(r"manufacturer|^model|type designation", head):
            model_cols = cs[1:]
            continue
        unit = ""
        values = cs[1:]
        if _is_unit(cs[1]):
            norm = cs[1].replace("（", "(").replace("）", ")").replace(" ", "")
            unit = re.sub(r"^Q\(|\)$", "", norm, flags=re.I)
            values = cs[2:]
        if values:
            rows.append((cs[0], unit, values))
    return model_cols, rows


def _strip_brand(name: str) -> str:
    return re.sub(r"^Noblelift\s+", "", name or "", flags=re.I).strip()


def expand_variants(name: str) -> list[str]:
    """Expand a slash-compressed family record into its member model codes.

    CRM rows are written as the OEM writes families: 'PS12/16/20N' means
    PS12N + PS16N + PS20N; 'PTE15/20N PRO' means PTE15N PRO + PTE20N PRO;
    'FEP-30/35/38P' means FEP-30P + FEP-35P + FEP-38P. Without expanding, a
    legitimate family record never matches its own page's columns and gets
    refused — while a wrong-URL row (PT20/25/30L on the PT20/25N page) still
    correctly fails to match."""
    n = _strip_brand(name)
    m = re.match(r"^([A-Za-z]+[\-]?)((?:\d+/)+\d+)([A-Za-z0-9][A-Za-z0-9 \-]*)?$", n)
    if not m:
        return [n] if n else []
    prefix, nums, suffix = m.group(1), m.group(2), (m.group(3) or "")
    return [f"{prefix}{num}{suffix}".strip() for num in nums.split("/")]


def page_covers_model(target_name: str, page_name: str, model_cols: list[str]) -> tuple[bool, str]:
    """A PDP may only source specs for a robot it actually documents.

    Covered when: the page IS this model/family by name; a column is this model;
    or every member of this family record appears among the columns.
    Not covered when the record simply isn't on the page (e.g. 'OPL10' on the
    'OPL12-25N' page whose columns are OPL12N/OPL25N, or 'PT20/25/30L' on the
    'PT20/25N' page) — sourcing there attributes a sibling's numbers to this robot."""
    full = _norm_model(_strip_brand(target_name))
    head = _norm_model(_strip_brand(target_name).split()[0]) if _strip_brand(target_name) else ""
    page = _norm_model(page_name)
    if full and page == full:
        return True, "family-exact"
    if head and page == head:
        return True, "family-exact-head"
    cols = {_norm_model(c) for c in model_cols}
    if full and full in cols:
        return True, "model-column"
    if head and head in cols:
        return True, "model-column-head"
    variants = [_norm_model(v) for v in expand_variants(target_name)]
    if len(variants) > 1 and cols and all(v in cols for v in variants):
        return True, f"family-variants:{'+'.join(variants)}"
    return False, "no-match"


def _match_indices(model_cols: list[str], target: str) -> list[int]:
    """Column indices belonging to this record (its variants), else all columns."""
    if not model_cols:
        return []
    cols = [_norm_model(c) for c in model_cols]
    wanted = {_norm_model(v) for v in expand_variants(target)}
    wanted.add(_norm_model(_strip_brand(target)))
    idx = [i for i, c in enumerate(cols) if c in wanted]
    return idx


def _pick(values: list[str], model_cols: list[str], target: str) -> str | None:
    """Only return a value that unambiguously belongs to `target`.

    When the record maps onto a subset of columns (a family record), restrict to
    THOSE columns and require agreement among them — a value that differs across
    the record's own variants is genuinely ambiguous for the combined row."""
    if not values:
        return None
    idx = _match_indices(model_cols, target) if model_cols and len(model_cols) == len(values) else []
    if idx:
        sub = [values[i] for i in idx]
        if len(set(sub)) == 1:
            return sub[0]
        if len(sub) == 1:
            return sub[0]
        return None
    if len(set(values)) == 1:
        return values[0]  # every column agrees → safe for the family record
    return None  # columns disagree and none is this model → refuse to guess


def parse_specs(url: str, target_name: str = "") -> dict[str, Any]:
    """Parse the noblelift.com PDP spec table into typed values, column-aware."""
    html = requests.get(url, headers=HEADERS, timeout=45, allow_redirects=True).text
    page_name = _page_name(html)
    model_cols, rows = _parse_rows(html)
    covered, why = page_covers_model(target_name or page_name, page_name, model_cols)
    specs: dict[str, Any] = {
        "page_name": page_name,
        "model_cols": model_cols,
        "covered": covered,
        "coverage": why,
    }
    if not covered:
        return specs  # never source specs from a page that omits this model

    target = target_name or page_name
    labelled: list[tuple[str, str, str]] = []
    for lab, unit, values in rows:
        if "battery voltage" in lab.lower():
            # 'V/Ah' cells like '48/420,560' | '48/560'. Voltage and capacity agree
            # independently across columns — the pack is 48 V on every RT16/20Pro
            # variant even though the Ah options differ. Resolve each component
            # separately so a shared voltage isn't thrown away with an ambiguous Ah
            # (and an ambiguous Ah is never fused into a shared voltage).
            volts, caps = [], []
            for v in values:
                vp, _, ap = v.partition("/")
                volts.append(vp.strip())
                caps.append(ap.strip().replace(",", "/").replace(" ", ""))
            vsel = _pick(volts, model_cols, target)
            csel = _pick(caps, model_cols, target)
            if vsel and re.fullmatch(r"\d+(?:\.\d+)?", vsel):
                specs["voltage"] = f"{float(vsel):g} V"
            if csel and re.fullmatch(r"\d+(?:\.\d+)?(?:[-/]\d+(?:\.\d+)?)*", csel):
                specs["battery_capacity"] = f"{csel} Ah"
            continue
        v = _pick(values, model_cols, target)
        if v is not None and re.search(r"\d", v):
            labelled.append((lab, v, unit))
    specs["raw"] = labelled

    def num(v: str) -> float | None:
        m = _NUM.match(v.replace(",", ""))
        return float(m.group(1)) if m else None

    for lab, val, unit in labelled:
        low = lab.lower()
        u = unit.lower()
        # --- weight (real column) ---
        # The OEM qualifies these ('Net weight without battery', 'Service weight
        # incl. battery'). Keep the qualifier in the weight TEXT so the number is
        # never presented as a bare curb weight it isn't.
        if ("service weight" in low or "net weight" in low) and u == "kg" and "weight_kg" not in specs:
            n = num(val)
            if n:
                specs["weight_kg"] = n
                if "without" in low and "batter" in low:
                    qual = " (net, without battery)"
                elif "incl" in low and "batter" in low:
                    qual = " (incl. battery)"
                else:
                    qual = ""
                specs["weight_text"] = f"{n:g} kg{qual}"
        # --- overall dimensions (real columns) ---
        if low.startswith("overall length") and u == "mm":
            specs["length_mm"] = num(val)
        if low.startswith("overall width") and u == "mm":
            specs["width_mm"] = num(val)
        if low.startswith("overall height") and u == "mm":
            specs["height_mm"] = num(val)
        # --- combined product dimensions LxWxH ---
        if "product dimensions" in low and "x" in val.lower():
            parts = re.findall(r"\d+(?:\.\d+)?", val)
            if len(parts) == 3:
                specs["length_mm"] = float(parts[0])
                specs["width_mm"] = float(parts[1])
                specs["height_mm"] = float(parts[2])
        # --- travel speed → speed (km/h) ---
        if "travel speed" in low and u in ("km/h",) and "speed" not in specs:
            specs["speed"] = num(val)
        # (battery voltage/capacity resolved per-component above)
        # --- payload (no column; kept for notes/report) ---
        if ("load capacity" in low or "rated load" in low or low.startswith("capacity")) and "payload_kg" not in specs:
            n = num(val)
            if n is not None:
                specs["payload_kg"] = n * 1000.0 if (u == "t" or n <= 5) else n
        if "lift height" in low and u == "mm":
            specs["lift_mm"] = num(val)
    return specs


def build_patch_row(robot: dict[str, Any], url: str, specs: dict[str, Any],
                    third_party: list[tuple[str, str, str]]) -> dict[str, Any]:
    name = robot["name"]
    sources: list[dict[str, str]] = [
        {"url": url, "type": "website", "title": f"Noblelift official product page — {specs.get('page_name') or name}"},
        {"url": GROUP_SITE, "type": "website", "title": "Noblelift Group — Material Handling (corporate site)"},
    ]
    for tp_url, tp_type, tp_title in third_party:
        sources.append({"url": tp_url, "type": tp_type, "title": tp_title})

    # validate_staging requires description|purpose. Echo the robot's CURRENT values
    # so the row validates without proposing new prose — patch mode skips non-blank
    # text anyway, so this is a no-op against the DB and never rewrites copy.
    existing_desc = (robot.get("description") or "").strip()
    existing_purpose = (robot.get("purpose") or "").strip()

    row: dict[str, Any] = {
        "id": int(robot["id"]),
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CN",
        "description": existing_desc or existing_purpose,
        "purpose": existing_purpose or existing_desc,
        "url": url,
        "availability_status_key": "available",
        "sources": sources,
        "research_notes": (
            "Noblelift source-extension pass: added OEM PDP + nobleliftgroup.com "
            "corporate site + credible third-party sources (official regional "
            "subsidiaries / trade / distributor datasheet); filled cited specs from "
            "the OEM PDP spec table. release_year left blank — no credible "
            "launch-year citation found."
        ),
    }
    # Typed spec columns (patch fills only where DB is null).
    if specs.get("weight_kg") is not None:
        row["weight_kg"] = specs["weight_kg"]
        row["weight"] = specs.get("weight_text") or f"{specs['weight_kg']:g} kg"
    if specs.get("length_mm") is not None:
        row["length_mm"] = specs["length_mm"]
        row["length"] = f"{specs['length_mm']:g} mm"
    if specs.get("width_mm") is not None:
        row["width_mm"] = specs["width_mm"]
        row["width"] = f"{specs['width_mm']:g} mm"
    if specs.get("height_mm") is not None:
        row["height_mm"] = specs["height_mm"]
        row["height"] = f"{specs['height_mm']:g} mm"
    if specs.get("speed") is not None:
        row["speed"] = specs["speed"]
    if specs.get("voltage"):
        row["voltage"] = specs["voltage"]
    if specs.get("battery_capacity"):
        row["battery_capacity"] = specs["battery_capacity"]
    # payload has no Robot column — pack into notes so the server keeps the citation.
    notes_bits = []
    if specs.get("payload_kg") is not None:
        notes_bits.append(f"Payload: {specs['payload_kg']:g} kg")
    if specs.get("lift_mm") is not None:
        notes_bits.append(f"Lift height: {specs['lift_mm']:g} mm")
    if notes_bits:
        row["notes"] = " | ".join(notes_bits)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Extend sources + specs for 6 Noblelift robots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--ids", nargs="*", type=int, help="override target ids")
    parser.add_argument("--all", action="store_true",
                        help="process every pending_review robot except EXCLUDE")
    args = parser.parse_args()

    client = ResearchApiClient()
    by_id = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    }
    if args.ids:
        target_ids = args.ids
    elif args.all:
        target_ids = [i for i in sorted(by_id) if i not in EXCLUDE]
    else:
        target_ids = list(TARGETS.keys())

    plan: list[dict[str, Any]] = []
    staging: dict[int, dict[str, Any]] = {}
    for rid in target_ids:
        robot = by_id.get(rid)
        if not robot:
            print(f"SKIP {rid}: not a pending_review robot in company {COMPANY_ID}")
            continue
        cfg = TARGETS.get(rid, {})
        url, res = resolve_url(robot["name"], (robot.get("url") or "").strip())
        try:
            specs = parse_specs(url, robot["name"])
        except requests.RequestException as exc:
            print(f"  FAIL scrape {rid}: {exc}")
            continue
        if not specs.get("covered"):
            # Fail closed on SPECS only: the PDP documents a different model, so no
            # number from it may be attributed here (see page_covers_model). The row
            # still gets its sources + availability, which don't depend on the table.
            print(f"  NO-SPECS {rid} {robot['name']}: PDP {specs.get('page_name')!r} "
                  f"(cols={specs.get('model_cols')}) does not cover this model "
                  f"[{specs.get('coverage')}] — sources/availability only")
        row = build_patch_row(robot, url, specs, cfg.get("third_party", []))
        staging[rid] = row
        item = {
            "id": rid,
            "name": robot["name"],
            "url": url,
            "resolution": res,
            "page_name": specs.get("page_name"),
            "weight_kg": row.get("weight_kg"),
            "length_mm": row.get("length_mm"),
            "width_mm": row.get("width_mm"),
            "height_mm": row.get("height_mm"),
            "speed": row.get("speed"),
            "voltage": row.get("voltage"),
            "battery_capacity": row.get("battery_capacity"),
            "payload_kg": specs.get("payload_kg"),
            "n_sources": len(row["sources"]),
        }
        plan.append(item)
        print(f"{rid} {robot['name'][:22]:22} page={specs.get('page_name')!r} "
              f"w_kg={item['weight_kg']} L={item['length_mm']} W={item['width_mm']} "
              f"H={item['height_mm']} spd={item['speed']} volt={item['voltage']} "
              f"bat={item['battery_capacity']} payload={item['payload_kg']} src={item['n_sources']}")

    preview = _RESEARCH_DIR / "staging" / "reports" / "noblelift-sources-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="noblelift-src-"))
    imported: list[int] = []
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    all_ok = True
    for item in plan:
        rid = item["id"]
        row = staging[rid]
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = import_staging(
            fpath,
            patch=True,                 # patch_existing: fill blanks only
            force_overwrite=False,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=False,        # keep existing 4 photos untouched
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result.get('errors')}", file=sys.stderr)
            continue
        # bulk-import created_count>0 would mean a NEW robot — must never happen here.
        if result.get("created_count"):
            all_ok = False
            print(f"WARN {rid}: created_count={result.get('created_count')} (expected patch only)", file=sys.stderr)
        imported.append(rid)
        for k in totals:
            totals[k] += result.get(k, 0) or 0
        print(f"patched {rid} {row['name']}")

    print(json.dumps({"ok": all_ok, **totals, "imported": imported}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
