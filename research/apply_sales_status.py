"""Apply a reviewed sales_status CSV sheet via the batch endpoint.

Dry run by default. Only rows whose `decision` is `accept` (use the proposed
value) or a corrected assessable key are sent. Prints the endpoint response
and saves it next to the sheet.

Run from scripts/research:
  python apply_sales_status.py output/sales_status_assess_YYYYMMDD-HHMM.csv
  python apply_sales_status.py output/sales_status_assess_YYYYMMDD-HHMM.csv --apply

Env: IMPORT_SYNC_API_BASE_URL, IMPORT_SYNC_API_KEY (admin key).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from recheck_company_funding import load_env_file  # noqa: E402

ASSESSABLE = {
    "not_for_sale",
    "pre_order",
    "limited_availability",
    "general_sale",
    "made_to_order",
}


def normalize_decision(raw: str) -> str:
    return str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")


def rows_from_sheet(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def build_batch_rows(sheet_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (batch rows, skip notes)."""
    batch: list[dict[str, Any]] = []
    skips: list[str] = []
    today = date.today().isoformat()
    for row in sheet_rows:
        rid = row.get("id")
        name = (row.get("name") or "").strip()
        current = normalize_decision(row.get("current_status") or "not_assessed") or "not_assessed"
        proposed = normalize_decision(row.get("proposed_sales_status") or "")
        decision = normalize_decision(row.get("decision") or "")
        source_url = (row.get("source_url") or "").strip()

        if not rid or not name:
            skips.append(f"skip missing id/name: {row!r}")
            continue
        if not decision:
            skips.append(f"{rid}: blank decision")
            continue

        if decision == "accept":
            new_status = proposed
        elif decision in ASSESSABLE:
            new_status = decision
        else:
            skips.append(f"{rid}: decision {decision!r} not accept/assessable")
            continue

        if new_status not in ASSESSABLE:
            skips.append(f"{rid}: proposed/corrected status {new_status!r} not assessable")
            continue
        if not source_url:
            skips.append(f"{rid}: missing source_url")
            continue

        batch.append({
            "id": int(rid),
            "expected_name": name,
            "expected_sales_status": current,
            "sales_status": new_status,
            "source_url": source_url,
            "checked_on": today,
        })
    return batch, skips


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheet", help="Reviewed CSV from assess_sales_status.py")
    parser.add_argument("--apply", action="store_true", help="Write (default is dry_run).")
    args = parser.parse_args(argv)

    sheet = Path(args.sheet)
    if not sheet.exists():
        print(f"Sheet not found: {sheet}", file=sys.stderr)
        return 2

    load_env_file(_HERE.parents[1] / "robotaigeek-server" / ".env")
    for key in ("IMPORT_SYNC_API_BASE_URL", "IMPORT_SYNC_API_KEY"):
        if not os.environ.get(key):
            print(f"Missing {key}", file=sys.stderr)
            return 2

    sheet_rows = rows_from_sheet(sheet)
    batch, skips = build_batch_rows(sheet_rows)
    for note in skips:
        print(note)
    if not batch:
        print("No rows to send.")
        return 0

    from api_client import ResearchApiClient

    api = ResearchApiClient()
    body = {"dry_run": not args.apply, "rows": batch}
    print(f"Sending {len(batch)} rows (dry_run={body['dry_run']})…")
    result = api._post("robots/robots/sales-status-batch/", body)

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = sheet.with_name(f"{sheet.stem}_apply_{stamp}.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:4000])
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
