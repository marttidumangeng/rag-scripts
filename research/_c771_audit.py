import requests, hashlib
from collections import Counter
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c = ResearchApiClient()
rs = c.list_robots_for_company(771)
print("company 771 total robots:", len(rs))
if rs:
    print("company:", rs[0].get("company") or rs[0].get("company_name"))
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
cache={}
def sha(u):
    if not u: return (None,0,"-")
    if u in cache: return cache[u]
    try:
        g=S.get(u,timeout=20); r=(hashlib.sha256(g.content).hexdigest()[:10] if g.ok else None, len(g.content), g.headers.get("Content-Type"))
    except Exception as e: r=(None,0,"ERR")
    cache[u]=r; return r
statuses=Counter(str(r.get("status") or "").lower() for r in rs)
print("statuses:", dict(statuses))
herohash=Counter()
for r in sorted(rs, key=lambda x:int(x["id"])):
    st=str(r.get("status") or "").lower()
    if st not in ("pending_review","draft"): continue
    hero=r.get("s3_image") or r.get("image")
    h,sz,ct=sha(hero)
    herohash[h]+=1
    photos=r.get("photos") or r.get("images") or []
    vids=r.get("videos") or []
    print("\n=== %s  id=%s  status=%s ==="%(r.get("name"),r["id"],st))
    print(" url:", r.get("url"))
    print(" hero:", hero)
    print("   herohash:", h, sz, ct)
    print(" photos:", len(photos), "| videos:", len(vids), "| tags:", len(r.get("tags") or []))
    print(" year:", r.get("release_year"), "| avail:", (r.get("availability_status") or {}).get("key") if isinstance(r.get("availability_status"),dict) else None, "| cats:", r.get("categories"))
print("\n=== HERO HASH FREQUENCY (shared-primary defect) ===")
for h,n in herohash.most_common():
    print(" ",h,"->",n,"robots")
