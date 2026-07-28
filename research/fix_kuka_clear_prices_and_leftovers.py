"""Clear unsourced KUKA price_min/max estimates (no public OEM MSRP).

Also append honest short-feature notes for discontinued / gen-1 / placeholder rows
that have no live OEM table match — never invent specs or prices.

Usage:
  python fix_kuka_clear_prices_and_leftovers.py            # dry-run
  python fix_kuka_clear_prices_and_leftovers.py --apply
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1396

# Honest feature notes — facts about why specs are absent, not invented numbers.
FEATURE_NOTES: dict[str, str] = {
    "KR 700 PA": (
        "Legacy palletizing model; not present in current KUKA family product tables "
        "(OEM palletizing-robots hub)."
    ),
    "KR 300-2 PA": (
        "Legacy palletizing model; not present in current KUKA family product tables "
        "(OEM palletizing-robots hub)."
    ),
    "KR 470-2 PA": (
        "Legacy palletizing model; not present in current KUKA family product tables "
        "(OEM palletizing-robots hub)."
    ),
    "KR 120 R3500-2 PA": (
        "Not listed in the current KR QUANTEC PA family table on kuka.com "
        "(no live Total load / reach row)."
    ),
    "KR 6 R1440-2 nano": (
        "Not listed in the current KR CYBERTECH nano family table on kuka.com "
        "(no live Total load / reach row)."
    ),
    "KR 120 R2700": (
        "Generation-1 designation; live OEM family table publishes -2 successors only "
        "(specs not copied from -2)."
    ),
    "KR 120 R2300": (
        "Not listed in the current KR QUANTEC family table on kuka.com "
        "(no live Total load / reach row)."
    ),
    "KR 90 R2300": (
        "Not listed in the current KR CYBERTECH family table on kuka.com "
        "(no live Total load / reach row)."
    ),
    "KR 90 R2700": (
        "Not listed in the current KR CYBERTECH family table on kuka.com "
        "(no live Total load / reach row)."
    ),
    "KR 120 R2700-2 K": (
        "Shelf-mounted K variant not listed in the current KR QUANTEC table "
        "(sibling K rows exist for other payloads; this exact name absent)."
    ),
    "KR SCARA": (
        "Family placeholder name (not a single variant); see KR SCARA Z-series rows for OEM specs."
    ),
    "KMP 250P": (
        "KUKA KMP topload AMR family; exact payload not confirmed on a public SKU page in this pass."
    ),
    "KMP 600W": (
        "KUKA KMP topload AMR family; exact payload not confirmed on a public SKU page in this pass."
    ),
    "KUKA omniMove E375 3000": (
        "KUKA omniMove heavy-load platform; per-model payload/year not published on scraped hub pages."
    ),
    "KUKA omniMove E575 7000": (
        "KUKA omniMove heavy-load platform; per-model payload/year not published on scraped hub pages."
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:  # noqa: BLE001
            print(f"list retry {a}: {e}", file=sys.stderr)
            time.sleep(5)
    if robots is None:
        return 1

    price_targets = [
        r
        for r in robots
        if r.get("price_min") not in (None, "") or r.get("price_max") not in (None, "")
    ]
    feat_targets = []
    for r in robots:
        name = (r.get("name") or "").strip()
        note = FEATURE_NOTES.get(name)
        if not note:
            continue
        cur = (r.get("features") or "").strip()
        if note in cur:
            continue
        if len(cur) >= 100 and "Total load" in cur:
            continue
        merged = f"{cur} | {note}" if cur else note
        feat_targets.append({"id": int(r["id"]), "name": name, "features": merged[:1900], "old_len": len(cur)})

    print(f"price_clear={len(price_targets)} feature_notes={len(feat_targets)}")
    for p in feat_targets:
        print(f"  feat {p['id']} {p['name']} {p['old_len']}->{len(p['features'])}")

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    ok = fail = 0
    for r in price_targets:
        rid = int(r["id"])
        try:
            patched = client._patch(
                f"robots/robots/{rid}/",
                {
                    "price_min": None,
                    "price_max": None,
                    "price_currency": "",
                    "price_range": "",
                },
            )
            still = patched.get("price_min") not in (None, "") or patched.get("price_max") not in (
                None,
                "",
            )
            print(f"{'FAIL-still' if still else 'ok'} price {rid} {r.get('name')}")
            if still:
                fail += 1
            else:
                ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL price {rid}: {exc}")
            fail += 1
        time.sleep(0.06)

    for p in feat_targets:
        try:
            client._patch(f"robots/robots/{p['id']}/", {"features": p["features"]})
            print(f"ok feat {p['id']} {p['name']}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL feat {p['id']}: {exc}")
            fail += 1
        time.sleep(0.06)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
