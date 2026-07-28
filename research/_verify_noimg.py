import sys, hashlib, requests
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c = ResearchApiClient()
rs = c.list_robots_for_company(189)
by = {int(r["id"]): r for r in rs}
IDS = [4098,4099,4100,4101,4102,4103,4104,4105,4106,4107,4109,4110,4111,4112,4113,4114,4116,4118,4122,4123]
S = requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
ok = 0; bad = []
seen = {}
for rid in IDS:
    r = by.get(rid)
    u = (r.get("s3_image") or r.get("image")) if r else None
    if not u:
        bad.append((rid, "NO HERO")); continue
    try:
        g = S.get(u, timeout=30)
        good = g.ok and g.headers.get("Content-Type","").startswith("image") and len(g.content) > 6000
        h = hashlib.sha256(g.content).hexdigest()[:12] if good else "-"
    except Exception as e:
        good = False; h = str(e)[:20]
    owned = "cdn.robotaigeek.com" in (u or "")
    ng = len(r.get("photos") or r.get("images") or [])
    if good and owned:
        ok += 1
    else:
        bad.append((rid, f"owned={owned} good={good}"))
    seen.setdefault(h, []).append(rid)
    print(f"  {rid} {r['name'][:16]:<17} gallery={ng} sha={h} {'OK' if good and owned else 'CHECK'}")
print(f"\nheroes live+owned: {ok}/{len(IDS)}")
if bad:
    print("PROBLEMS:", bad)
dups = {h:ids for h,ids in seen.items() if len(ids)>1 and h!='-'}
print("shared-hero groups (expected within same series):")
for h,ids in dups.items():
    print(f"   {h}: {ids}")
