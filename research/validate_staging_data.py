#!/usr/bin/env python3
"""
validate_staging_data.py
------------------------
Daily validation of critical robot data quality in the production database.
Checks all robots in 'pending_review' status (and optionally all statuses)
for missing or inadequate field values before they are approved.

Checks performed:
  ERROR level (must fix before approval):
    - manufacturer_countries empty
    - description shorter than 100 characters
    - no tags assigned
    - features empty
    - purpose empty

  WARNING level (should fix, will not block approval):
    - price_min and price_max both null
    - payload_kg null (for arm/cobot/industrial robots)
    - reach_mm null (for arm/cobot/industrial robots)
    - sub_category_slug not set
    - no video attached

Output:
  - Console summary grouped by company
  - JSON report written to staging/reports/validation-YYYY-MM-DD.json

Usage:
    python validate_staging_data.py                    # pending_review only
    python validate_staging_data.py --all-statuses     # all robots
    python validate_staging_data.py --company-id 1375  # single company
    python validate_staging_data.py --errors-only      # suppress warnings
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date
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

# Robot categories that are expected to have arm specs (payload, reach)
ARM_LIKE_CATEGORIES = {
    "manufacturing-industrial",
    "manufacturing-collaborative",
    "manufacturing-welding",
    "manufacturing-painting",
    "manufacturing-assembly",
    "manufacturing-palletizing",
    "manufacturing-scara",
    "manufacturing-delta",
}

# Movement types that are stationary arms (not mobile platforms)
STATIONARY_TYPES = {"stationary"}


def is_arm_like(robot: dict) -> bool:
    """Return True if this robot is expected to have payload/reach specs."""
    sub_cat = robot.get("sub_category_slug") or ""
    # movement_type_keys may be a list or comma-separated string
    movement_raw = robot.get("movement_type_keys") or robot.get("movement_types") or ""
    if isinstance(movement_raw, list):
        movement = " ".join(str(m) for m in movement_raw).lower()
    else:
        movement = str(movement_raw).lower()
    if sub_cat in ARM_LIKE_CATEGORIES:
        return True
    if "stationary" in movement and "mobile" not in movement:
        return True
    # Heuristic: name contains arm/cobot/robot arm keywords
    name = (robot.get("name") or "").lower()
    if any(kw in name for kw in ("cobot", "robot arm", "robotic arm", "manipulator", "scara", "delta robot")):
        return True
    return False


def validate_robot(robot: dict, errors_only: bool = False) -> list[dict]:
    """Return list of issue dicts for a single robot."""
    issues = []
    rid = robot["id"]
    name = robot.get("name", f"Robot {rid}")

    # ---- ERRORS ----
    countries = robot.get("manufacturer_countries") or []
    if not countries:
        issues.append({
            "id": rid, "name": name, "level": "ERROR",
            "field": "manufacturer_countries",
            "message": "No manufacturer country assigned",
        })

    desc = robot.get("description") or ""
    if len(desc) < 100:
        issues.append({
            "id": rid, "name": name, "level": "ERROR",
            "field": "description",
            "message": f"Description too short ({len(desc)} chars, minimum 100)",
        })

    # tags may be a list of strings or dicts
    tags_raw = robot.get("tags") or []
    tags = [t for t in tags_raw if t]  # filter out empty/None
    if not tags:
        issues.append({
            "id": rid, "name": name, "level": "ERROR",
            "field": "tags",
            "message": "No tags assigned",
        })

    # ---- ERRORS (continued) ----
    features = robot.get("features") or ""
    if not features:
        issues.append({
            "id": rid, "name": name, "level": "ERROR",
            "field": "features",
            "message": "Features field is empty",
        })

    purpose = robot.get("purpose") or ""
    if not purpose:
        issues.append({
            "id": rid, "name": name, "level": "ERROR",
            "field": "purpose",
            "message": "Purpose field is empty",
        })

    if errors_only:
        return issues

    # ---- WARNINGS ----

    price_min = robot.get("price_min")
    price_max = robot.get("price_max")
    if price_min is None and price_max is None:
        issues.append({
            "id": rid, "name": name, "level": "WARNING",
            "field": "price",
            "message": "No price information (price_min and price_max both null)",
        })

    if is_arm_like(robot):
        if robot.get("payload_kg") is None:
            issues.append({
                "id": rid, "name": name, "level": "WARNING",
                "field": "payload_kg",
                "message": "payload_kg is null for an arm/cobot robot",
            })
        if robot.get("reach_mm") is None:
            issues.append({
                "id": rid, "name": name, "level": "WARNING",
                "field": "reach_mm",
                "message": "reach_mm is null for an arm/cobot robot",
            })

    sub_cat = robot.get("sub_category_slug") or ""
    if not sub_cat:
        issues.append({
            "id": rid, "name": name, "level": "WARNING",
            "field": "sub_category_slug",
            "message": "No sub-category assigned",
        })

    # videos may be a list of dicts or linked_videos
    videos = (robot.get("videos") or []) + (robot.get("linked_videos") or [])
    if not videos:
        issues.append({
            "id": rid, "name": name, "level": "WARNING",
            "field": "videos",
            "message": "No video attached",
        })

    return issues


def fetch_robots(
    client: ResearchApiClient,
    company_id: int | None,
    all_statuses: bool,
) -> list[dict]:
    """Fetch robots from the API with appropriate filters."""
    results = []
    page = 1
    params: dict = {"page_size": 50}
    if company_id:
        params["company_ref"] = company_id
    if not all_statuses:
        params["status"] = "pending_review"

    while True:
        params["page"] = page
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                data = client._get("robots/robots/", params=params)
                break
            except Exception as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        else:
            raise last_exc

        batch = data.get("results") or []
        results.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1
        time.sleep(0.1)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily validation of robot data quality")
    parser.add_argument("--company-id", type=int, help="Validate only robots for this company")
    parser.add_argument("--all-statuses", action="store_true", help="Check all statuses, not just pending_review")
    parser.add_argument("--errors-only", action="store_true", help="Report only ERROR-level issues (suppress warnings)")
    args = parser.parse_args()

    client = ResearchApiClient()

    scope = "all statuses" if args.all_statuses else "pending_review"
    company_note = f" for company {args.company_id}" if args.company_id else ""
    print(f"Fetching robots ({scope}{company_note})...")

    robots = fetch_robots(client, args.company_id, args.all_statuses)
    print(f"Fetched {len(robots)} robots\n")

    all_issues: list[dict] = []
    by_company: dict[str, list[dict]] = defaultdict(list)

    for robot in robots:
        issues = validate_robot(robot, errors_only=args.errors_only)
        all_issues.extend(issues)
        # 'company' field is a plain string (company name) in the list API
        company_name = robot.get("company") or robot.get("company_name") or "Unknown"
        if isinstance(company_name, dict):
            company_name = company_name.get("name") or "Unknown"
        for issue in issues:
            issue["company"] = company_name
            by_company[company_name].append(issue)

    # ---- Console report ----
    errors = [i for i in all_issues if i["level"] == "ERROR"]
    warnings = [i for i in all_issues if i["level"] == "WARNING"]

    print("=" * 70)
    print(f"VALIDATION REPORT — {date.today().isoformat()}")
    print(f"Robots checked: {len(robots)}")
    print(f"Total issues:   {len(all_issues)}  (ERRORS: {len(errors)}, WARNINGS: {len(warnings)})")
    print("=" * 70)

    if not all_issues:
        print("\n✓ All robots pass validation — no issues found.")
    else:
        for company, issues in sorted(by_company.items()):
            company_errors = [i for i in issues if i["level"] == "ERROR"]
            company_warnings = [i for i in issues if i["level"] == "WARNING"]
            print(f"\n{company}  ({len(company_errors)} errors, {len(company_warnings)} warnings)")
            for issue in sorted(issues, key=lambda x: (x["level"], x["id"])):
                icon = "✗" if issue["level"] == "ERROR" else "⚠"
                print(f"  {icon} [{issue['id']}] {issue['name'][:40]:40s}  {issue['field']:25s}  {issue['message']}")

    # ---- JSON report ----
    today = date.today().isoformat()
    report = {
        "date": today,
        "scope": scope,
        "company_id_filter": args.company_id,
        "robots_checked": len(robots),
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "by_company": {
            company: {
                "errors": [i for i in issues if i["level"] == "ERROR"],
                "warnings": [i for i in issues if i["level"] == "WARNING"],
            }
            for company, issues in sorted(by_company.items())
        },
        "all_issues": all_issues,
    }
    report_path = REPORT_DIR / f"validation-{today}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nReport written to {report_path}")

    # Exit with non-zero code if there are errors (useful for CI/automated checks)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
