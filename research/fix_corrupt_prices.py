"""Clear unsourced/corrupt prices on 2 LIVE robots (Martti-directed, 2026-09-23).

WHY
---
The /prices/{category} and /robots-for-sale/{category} pages rank the catalog
by price, so one bad row headlines a whole guide as "the cheapest model" — in
the visible copy AND in the FAQPage schema Google and AI engines read.

  * 5371 Unitree H2 PLUS   price_min=2       price_max=29,900
  * 60   Da Vinci Xi       price_min=15      price_max=2,000,000

price_min is garbage in both. price_max is ALSO unsourced:
  - unitree.com/H2plus publishes NO price (verified 2026-09-23); 29,900 is the
    base H2's price sitting on the H2 PLUS row.
  - Intuitive sells da Vinci through enterprise sales and publishes no list
    price; 2,000,000 is an industry estimate, and neither row cites a source.

Our own price pages promise "We list a price only when the maker or a
verifiable source has published one — we never estimate." So the honest fix is
to clear BOTH fields and let the pages say "not publicly announced", rather
than keep a number we cannot stand behind.

DISCIPLINE (feedback_destructive_prod_writes)
---------------------------------------------
scope filter (2 explicit ids) + expected-count assert + capture-before-mutate
(snapshot written to disk) + verify-after. Plain PATCH, which is wipe-safe;
the admin update-data action is NOT used because it blanks unsent fields.

Usage:  python fix_corrupt_prices.py           (dry run)
        python fix_corrupt_prices.py --apply
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient  # noqa: E402

EXPECTED_ROWS = 2

# id -> (name guard, current price_min guard, note to record)
TARGETS = {
    5371: {
        "name": "Unitree H2 PLUS",
        "expect_price_min": "2.00",
        "note": (
            "Price cleared 2026-09-23: price_min=2 was a data-entry error and price_max=29,900 "
            "is the base H2's price, not the H2 PLUS. Unitree publishes no price for the H2 PLUS "
            "(https://www.unitree.com/H2plus, checked 2026-09-23) — quote on enquiry."
        ),
    },
    60: {
        "name": "Da Vinci Xi",
        "expect_price_min": "15.00",
        "note": (
            "Price cleared 2026-09-23: price_min=15 was a data-entry error and price_max=2,000,000 "
            "was an uncited industry estimate. Intuitive Surgical publishes no list price for the "
            "da Vinci Xi (https://www.intuitive.com/en-us/products-and-services/da-vinci/xi) — "
            "sold through enterprise sales."
        ),
    },
}


def main() -> None:
    apply = "--apply" in sys.argv
    client = ResearchApiClient()
    assert len(TARGETS) == EXPECTED_ROWS, f"scope check failed: {len(TARGETS)} != {EXPECTED_ROWS}"

    snapshot = {}
    planned = {}
    for robot_id, target in TARGETS.items():
        row = client._get(f"robots/robots/{robot_id}/")
        snapshot[robot_id] = row
        name = row.get("name", "")
        # Guards: refuse to touch a row that is not the one surveyed.
        if target["name"].lower() not in name.lower():
            print(f"SKIP {robot_id}: name {name!r} does not match {target['name']!r}")
            continue
        if str(row.get("price_min")) != target["expect_price_min"]:
            print(f"SKIP {robot_id} ({name}): price_min is {row.get('price_min')!r}, "
                  f"expected {target['expect_price_min']!r} — already fixed or changed.")
            continue
        existing_notes = str(row.get("notes") or "").strip()
        planned[robot_id] = {
            "price_min": None,
            "price_max": None,
            "notes": (existing_notes + "\n" if existing_notes else "") + target["note"],
        }
        print(f"{name} (id {robot_id}): clear price_min={row.get('price_min')} "
              f"price_max={row.get('price_max')} + record reason in notes")

    out = Path(sys.argv[sys.argv.index("--snapshot") + 1]) if "--snapshot" in sys.argv else _HERE / "fix_corrupt_prices_before.json"
    out.write_text(json.dumps(snapshot, indent=1, default=str), encoding="utf-8")
    print(f"\nbefore-snapshot written: {out}")

    if not planned:
        print("nothing to do.")
        return
    if not apply:
        print("DRY RUN — nothing written. Re-run with --apply.")
        return

    print("\nApplying...")
    for robot_id, payload in planned.items():
        client._patch(f"robots/robots/{robot_id}/", payload)

    print("Verifying...")
    failures = 0
    for robot_id in planned:
        after = client._get(f"robots/robots/{robot_id}/")
        pmin, pmax = after.get("price_min"), after.get("price_max")
        note_ok = TARGETS[robot_id]["note"][:60] in str(after.get("notes") or "")
        ok = pmin in (None, "") and pmax in (None, "") and note_ok
        if not ok:
            failures += 1
        print(f"  {'OK ' if ok else 'FAIL'} {after.get('name')}: price_min={pmin!r} "
              f"price_max={pmax!r} note_recorded={note_ok}")
    print(f"\n{'ALL VERIFIED' if failures == 0 else f'{failures} ROW(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
