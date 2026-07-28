"""
image_status_report_v3.py
==========================
Fast approach:
1. Fetch all robots missing an image (746 robots, 8 pages — fast)
2. Load the existing content-queue-triage.json for total per-company robot counts
3. Merge the two to compute coverage per company
4. Output image_status_data.json

Run:
    python image_status_report_v3.py
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

TRIAGE_FILE = os.path.join(os.path.dirname(__file__), "staging", "reports", "content-queue-triage.json")
OUTPUT = os.path.join(os.path.dirname(__file__), "staging", "reports", "image_status_data.json")


def fetch_all_missing_image(client, page_size: int = 200) -> list[dict]:
    results = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={"no_image": "true", "page": page, "page_size": page_size},
        )
        batch = data.get("results", [])
        results.extend(batch)
        total = data.get("count", "?")
        print(f"  page {page}: {len(batch)} robots (total so far: {len(results)}/{total})")
        if not data.get("next"):
            break
        page += 1
        time.sleep(0.1)
    return results


def extract_company(robot: dict) -> tuple[int, str, str]:
    co = robot.get("company")
    if isinstance(co, dict):
        return co.get("id", 0), co.get("name", "Unknown"), co.get("slug", "")
    return 0, "Unknown", ""


def main():
    client = ResearchApiClient()

    print("Fetching all robots missing an image...")
    no_image_robots = fetch_all_missing_image(client)
    print(f"Total robots missing image: {len(no_image_robots)}\n")

    # Also get the total robot count from the API (just count, no data)
    print("Fetching total robot count...")
    total_data = client._get("robots/robots/", params={"page": 1, "page_size": 1})
    total_robots_db = total_data.get("count", 0)
    print(f"Total robots in database: {total_robots_db}\n")

    # Load triage file for per-company total counts
    company_totals = {}  # company_id -> {name, slug, total_robots}
    if os.path.exists(TRIAGE_FILE):
        print(f"Loading triage file: {TRIAGE_FILE}")
        with open(TRIAGE_FILE, encoding="utf-8") as f:
            triage = json.load(f)
        # triage is a list of company objects with robot_count
        companies_list = triage if isinstance(triage, list) else triage.get("companies", [])
        for c in companies_list:
            cid = c.get("company_id") or c.get("id")
            if cid:
                company_totals[int(cid)] = {
                    "name": c.get("company_name") or c.get("name", ""),
                    "slug": c.get("company_slug") or c.get("slug", ""),
                    "total_robots": c.get("robot_count") or c.get("total_robots") or 0,
                }
        print(f"Loaded {len(company_totals)} companies from triage file\n")
    else:
        print(f"Warning: triage file not found at {TRIAGE_FILE}\n")

    # Build company map from missing-image robots
    company_map: dict[int, dict] = {}

    for r in no_image_robots:
        cid, cname, cslug = extract_company(r)
        if cid not in company_map:
            company_map[cid] = {
                "id": cid,
                "name": cname,
                "slug": cslug,
                "robots_no_image": [],
            }
        if cname and cname != "Unknown":
            company_map[cid]["name"] = cname
        if cslug:
            company_map[cid]["slug"] = cslug
        company_map[cid]["robots_no_image"].append({
            "id": r.get("id"),
            "name": r.get("name", ""),
            "model_name": r.get("model_name", "") or "",
            "status": r.get("status", ""),
        })

    # Merge with triage totals
    companies_out = []
    for cid, cdata in company_map.items():
        n_missing = len(cdata["robots_no_image"])
        triage_info = company_totals.get(cid, {})
        total = triage_info.get("total_robots", 0) or n_missing
        # Use triage name/slug if we have it
        name = triage_info.get("name") or cdata["name"]
        slug = triage_info.get("slug") or cdata["slug"]
        n_with = max(0, total - n_missing)
        pct = round(100 * n_with / total, 1) if total > 0 else 0.0

        companies_out.append({
            "id": cid,
            "name": name,
            "slug": slug,
            "total_robots": total,
            "robots_with_image": n_with,
            "robots_missing_image": n_missing,
            "image_coverage_pct": pct,
            "status": (
                "complete" if n_missing == 0
                else "all_missing" if n_with == 0
                else "partial"
            ),
            "missing_robots": sorted(cdata["robots_no_image"], key=lambda x: x["name"]),
        })

    # Sort by missing count descending
    companies_out.sort(key=lambda c: c["robots_missing_image"], reverse=True)

    # Summary stats
    total_companies = len(companies_out)
    all_missing = sum(1 for c in companies_out if c["status"] == "all_missing")
    partial = sum(1 for c in companies_out if c["status"] == "partial")
    complete_count = sum(1 for c in companies_out if c["status"] == "complete")
    robots_with_image = total_robots_db - len(no_image_robots)
    overall_pct = round(100 * robots_with_image / total_robots_db, 1) if total_robots_db > 0 else 0

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC"),
        "total_robots_in_db": total_robots_db,
        "robots_with_image": robots_with_image,
        "robots_missing_image": len(no_image_robots),
        "overall_image_coverage_pct": overall_pct,
        "total_companies_with_missing_images": total_companies,
        "companies_all_missing": all_missing,
        "companies_partial": partial,
        "companies_complete_in_this_report": complete_count,
    }

    output = {
        "summary": summary,
        "companies": companies_out,
    }

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Done. Output saved to: {OUTPUT}")
    print("\nSummary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\nTop 10 companies by missing images:")
    for c in companies_out[:10]:
        print(f"  {c['name']}: {c['robots_missing_image']} missing / {c['total_robots']} total ({c['image_coverage_pct']}% covered)")


if __name__ == "__main__":
    main()
