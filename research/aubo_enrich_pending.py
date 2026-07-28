"""AUBO Robotics (769) queue enrichment: family metadata + specs + narrative
fields + error-flag fixes on the 15 pending_review + 1 draft robots.

Queue defects (audit 2026-07-27):
  - family data empty on the 13 i-series robots (FB trio already keyed)
  - payload_kg cloned to 16.0 on all 7 "Collaborative Robot" records: the
    aubo-cobot.com CPID template serves IDENTICAL static HTML for every CPID
    (the 16kg is the i3's *weight* row) — a previous scrape trusted it
  - url_domain_mismatch on the 6 older records (reseller/PDF/RoboDK URLs)
  - non_english_content on 361 (Chinese description)
  - missing_manufacturer_country on 684-688
  - FB trio imageless; their launch page dates the series (Changzhou,
    2019-03-10) -> grounded release_year=2019

Authoritative spec source: https://www.aubo-cobot.com/public/iproduct3
(per-model table: payload / weight / repeatability / reach, all 7 models).
Narrative facts come from the same page's English copy (SDK/API open platform;
drag teaching / coordinate positioning / path planning / offline programming;
fenceless near-human operation).

Duplicate pairs (old -> official-site twin) are NOT merged here — rejection is
a review decision: 687->1641 (i3), 361->1642 (i5), 685->1644 (i10),
686->1646 (i16), 684->1647 (i20). This script only merges their tags into the
twins and repoints the old records' URLs at the official hub.

Usage:
    python aubo_enrich_pending.py            # dry-run
    python aubo_enrich_pending.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from import_staging import resolve_created_by_id  # noqa: E402
from map_to_bulk_import import staging_dict_to_bulk_import_row  # noqa: E402

COMPANY_ID = 769
COMPANY_SLUG = "aubo-robotics"
COMPANY_NAME = "AUBO Robotics"
I_HUB = "https://www.aubo-cobot.com/public/iproduct3"
CPID = "https://www.aubo-cobot.com/public/i5product3?CPID={m}"
FB_PAGE = "https://www.aubo-cobot.com/public/jumcase?xwid=4"
FB_HERO = "https://www.troysupply.com/uploadfile/202109/16/5987abc7b21be5c586882f04674bb47f.jpg"

# model -> (payload_kg, reach_mm, repeatability_mm, weight_kg)  [iproduct3 table]
SPECS = {
    "i3": (3.0, 625.0, 0.02, 16.0),
    "i5": (5.0, 886.5, 0.02, 24.0),
    "i7": (7.0, 786.5, 0.02, 24.0),
    "i10": (10.0, 1350.0, 0.03, 38.5),
    "i12": (12.0, 1250.0, 0.03, 40.0),
    "i16": (16.0, 967.5, 0.03, 38.0),
    "i20": (20.0, 1650.0, 0.1, 63.0),
}

# robot id -> (model, group)  group: "official" (CPID pages) | "legacy" | "fb"
ROBOTS: dict[int, tuple[str, str]] = {
    361: ("i5", "legacy"), 684: ("i20", "legacy"), 685: ("i10", "legacy"),
    686: ("i16", "legacy"), 687: ("i3", "legacy"), 688: ("i5L", "legacy"),
    1641: ("i3", "official"), 1642: ("i5", "official"), 1643: ("i7", "official"),
    1644: ("i10", "official"), 1645: ("i12", "official"), 1646: ("i16", "official"),
    1647: ("i20", "official"),
    3529: ("i5FB", "fb"), 4810: ("i3FB", "fb"), 4811: ("i10FB", "fb"),
}

# Grounded family-wide narrative (iproduct3 English copy). mounting is not
# stated on the page -> left empty on the i-series.
NARRATIVE = {
    "programming_interface": "Drag teaching, coordinate positioning, path planning and offline programming via visual interface",
    "safety_fencing": "Not required — designed for fenceless operation in close proximity to people",
    "deployment_context": "Quickly adapts to different application scenarios through abundant configuration options",
    "ecosystem_compatibility": "Open system platform with SDK and API; multiple communication methods to peripheral equipment",
}

FB_YEAR_CITE = (
    "release_year=2019: AUBO launched its explosion-proof collaborative robot "
    "line (FB series) with a world premiere in Changzhou on 10 March 2019, per "
    "the official AUBO launch page. (https://www.aubo-cobot.com/public/jumcase?xwid=4)"
)

# Corrections for wrong non-null values (direct PATCH, plain & wipe-safe):
PAYLOAD_FIX = {1641: 3.0, 1642: 5.0, 1643: 7.0, 1644: 10.0, 1645: 12.0,
               1647: 20.0, 687: 3.0, 685: 10.0}

DESC_361_EN = (
    "AUBO-i5 is a mid-range collaborative robot arm in AUBO's i Series, "
    "designed for precise, flexible automation with a balance of payload, "
    "reach and affordability. Unlike conventional industrial robots it is "
    "built for easy deployment and fenceless human-robot collaboration, and "
    "is widely used for assembly, pick-and-place and material handling in "
    "small and mid-sized factories and flexible production lines."
)

# Duplicate pairs: legacy id -> official twin id (tags merged into the twin).
DUP_TWINS = {687: 1641, 361: 1642, 685: 1644, 686: 1646, 684: 1647}
# Legacy tags that are factually wrong for a fixed cobot arm.
TAG_BLOCKLIST = {"wheeled", "care robot"}


def build_rows(by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for rid, (model, group) in ROBOTS.items():
        r = by_id[rid]
        row: dict[str, Any] = {
            "id": rid,
            "name": r["name"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "url": (r.get("url") or "").strip(),
            "model_name": r["name"],
            "variant_code": r["name"],
            "source_locale": "en",
            "sources": [{"url": I_HUB if group != "fb" else FB_PAGE,
                         "type": "website", "title": "AUBO official product page"}],
        }
        if group in ("official", "legacy"):
            row.update({
                "family_name": "i Series",
                "family_key": "aubo:i-series",
                "variant_label": model,
                "family_url": I_HUB,
                "product_url_scope": "exact_variant" if group == "official" else "family",
                **NARRATIVE,
            })
            spec = SPECS.get(model)
            if spec:
                pay, reach, rep, wt = spec
                # patch mode only fills NULLs; wrong non-nulls fixed via PATCH below
                row.update({"payload_kg": pay, "reach_mm": reach,
                            "repeatability_mm": rep, "weight_kg": wt, "dof": 6})
            if group == "legacy":
                row["manufacturer_country_code"] = "CN"
        else:  # fb
            row.update({
                "release_year": 2019,
                "research_notes": FB_YEAR_CITE,
                "manufacturer_country_code": "CN",
                "image": FB_HERO,
                "images": [FB_HERO],
            })
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    snap = json.loads(Path(
        r"C:\Users\tramk\AppData\Local\Temp\claude\C--Github-Personal-robot-ai-geek"
        r"\f3998b3d-68c5-4c68-85be-c6a45d3e4add\scratchpad\aubo_all.json"
    ).read_text(encoding="utf-8"))
    by_id = {int(r["id"]): r for r in snap}

    rows = [staging_dict_to_bulk_import_row(r) | {"id": r["id"]} for r in build_rows(by_id)]

    # Direct-PATCH plan (wrong values that patch-mode import will not touch)
    patches: dict[int, dict[str, Any]] = {}
    for rid, pay in PAYLOAD_FIX.items():
        patches.setdefault(rid, {})["payload_kg"] = pay
    patches.setdefault(361, {})["description"] = DESC_361_EN
    for rid in (361, 684, 685, 686, 687, 688):
        patches.setdefault(rid, {})["url"] = I_HUB
    # Tag merge into official twins
    for legacy, twin in DUP_TWINS.items():
        legacy_tags = [t for t in (by_id[legacy].get("tags") or [])
                       if t.strip().lower() not in TAG_BLOCKLIST]
        merged = sorted(set((by_id[twin].get("tags") or []) + legacy_tags))
        if set(merged) != set(by_id[twin].get("tags") or []):
            patches.setdefault(twin, {})["tags"] = merged

    print(f"import rows: {len(rows)}   direct patches: {len(patches)}")
    if not args.apply:
        print(json.dumps(rows[0], indent=1, ensure_ascii=False)[:900])
        print("patches:", json.dumps({k: {kk: (vv if not isinstance(vv, list) else f'{len(vv)} tags') for kk, vv in v.items()} for k, v in patches.items()}, indent=1, ensure_ascii=False)[:1500])
        print("dry-run; pass --apply")
        return 0

    client = ResearchApiClient()
    created_by = resolve_created_by_id(args.created_by_id)
    for i in range(0, len(rows), 8):
        batch = rows[i:i + 8]
        for attempt in range(5):
            try:
                resp = client.bulk_import_robots(
                    batch, update_existing=True, patch_existing=True,
                    status="pending_review", skip_company_update=True,
                    created_by_id=created_by)
                print(f"batch {i // 8}:", {k: v for k, v in resp.items() if k.endswith("_count")})
                break
            except Exception as exc:  # noqa: BLE001
                print(f"batch {i // 8} attempt {attempt}: {exc}")
                time.sleep(30 * (attempt + 1))

    for rid, payload in patches.items():
        for attempt in range(5):
            try:
                client._patch(f"robots/robots/{rid}/", payload)
                print(f"patched {rid}: {sorted(payload)}")
                break
            except Exception as exc:  # noqa: BLE001
                print(f"patch {rid} attempt {attempt}: {exc}")
                time.sleep(30 * (attempt + 1))
        time.sleep(0.3)

    from fix_acy_gallery_cleanup import trigger_copy_media
    ok, fail = trigger_copy_media([3529, 4810, 4811], force=False)
    print(f"copy-media (FB heroes) ok={ok} fail={fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
