import requests, hashlib, json
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c = ResearchApiClient()
rs=[r for r in c.list_robots_for_company(1028) if str(r.get("status") or "").lower()=="pending_review"]
rs.sort(key=lambda x:int(x["id"]))
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
cache={}
def probe(u):
    if u in cache: return cache[u]
    try:
        g=S.get(u,timeout=20); r=(g.status_code, g.headers.get("Content-Type",""), len(g.content))
    except Exception as e: r=("ERR",str(e)[:20],0)
    cache[u]=r; return r
BROKEN=[]  # robots with broken/tiny photos
report={}
for r in rs:
    rid=int(r["id"])
    hero=r.get("s3_image") or r.get("image")
    hs=probe(hero) if hero else ("-","-",0)
    photos=[]
    for p in (r.get("photos") or r.get("images") or []):
        u=(p.get("s3_image") or p.get("url")) if isinstance(p,dict) else p
        st,ct,sz=probe(u)
        bad = (sz<2000) or (st!=200) or (not str(ct).startswith("image"))
        photos.append((u,sz,bad))
    nbad=sum(1 for _,_,b in photos if b)
    hero_bad = (hs[2]<2000) or (hs[0]!=200) or (not str(hs[1]).startswith("image"))
    if nbad or hero_bad:
        BROKEN.append(rid)
        print(f"{rid} {r['name'][:26]:<27} hero={'BAD' if hero_bad else 'ok'}({hs[2]}b) badphotos={nbad}/{len(photos)}")
    report[rid]={"hero_bad":hero_bad,"photos":[[u,sz,b] for u,sz,b in photos]}
print("\nrobots with broken hero or photos:", len(BROKEN))
json.dump(report, open("staging/reports/nl-photohealth.json","w"), indent=1)
