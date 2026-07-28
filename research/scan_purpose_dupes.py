"""DB-wide scan for robots whose `purpose` duplicates their `description`.

The earlier pass only sampled 12 companies (193 found, all fixed). This walks every robot
in every status so the remaining backlog is a real number, not an extrapolation.

Usage:
  python scan_purpose_dupes.py                 # all statuses
  python scan_purpose_dupes.py --status published
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

_RD = Path(__file__).resolve().parent
if str(_RD) not in sys.path:
    sys.path.insert(0, str(_RD))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from validate_staging import purpose_duplicates_description

STATUSES = ["published", "pending_review", "draft", "rejected"]


def scan_status(client: ResearchApiClient, status: str, page_size: int = 50) -> tuple[list[dict], int, int]:
    """Return (rows, pages_ok, pages_failed).

    Prod 502s on these heavily-serialized pages. A failed page must NOT end the scan —
    the first version broke out and silently reported 100 of ~2000 published robots as if
    it were the whole set. Skip the page, keep going, and report the miss count so a
    partial scan can never be mistaken for a complete one.
    """
    out, page, ok, failed = [], 1, 0, 0
    total_pages: int | None = None
    while True:
        data = None
        for attempt in range(6):
            try:
                data = client._get("robots/robots/", params={"status": status, "page": page, "page_size": page_size})
                break
            except Exception as exc:
                print(f"  {status} p{page} retry {attempt}: {str(exc)[:60]}", flush=True)
                time.sleep(2 ** attempt)
        if data is None:
            failed += 1
            print(f"  SKIP {status} page {page} (unreadable)", flush=True)
            page += 1
            # keep going until we pass the known page count, else bail after a long gap
            if total_pages is not None and page > total_pages:
                break
            if total_pages is None and failed > 10:
                break
            continue
        if total_pages is None and data.get("count") is not None:
            total_pages = (int(data["count"]) + page_size - 1) // page_size
            print(f"  {status}: {data['count']} robots / {total_pages} pages", flush=True)
        batch = data.get("results") or []
        out.extend(batch)
        ok += 1
        if not data.get("next"):
            break
        page += 1
        if page > 400:
            break
    return out, ok, failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="append", choices=STATUSES)
    args = ap.parse_args()
    client = ResearchApiClient()

    kinds = Counter()
    by_status = Counter()
    by_company: defaultdict[str, list] = defaultdict(list)
    total = 0
    coverage: dict[str, dict] = {}
    for status in (args.status or STATUSES):
        rows, pages_ok, pages_failed = scan_status(client, status)
        total += len(rows)
        coverage[status] = {"scanned": len(rows), "pages_ok": pages_ok, "pages_failed": pages_failed}
        flag = "  *** PARTIAL — pages missed ***" if pages_failed else ""
        print(f"{status}: scanned {len(rows)} (pages ok={pages_ok} failed={pages_failed}){flag}", flush=True)
        for r in rows:
            kind = purpose_duplicates_description(
                (r.get("purpose") or "").strip(), (r.get("description") or "").strip()
            )
            if not kind:
                continue
            kinds[kind] += 1
            by_status[status] += 1
            comp = r.get("company") or r.get("company_name") or "?"
            if isinstance(comp, dict):
                comp = comp.get("name") or comp.get("slug") or "?"
            by_company[str(comp)].append({"id": int(r["id"]), "name": r.get("name"), "status": status, "kind": kind})

    bad = sum(kinds.values())
    missed = sum(c["pages_failed"] for c in coverage.values())
    print(f"\n=== DB-WIDE purpose==description ===")
    if missed:
        print(f"!!! COVERAGE INCOMPLETE — {missed} page(s) unreadable; count is a FLOOR, not a total")
    print(f"coverage: {coverage}")
    print(f"robots scanned: {total} | duplicates: {bad}")
    print("kinds:", dict(kinds))
    print("by status:", dict(by_status))
    print("\nby company (worst first):")
    for comp, items in sorted(by_company.items(), key=lambda kv: -len(kv[1])):
        print(f"  {comp[:38]:<39} {len(items)}")
    Path(_RD / "staging" / "reports").mkdir(parents=True, exist_ok=True)
    (_RD / "staging" / "reports" / "purpose-dupes-dbwide.json").write_text(
        json.dumps({"scanned": total, "duplicates": bad, "kinds": dict(kinds),
                    "by_company": {k: v for k, v in by_company.items()}}, indent=1, ensure_ascii=False),
        encoding="utf-8")
    print("\n-> staging/reports/purpose-dupes-dbwide.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
