"""
audit_image_rights_flags.py
----------------------------
Finds all robots blocked by "image rights: review required" flags by querying
the RobotPhoto table directly via the Django ORM through a management command,
or alternatively via the admin content-queue API.

Since the photos endpoint is not exposed via the research API, this script
uses the admin API to query robots with rights_status=review_required photos.
"""
import os, sys, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

client = ResearchApiClient()

# Use the admin content-queue endpoint which supports rights_status filter
# Try fetching robots that have photos with review_required status
page = 1
flagged_robots = []

while True:
    try:
        resp = client._get("robots/robots/", params={
            "has_rights_flag": "review_required",
            "page_size": 200,
            "page": page,
        })
    except Exception:
        resp = None

    if not resp:
        # Try alternate param name
        try:
            resp = client._get("robots/robots/", params={
                "photo_rights_status": "review_required",
                "page_size": 200,
                "page": page,
            })
        except Exception as e:
            print(f"API error: {e}")
            break

    if isinstance(resp, dict):
        results = resp.get("results", [])
        has_next = bool(resp.get("next"))
    elif isinstance(resp, list):
        results = resp
        has_next = False
    else:
        break

    if not results:
        break
    flagged_robots.extend(results)
    if not has_next:
        break
    page += 1

if flagged_robots:
    by_company = defaultdict(list)
    for r in flagged_robots:
        company = r.get("company_name") or "Unknown"
        by_company[company].append({"id": r["id"], "name": r.get("name", "")})

    print(f"\nTotal robots with image rights flag: {len(flagged_robots)}\n")
    print(f"{'Company':<50} {'Count':>5}")
    print("-" * 57)
    for company, robots in sorted(by_company.items(), key=lambda x: -len(x[1])):
        print(f"{company:<50} {len(robots):>5}")
else:
    print("No robots found via API filter. Trying admin content-queue endpoint...")
    # Try the admin content-queue endpoint used by the moderation UI
    try:
        resp = client._get("admin/robots/robot/content-queue/api/", params={
            "rights_status": "review_required",
            "page_size": 200,
        })
        print(f"Admin API response type: {type(resp)}")
        print(json.dumps(resp, indent=2, ensure_ascii=False)[:2000] if resp else "Empty response")
    except Exception as e:
        print(f"Admin API error: {e}")
    
    print("\nFalling back to checking the RobotPhoto model via the robot detail endpoint...")
    # Check a sample of robots to find ones with review_required photos
    # by looking at the content-queue for all companies
    try:
        # Get all companies
        companies = client._get("robots/companies/", params={"page_size": 500})
        company_list = companies.get("results", companies) if isinstance(companies, dict) else companies
        print(f"Found {len(company_list)} companies. Checking each for flagged photos...")
        
        flagged_by_company = {}
        for company in company_list[:20]:  # Sample first 20
            cid = company.get("id")
            cname = company.get("name", f"Company {cid}")
            robots = client.list_robots_for_company(cid)
            for r in robots:
                photos = r.get("photos", [])
                flagged = [p for p in photos if p.get("rights_status") == "review_required"]
                if flagged:
                    if cname not in flagged_by_company:
                        flagged_by_company[cname] = []
                    flagged_by_company[cname].append({
                        "robot_id": r["id"],
                        "robot_name": r.get("name", ""),
                        "flagged_photos": len(flagged)
                    })
        
        if flagged_by_company:
            print(f"\nFound flagged robots in {len(flagged_by_company)} companies:")
            for cname, robots in sorted(flagged_by_company.items(), key=lambda x: -len(x[1])):
                print(f"  {cname}: {len(robots)} robots")
        else:
            print("No flagged photos found in sampled companies (photos may not be returned in list endpoint).")
    except Exception as e:
        print(f"Company scan error: {e}")
