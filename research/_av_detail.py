import json, requests, hashlib
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c = ResearchApiClient()
rs = c.list_robots_for_company(283)
by = {int(r["id"]): r for r in rs}
S = requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
def info(u):
    try:
        g=S.get(u,timeout=20)
        return (g.status_code, g.headers.get("Content-Type"), len(g.content), hashlib.sha256(g.content).hexdigest()[:10] if g.ok else "-")
    except Exception as e:
        return ("ERR",str(e)[:30],0,"-")
paths=[]
for rid in (519,1506,1509,1510):
    r=by[rid]
    print("\n=== %s (%s) ==="%(r["name"],rid))
    hero=r.get("s3_image") or r.get("image")
    print(" HERO", hero, info(hero) if hero else "-")
    photos=r.get("photos") or r.get("images") or []
    for i,p in enumerate(photos):
        u=(p.get("s3_image") or p.get("url")) if isinstance(p,dict) else p
        print("  photo%d"%i, u, info(u))
    for v in (r.get("videos") or []):
        vu=v.get("url") if isinstance(v,dict) else v
        vt=v.get("title") if isinstance(v,dict) else ""
        print("  VID", vu, "|", vt)
