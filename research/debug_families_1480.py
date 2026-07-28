"""Print all robots for company 1480 that have a non-empty family_name."""
import sys
sys.path.insert(0, r"C:\Github_Personal\robot-ai-geek\scripts\research")
from api_client import ResearchApiClient

client = ResearchApiClient()
robots = client.list_robots_for_company(1480)
print(f"Total: {len(robots)}")
for r in robots:
    fam = (r.get("family_name") or "").strip()
    if fam:
        print(f"  ID={r['id']} | name={r.get('name','')[:60]} | family={fam[:80]}")
