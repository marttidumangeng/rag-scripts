"""
image_status_report.py
=======================
Collects image status for every robot in the database, grouped by company.
Outputs a JSON file: image_status_data.json

Run:
    python image_status_report.py
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

OUTPUT = os.path.join(os.path.dirname(__file__), "staging", "reports", "image_status_data.json")

def main():
    client = ResearchApiClient()

    print("Fetching all robots with no image (paginated)...")
    no_image_robots = client.list_robots_missing_image(page_size=200)
    print(f"  Robots missing image: {len(no_image_robots)}")

    # Build a set of robot IDs with no image
    no_image_ids = {r["id"] for r in no_image_robots}

    # Also collect company-level data from the no-image list
    company_map = {}  # company_id -> {name, slug, robots_no_image: [], robots_with_image_count: 0}

    for r in no_image_robots:
        co = r.get("company") or {}
        cid = co.get("id") if isinstance(co, dict) else r.get("company_id")
        cname = co.get("name", "") if isinstance(co, dict) else ""
        cslug = co.get("slug", "") if isinstance(co, dict) else ""
        if not cid:
            cid = 0
            cname = "Unknown"
            cslug = "unknown"
        if cid not in company_map:
            company_map[cid] = {
                "id": cid,
                "name": cname,
                "slug": cslug,
                "robots_no_image": [],
                "robots_with_image_count": 0,
                "total_robots": 0,
            }
        company_map[cid]["robots_no_image"].append({
            "id": r.get("id"),
            "name": r.get("name", ""),
            "model_name": r.get("model_name", "") or "",
            "status": r.get("status", ""),
        })

    print(f"  Companies with at least one missing image: {len(company_map)}")

    # Now fetch total robot count per company for those companies
    # to compute coverage percentage
    print("Fetching total robot counts per company...")
    for i, (cid, cdata) in enumerate(company_map.items()):
        if cid == 0:
            continue
        try:
            robots = client.list_robots_for_company(cid, page_size=200)
            total = len(robots)
            with_image = sum(1 for r in robots if r.get("image") or r.get("image_url") or r.get("photos"))
            cdata["total_robots"] = total
            cdata["robots_with_image_count"] = with_image
        except Exception as e:
            print(f"  Warning: could not fetch robots for company {cid} ({cdata['name']}): {e}")
            cdata["total_robots"] = len(cdata["robots_no_image"])
            cdata["robots_with_image_count"] = 0
        if (i + 1) % 20 == 0:
            print(f"  Progress: {i+1}/{len(company_map)} companies processed...")
        time.sleep(0.15)

    # Compute summary stats
    total_companies = len(company_map)
    total_robots_no_image = sum(len(c["robots_no_image"]) for c in company_map.values())
    total_robots_checked = sum(c["total_robots"] for c in company_map.values())
    companies_all_missing = sum(
        1 for c in company_map.values()
        if c["total_robots"] > 0 and c["robots_with_image_count"] == 0
    )
    companies_partial = sum(
        1 for c in company_map.values()
        if c["total_robots"] > 0 and 0 < c["robots_with_image_count"] < c["total_robots"]
    )

    # Sort companies by number of missing images descending
    sorted_companies = sorted(
        company_map.values(),
        key=lambda c: len(c["robots_no_image"]),
        reverse=True
    )

    output = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC"),
        "summary": {
            "total_companies_with_missing_images": total_companies,
            "total_robots_missing_image": total_robots_no_image,
            "total_robots_checked": total_robots_checked,
            "companies_all_missing": companies_all_missing,
            "companies_partial_missing": companies_partial,
        },
        "companies": sorted_companies,
    }

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Output saved to: {OUTPUT}")
    print(f"Summary:")
    print(f"  Companies with missing images: {total_companies}")
    print(f"  Robots missing image:          {total_robots_no_image}")
    print(f"  Companies with ALL missing:    {companies_all_missing}")
    print(f"  Companies with PARTIAL:        {companies_partial}")

if __name__ == "__main__":
    main()
