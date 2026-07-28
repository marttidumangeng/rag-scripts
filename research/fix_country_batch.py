"""
fix_country_batch.py
--------------------
Fix missing manufacturer_countries for:
  - Wellwit Robotics (1423) → CN
  - Robotphoenix Technology Co., Ltd. (1474) → CN
  - Hikrobot (204) → CN

All three are Chinese manufacturers. This script patches every
pending_review robot in these companies that is missing manufacturer_countries.

Usage:
    python fix_country_batch.py --dry-run     # preview changes
    python fix_country_batch.py               # apply to production
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
load_research_env()

from api_client import ResearchApiClient

REPORT_DIR = _HERE / "staging" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Companies to fix: company_id → (company_name, country_code)
COMPANIES = {
    1423: ("Shenzhen Wellwit Robotics Co., Ltd.", "CN"),
    1474: ("Robotphoenix Technology Co., Ltd.", "CN"),
    204:  ("Hikrobot", "CN"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix manufacturer_countries for Wellwit, Robotphoenix, Hikrobot")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to production")
    parser.add_argument("--company-id", type=int, choices=list(COMPANIES.keys()), help="Only fix a specific company")
    args = parser.parse_args()

    client = ResearchApiClient()

    # Resolve CN country ID once
    print("Resolving country IDs...")
    cn_id = client.get_country_id("CN")
    print(f"  CN → id={cn_id}")
    if not cn_id:
        print("ERROR: Could not resolve CN country ID. Aborting.")
        sys.exit(1)

    companies_to_fix = {k: v for k, v in COMPANIES.items()
                        if args.company_id is None or k == args.company_id}

    total_fixed = total_skipped = total_failed = 0
    all_results = {}

    for company_id, (company_name, country_code) in companies_to_fix.items():
        country_id = cn_id  # all are CN for now
        print(f"\n{'='*60}")
        print(f"Company: {company_name} (id={company_id}) → {country_code} (id={country_id})")
        print(f"{'='*60}")

        robots = client.list_robots_for_company(company_id)
        print(f"Fetched {len(robots)} robots")

        fixed = skipped = failed = 0
        results_log = []

        for robot in robots:
            rid = robot["id"]
            name = robot.get("name", f"Robot {rid}")
            current_countries = robot.get("manufacturer_countries") or []

            if current_countries:
                print(f"  [{rid}] {name} — already has countries {current_countries}, skipping")
                skipped += 1
                results_log.append({"id": rid, "name": name, "status": "skipped"})
                continue

            patch = {"manufacturer_countries": [country_id]}

            print(f"  [{rid}] {name} — setting manufacturer_countries=[{country_id}] ({country_code})")

            if args.dry_run:
                print("    [DRY RUN] Would apply patch")
                fixed += 1
                results_log.append({"id": rid, "name": name, "status": "would_fix", "patch": patch})
                continue

            try:
                client._patch(f"robots/robots/{rid}/", patch)
                print(f"    ✓ Patched successfully")
                fixed += 1
                results_log.append({"id": rid, "name": name, "status": "fixed", "patch": patch})
            except Exception as exc:
                print(f"    ✗ FAILED: {exc}")
                failed += 1
                results_log.append({"id": rid, "name": name, "status": "failed", "error": str(exc)})

            time.sleep(0.15)

        print(f"\n  Company summary: Fixed={fixed} Skipped={skipped} Failed={failed}")
        total_fixed += fixed
        total_skipped += skipped
        total_failed += failed
        all_results[company_id] = {
            "company_name": company_name,
            "country_code": country_code,
            "fixed": fixed,
            "skipped": skipped,
            "failed": failed,
            "robots": results_log,
        }

    print(f"\n{'='*60}")
    print(f"{'[DRY RUN] ' if args.dry_run else ''}TOTAL SUMMARY")
    print(f"  Fixed:   {total_fixed}")
    print(f"  Skipped: {total_skipped}")
    print(f"  Failed:  {total_failed}")

    report_path = REPORT_DIR / "fix-country-batch.json"
    report_path.write_text(
        json.dumps({
            "summary": {"fixed": total_fixed, "skipped": total_skipped, "failed": total_failed},
            "companies": all_results,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
