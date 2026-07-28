"""Quick audit: print current name, model_name, family_name for all robots in company 1480."""
import sys
sys.path.insert(0, r"C:\Github_Personal\robot-ai-geek\scripts\research")

from api_client import ResearchApiClient

client = ResearchApiClient()
robots = client.list_robots_for_company(1480)
print(f"Total robots: {len(robots)}")
print()
for r in robots:
    rid = r.get("id", "?")
    name = (r.get("name") or "")
    model = (r.get("model_name") or "")
    family = (r.get("family_name") or "")
    url = (r.get("url") or "")
    print(f"ID={rid}")
    print(f"  name       : {name[:120]}")
    print(f"  model_name : {model[:80]}")
    print(f"  family_name: {family[:80]}")
    print(f"  url        : {url[:120]}")
    print()
