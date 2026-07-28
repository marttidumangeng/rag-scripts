"""
image_status_report_v2.py
==========================
Fast version: uses two bulk API calls only.
1. GET all robots with no image  (no_image=true, all pages)
2. GET all robots WITH image      (no_image=false, all pages)
Groups by company and computes coverage. Outputs image_status_data.json.

Run:
    python image_status_report_v2.py
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

OUTPUT = os.path.join(os.path.dirname(__file__), "staging", "reports", "image_status_data.json")


def fetch_all_robots(client, no_image: bool, page_size: int = 500) -> list[dict]:
    """Fetch all robots filtered by no_image flag, paginated."""
    results = []
    page = 1
    param_val = "true" if no_image else "false"
    label = "missing image" if no_image else "with image"
    while True:
        data = client._get(
            "robots/robots/",
            params={"no_image": param_val, "page": page, "page_size": page_size},
        )
        batch = data.get("results", [])
        results.extend(batch)
        total = data.get("count", "?")
        print(f"  [{label}] page {page}: {len(batch)} robots (total so far: {len(results)}/{total})")
        if not data.get("next"):
            break
        page += 1
        time.sleep(0.1)
    return results


def extract_company(robot: dict) -> tuple[int, str, str]:
    """Return (company_id, company_name, company_slug) from a robot record."""
    co = robot.get("company")
    if isinstance(co, dict):
        return co.get("id", 0), co.get("name", "Unknown"), co.get("slug", "")
    cid = robot.get("company_id", 0)
    return cid or 0, "Unknown", ""


def main():
    client = ResearchApiClient()

    print("Step 1: Fetching all robots missing an image...")
    no_image_robots = fetch_all_robots(client, no_image=True)
    print(f"  Total robots missing image: {len(no_image_robots)}\n")

    print("Step 2: Fetching all robots WITH an image...")
    with_image_robots = fetch_all_robots(client, no_image=False)
    print(f"  Total robots with image: {len(with_image_robots)}\n")

    # Build company map
    company_map: dict[int, dict] = {}

    def ensure_company(cid, cname, cslug):
        if cid not in company_map:
            company_map[cid] = {
                "id": cid,
                "name": cname,
                "slug": cslug,
                "robots_no_image": [],
                "robots_with_image": [],
            }
        # Update name/slug if we have better data
        if cname and cname != "Unknown":
            company_map[cid]["name"] = cname
        if cslug:
            company_map[cid]["slug"] = cslug

    for r in no_image_robots:
        cid, cname, cslug = extract_company(r)
        ensure_company(cid, cname, cslug)
        company_map[cid]["robots_no_image"].append({
            "id": r.get("id"),
            "name": r.get("name", ""),
            "model_name": r.get("model_name", "") or "",
            "status": r.get("status", ""),
        })

    for r in with_image_robots:
        cid, cname, cslug = extract_company(r)
        ensure_company(cid, cname, cslug)
        company_map[cid]["robots_with_image"].append({
            "id": r.get("id"),
            "name": r.get("name", ""),
        })

    # Compute per-company stats
    companies_out = []
    for cid, cdata in company_map.items():
        n_missing = len(cdata["robots_no_image"])
        n_with = len(cdata["robots_with_image"])
        total = n_missing + n_with
        pct = round(100 * n_with / total, 1) if total > 0 else 0.0
        companies_out.append({
            "id": cid,
            "name": cdata["name"],
            "slug": cdata["slug"],
            "total_robots": total,
            "robots_with_image": n_with,
            "robots_missing_image": n_missing,
            "image_coverage_pct": pct,
            "status": (
                "complete" if n_missing == 0
                else "all_missing" if n_with == 0
                else "partial"
            ),
            "missing_robots": cdata["robots_no_image"],
        })

    # Sort by missing count descending
    companies_out.sort(key=lambda c: c["robots_missing_image"], reverse=True)

    # Summary
    total_robots = len(no_image_robots) + len(with_image_robots)
    total_companies = len(companies_out)
    all_missing = sum(1 for c in companies_out if c["status"] == "all_missing")
    partial = sum(1 for c in companies_out if c["status"] == "partial")
    complete = sum(1 for c in companies_out if c["status"] == "complete")
    overall_pct = round(100 * len(with_image_robots) / total_robots, 1) if total_robots > 0 else 0

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC"),
        "total_robots": total_robots,
        "robots_with_image": len(with_image_robots),
        "robots_missing_image": len(no_image_robots),
        "overall_image_coverage_pct": overall_pct,
        "total_companies": total_companies,
        "companies_complete": complete,
        "companies_partial": partial,
        "companies_all_missing": all_missing,
    }

    output = {
        "summary": summary,
        "companies": companies_out,
    }

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Done. Output saved to: {OUTPUT}")
    print(f"\nSummary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
