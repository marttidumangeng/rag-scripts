import requests, hashlib
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c = ResearchApiClient()
rs = c.list_robots_for_company(1028)
print("company 1028 total robots:", len(rs))
# company website?
if rs:
    r0=rs[0]
    print("company:", r0.get("company") or r0.get("company_name"), "| website hint:", r0.get("company_website"))
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
def hh(u):
    if not u: return ("-","-",0,"-")
    try:
        g=S.get(u,timeout=20); return (g.status_code, g.headers.get("Content-Type"), len(g.content), hashlib.sha256(g.content).hexdigest()[:10] if g.ok else "-")
    except Exception as e: return ("ERR",str(e)[:24],0,"-")
from collections import Counter
statuses=Counter(str(r.get("status") or "").lower() for r in rs)
print("statuses:", dict(statuses))
for r in sorted(rs, key=lambda x:int(x["id"])):
    st=str(r.get("status") or "").lower()
    if st not in ("pending_review","draft"): continue
    hero=r.get("s3_image") or r.get("image")
    photos=r.get("photos") or r.get("images") or []
    vids=r.get("videos") or []
    print("\n=== %s  id=%s  status=%s ==="%(r.get("name"),r["id"],st))
    print(" url:", r.get("url"))
    print(" hero:", hero)
    print("   hero probe:", hh(hero))
    print(" photos:", len(photos), "| videos:", len(vids), "| tags:", len(r.get("tags") or []))
    print(" year:", r.get("release_year"), "| mfr_country:", (r.get("manufacturer_country_ref") or {}).get("name") if isinstance(r.get("manufacturer_country_ref"),dict) else r.get("manufacturer_country"))
    print(" categories:", r.get("categories"))
    for v in vids:
        vu=v.get("url") if isinstance(v,dict) else v; vt=v.get("title") if isinstance(v,dict) else ""
        print("   VID", vu, "|", vt)
