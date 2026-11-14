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
    seen_ids: set[int] = set()
    today = date.today().isoformat()
    for row in sheet_rows:
        rid = str(row.get("id") or "").strip()
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
        try:
            robot_id = int(rid)
        except ValueError:
            skips.append(f"{rid!r}: id is not a number")
            continue
        # The endpoint rejects a request with a repeated id; keep the first row.
        if robot_id in seen_ids:
            skips.append(f"{rid}: repeated id, only the first row is sent")
            continue
        seen_ids.add(robot_id)

        # The page was read when the sheet was assessed, not today.
        checked_on = (row.get("checked_on") or "").strip()
        try:
            checked_on = date.fromisoformat(checked_on).isoformat()
        except ValueError:
            skips.append(f"{rid}: no valid checked_on in sheet, using today ({today})")
            checked_on = today

        batch.append({
            "id": robot_id,
            "expected_name": name,
            "expected_sales_status": current,
            "sales_status": new_status,
            "source_url": source_url,
            "checked_on": checked_on,
        })
    return batch, skips


BATCH_MAX_ROWS = 200  # sales-status-batch rejects larger requests


def chunked(rows: list[dict[str, Any]], size: int = BATCH_MAX_ROWS) -> list[list[dict[str, Any]]]:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheet", help="Reviewed CSV from assess_sales_status.py")
    parser.add_argument("--apply", action="store_true", help="Write (default is dry_run).")
    parser.add_argument("--api-base", default="", help="Override IMPORT_SYNC_API_BASE_URL.")
    parser.add_argument("--api-key", default=None, help="Override IMPORT_SYNC_API_KEY.")
    args = parser.parse_args(argv)

    sheet = Path(args.sheet)
    if not sheet.exists():
        print(f"Sheet not found: {sheet}", file=sys.stderr)
        return 2

    load_env_file(_HERE.parents[1] / "robotaigeek-server" / ".env")
    if args.api_base:
        os.environ["IMPORT_SYNC_API_BASE_URL"] = args.api_base
    if args.api_key is not None:
        os.environ["IMPORT_SYNC_API_KEY"] = args.api_key
    for key in ("IMPORT_SYNC_API_BASE_URL", "IMPORT_SYNC_API_KEY"):
        if key == "IMPORT_SYNC_API_KEY" and args.api_key == "":
            continue
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

    api = ResearchApiClient(
        base_url=os.environ.get("IMPORT_SYNC_API_BASE_URL"),
        api_key=os.environ.get("IMPORT_SYNC_API_KEY", ""),
    )
    dry_run = not args.apply
    chunks = chunked(batch)
    print(f"Sending {len(batch)} rows in {len(chunks)} request(s) (dry_run={dry_run})…")
    responses = []
    for i, chunk in enumerate(chunks, 1):
        resp = api._post("robots/robots/sales-status-batch/", {"dry_run": dry_run, "rows": chunk})
        responses.append(resp)
        if isinstance(resp, dict):
            print(f"  request {i}/{len(chunks)}: applied={resp.get('applied_count')} "
                  f"skipped={resp.get('skipped_count')} error={resp.get('error', '')}")
    result = {
        "dry_run": dry_run,
        "applied_count": sum((r or {}).get("applied_count", 0) for r in responses if isinstance(r, dict)),
        "skipped_count": sum((r or {}).get("skipped_count", 0) for r in responses if isinstance(r, dict)),
        "results": [row for r in responses if isinstance(r, dict) for row in (r.get("results") or [])],
        "responses": responses,
    }

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = sheet.with_name(f"{sheet.stem}_apply_{stamp}.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:4000])
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
