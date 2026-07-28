import requests, hashlib, re, sys
from collections import Counter, defaultdict
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
from validate_staging import purpose_duplicates_description
c=ResearchApiClient()
rs=c.list_robots_for_company(174)
print("company 174 total:", len(rs))
if rs: print("company:", rs[0].get("company") or rs[0].get("company_name"))
print("statuses:", dict(Counter(str(r.get("status") or "").lower() for r in rs)))
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
cache={}
def probe(u):
    if not u: return (None,0,"-")
    if u in cache: return cache[u]
    try:
        g=S.get(u,timeout=20); r=(hashlib.sha256(g.content).hexdigest()[:10] if g.ok else None, len(g.content), g.headers.get("Content-Type",""))
    except Exception as e: r=(None,0,"ERR")
    cache[u]=r; return r
TYPED=("payload_kg","reach_mm","weight_kg","width_mm","length_mm","height_mm","speed","dof","repeatability_mm","walking_speed","runtime_minutes","battery_wh")
LEG=("weight","width","length","height","runtime","battery_capacity","voltage","connectivity","sensors","materials","charging_type")
herohash=Counter(); photohash=defaultdict(set)
for r in sorted(rs, key=lambda x:int(x["id"])):
    st=str(r.get("status") or "").lower()
    rid=int(r["id"])
    hero=r.get("s3_image") or r.get("image")
    hh,hsz,hct=probe(hero)
    herohash[hh]+=1
    photos=r.get("photos") or r.get("images") or []
    ph=[]
    for p in photos:
        u=(p.get("s3_image") or p.get("url")) if isinstance(p,dict) else p
        h2,sz2,ct2=probe(u); ph.append((sz2,ct2,h2)); photohash[h2].add(rid)
    badphotos=sum(1 for sz2,ct2,_ in ph if sz2<2000 or not str(ct2).startswith("image"))
    vids=r.get("videos") or []
    specs=[f for f in TYPED+LEG if r.get(f) not in (None,"",[],{})]
    desc=(r.get("description") or "").strip(); purp=(r.get("purpose") or "").strip()
    mc=r.get("manufacturer_country") or (r.get("manufacturer_country_ref") or {}).get("name") if isinstance(r.get("manufacturer_country_ref"),dict) else r.get("manufacturer_country")
    dup=purpose_duplicates_description(purp,desc)
    print("\n=== %s id=%s [%s] ==="%(r.get("name"),rid,st))
    print(" url:", r.get("url"))
    print(" hero:", hero)
    print("   heroprobe: hash=%s %db %s | loads=%s"%(hh,hsz,hct, bool(hh and hsz>2000 and str(hct).startswith("image"))))
    print(" photos:%d (bad:%d) | videos:%d | tags:%d"%(len(photos),badphotos,len(vids),len(r.get("tags") or [])))
    print(" desc:%d chars | purpose_dup:%s | specs:%s"%(len(desc),dup or '-',specs or 'NONE'))
    print(" year:%s | avail:%s | country:%s | cats:%s | uses:%d"%(
        r.get("release_year"),(r.get("availability_status") or {}).get("key") if isinstance(r.get("availability_status"),dict) else None,
        mc, r.get("categories"), len(r.get("uses") or [])))
    for v in vids:
        vu=v.get("url") if isinstance(v,dict) else v; vt=v.get("title") if isinstance(v,dict) else ""
        print("   VID", vu, "|", vt)
print("\n=== HERO HASH FREQ ==="); [print("  ",h,"->",n) for h,n in herohash.most_common()]
print("=== SHARED GALLERY IMAGES (>1 robot) ==="); [print("  ",h,"on",sorted(ids)) for h,ids in photohash.items() if len(ids)>1]
