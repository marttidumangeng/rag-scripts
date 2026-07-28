from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
from collections import Counter
c = ResearchApiClient()
# scan company 283 + a few US companies for existing country strings
seen = Counter()
for cid in (283,):
    for r in c.list_robots_for_company(cid):
        mc = r.get("manufacturer_country") or r.get("country")
        if isinstance(mc, dict): mc = mc.get("name")
        seen[mc] += 1
        # also print the ref
print("company 283 country values:", dict(seen))
# print one robot's full country-related keys
r = c.list_robots_for_company(283)[0]
for k,v in r.items():
    if "countr" in k.lower():
        print(" key", k, "=", v)
