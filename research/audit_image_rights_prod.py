"""
audit_image_rights_prod.py
---------------------------
Queries the PRODUCTION API for robots with photos flagged as
rights_status='review_required', grouped by company.

Explicitly loads credentials from robotaigeek-server/.env so it
always hits production regardless of shell environment state.
"""
import os, sys, json, re
from collections import defaultdict
from pathlib import Path

# ── Load .env from robotaigeek-server ──────────────────────────────────────
env_path = Path(__file__).resolve().parents[2] / "robotaigeek-server" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

client = ResearchApiClient()
print(f"Using API base: {client.base_url}")

# ── Fetch all robots, paginated ─────────────────────────────────────────────
# The robots endpoint doesn't expose a rights_status filter, so we fetch all
# robots and use the admin content-queue endpoint to find flagged ones.
# Strategy: use the bulk-import media admin endpoint which lists photos with
# rights_status. We'll call /admin/robots/robot/content-queue/api/ with the
# rights_status filter.

flagged_by_company = defaultdict(list)
total_photos = 0

# Try the admin content-queue API
try:
    resp = client._get(
        "admin/robots/robot/content-queue/api/image-rights/",
        params={"rights_status": "review_required", "page_size": 500}
    )
    print(f"Admin image-rights API response: {type(resp)}")
    if resp:
        print(json.dumps(resp, indent=2, ensure_ascii=False)[:1000])
except Exception as e:
    print(f"Admin image-rights API not found: {e}")

# Fallback: scan all robots for photos with review_required
# Fetch robots with content gaps (these are most likely to have flagged photos)
print("\nScanning all robots for flagged photos via robot list endpoint...")
page = 1
all_robots = []
while True:
    try:
        resp = client._get("robots/robots/", params={"page_size": 200, "page": page})
    except Exception as e:
        print(f"Error on page {page}: {e}")
        break
    if isinstance(resp, dict):
        results = resp.get("results", [])
        has_next = bool(resp.get("next"))
    elif isinstance(resp, list):
        results = resp
        has_next = False
    else:
        break
    all_robots.extend(results)
    print(f"  Fetched page {page} ({len(results)} robots, total so far: {len(all_robots)})")
    if not has_next:
        break
    page += 1

print(f"\nTotal robots fetched: {len(all_robots)}")

# Check each robot's photos for rights_status
for robot in all_robots:
    photos = robot.get("photos", [])
    flagged = [p for p in photos if p.get("rights_status") == "review_required"]
    if flagged:
        total_photos += len(flagged)
        company = robot.get("company_name") or "Unknown"
        flagged_by_company[company].append({
            "robot_id": robot["id"],
            "robot_name": robot.get("name", ""),
            "flagged_count": len(flagged),
        })

print(f"\nTotal photos with rights_status=review_required: {total_photos}")
print(f"Unique robots affected: {sum(len(v) for v in flagged_by_company.values())}")
print(f"Companies affected: {len(flagged_by_company)}\n")

if flagged_by_company:
    print(f"{'Company':<50} {'Robots':>7}")
    print("-" * 59)
    for company, robots in sorted(flagged_by_company.items(), key=lambda x: -len(x[1])):
        print(f"{company:<50} {len(robots):>7}")
    print("\nFull breakdown:")
    for company, robots in sorted(flagged_by_company.items(), key=lambda x: -len(x[1])):
        print(f"\n  {company}:")
        for r in robots:
            print(f"    - [{r['robot_id']}] {r['robot_name']} ({r['flagged_count']} flagged photo(s))")
else:
    print("No robots with flagged photos found in the robot list response.")
    print("Note: photos[] may not be included in the list endpoint — try the detail endpoint.")

# Save report
out = Path(__file__).parent / "staging" / "reports" / "image_rights_flagged_prod.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({
    "api_base": client.base_url,
    "total_photos": total_photos,
    "by_company": {k: v for k, v in sorted(flagged_by_company.items(), key=lambda x: -len(x[1]))}
}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nReport saved to: {out}")
