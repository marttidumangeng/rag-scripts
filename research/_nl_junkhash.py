import requests, hashlib, json
from collections import defaultdict
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c=ResearchApiClient()
rs=[r for r in c.list_robots_for_company(1028) if str(r.get("status") or "").lower()=="pending_review"]
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
cache={}
def sha(u):
    if u in cache: return cache[u]
    try:
        g=S.get(u,timeout=20)
        h=(hashlib.sha256(g.content).hexdigest()[:10], len(g.content)) if g.ok else (None,0)
    except: h=(None,0)
    cache[u]=h; return h
hashrobots=defaultdict(set); hashsize={}
for r in rs:
    rid=int(r["id"])
    for p in (r.get("photos") or r.get("images") or []):
        u=(p.get("s3_image") or p.get("url")) if isinstance(p,dict) else p
        h,sz=sha(u);
        if h: hashrobots[h].add(rid); hashsize[h]=sz
# junk = images shared across many robots (>3) — likely logos/flags/icons
print("images shared across >2 robots (candidate shared junk):")
for h,ids in sorted(hashrobots.items(), key=lambda kv:-len(kv[1])):
    if len(ids)>2:
        print(" ",h,"size",hashsize[h],"on",len(ids),"robots:",sorted(ids)[:12])
json.dump({h:sorted(ids) for h,ids in hashrobots.items() if len(ids)>2}, open("staging/reports/nl-junkhash.json","w"),indent=1)
