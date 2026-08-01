"""Scope the remaining "No specs" / "No features" gap on the review queue.

Mirrors `robots/quality.py` exactly so the numbers line up with the flags a
reviewer actually sees:

  * missing_features (ERROR) — features blank
  * missing_specs   (WARN)  — EVERY field in quality.SPEC_FIELDS blank, typed
    numeric AND legacy string/JSON. A robot carrying only `voltage='24V DC'`
    is NOT missing specs; that is complete data in a legacy field.

Read-only. Splits the queue by whether the record came from this session's
gap-discovery import, because the fix differs: records whose SOURCE still has
structured data can be backfilled from it (as Hyundai just was), whereas older
records may have no recoverable source at all.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402

OUT = _HERE / "staging" / "reports" / "specs-features-gap.json"

# Verbatim from robots/quality.py SPEC_FIELDS — keep in sync or the counts here
# will disagree with the flags in the content queue.
SPEC_FIELDS = (
    "weight_kg", "width_mm", "length_mm", "height_mm", "speed", "walking_speed",
    "runtime_minutes", "battery_wh", "charging_time_minutes", "joint_torque_nm",
    "torque_density_nm_per_kg", "dof",
    "payload_kg", "reach_mm", "repeatability_mm",
    "weight", "width", "length", "height", "runtime", "battery_capacity",
    "charging_time", "voltage", "joint_torque", "torque_density", "connectivity",
    "sensors", "materials", "charging_type", "computation", "actuation_mechanism",
)


def blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, dict, tuple)):
        return len(v) == 0
    return False


def main() -> None:
    client = ResearchApiClient()
    rows: list[dict[str, Any]] = []
    page = 1
    print("fetching pending_review (full serializer) ...", flush=True)
    while True:
        for attempt in range(4):
            try:
                data = client._get("robots/robots/",
                                   params={"status": "pending_review",
                                           "page": page, "page_size": 50})
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        rows.extend(data.get("results", []))
        if page % 10 == 0:
            print(f"  {len(rows)} ...", flush=True)
        if not data.get("next"):
            break
        page += 1
    print(f"fetched {len(rows)}", flush=True)

    # This session's gap-discovery imports, by id range recorded in the ledger.
    staged = json.loads((_HERE / "staging" / "gap_discovery" / "staged_import.json")
                        .read_text(encoding="utf-8"))
    mine: set[int] = set()
    for e in staged.get("import_ledger", {}).get("imported", []):
        ids = e.get("robot_ids")
        if isinstance(ids, list):
            mine.update(int(i) for i in ids)
    # plus the Hyundai API ingest
    mine.update(range(6744, 6805))

    def bucket(r: dict[str, Any]) -> str:
        return "this_session_import" if r.get("id") in mine else "pre_existing"

    stats: dict[str, Counter] = {"this_session_import": Counter(), "pre_existing": Counter()}
    no_feat_by_company: Counter = Counter()
    no_spec_by_company: Counter = Counter()

    for r in rows:
        b = bucket(r)
        stats[b]["total"] += 1
        nf = blank(r.get("features"))
        ns = all(blank(r.get(f)) for f in SPEC_FIELDS)
        if nf:
            stats[b]["no_features"] += 1
        if ns:
            stats[b]["no_specs"] += 1
        if nf and ns:
            stats[b]["no_features_and_no_specs"] += 1
        co = (r.get("company_ref") or {})
        co_name = (co.get("name") if isinstance(co, dict) else None) or r.get("company") or "?"
        if nf:
            no_feat_by_company[co_name] += 1
        if ns:
            no_spec_by_company[co_name] += 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "status=pending_review",
        "pending_total": len(rows),
        "by_origin": {k: dict(v) for k, v in stats.items()},
        "top_companies_no_features": no_feat_by_company.most_common(20),
        "top_companies_no_specs": no_spec_by_company.most_common(20),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    for k, v in stats.items():
        t = v["total"] or 1
        print(f"\n{k}: {v['total']} robots")
        print(f"   no features : {v['no_features']:4} ({round(100*v['no_features']/t)}%)  [ERROR]")
        print(f"   no specs    : {v['no_specs']:4} ({round(100*v['no_specs']/t)}%)  [WARN]")
        print(f"   both        : {v['no_features_and_no_specs']:4}")
    print("\ntop companies missing FEATURES:")
    for n, c in no_feat_by_company.most_common(12):
        print(f"   {c:4}  {n[:52]}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
