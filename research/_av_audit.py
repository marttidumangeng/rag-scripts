import sys, json, requests
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c = ResearchApiClient()
rs = c.list_robots_for_company(283)
print("total robots:", len(rs))
S = requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
def img_ok(u):
    if not u: return False
    try:
        g=S.get(u,timeout=20); return g.ok and g.headers.get("Content-Type","").startswith("image") and len(g.content)>3000
    except Exception: return False
for r in sorted(rs, key=lambda x:int(x["id"])):
    st=str(r.get("status") or "").lower()
    if st not in ("pending_review","draft"):
        continue
    photos=r.get("photos") or r.get("images") or []
    hero=r.get("s3_image") or r.get("image")
    nphoto=len(photos)+(1 if hero and not any((p.get("url")==hero or p.get("s3_image")==hero) if isinstance(p,dict) else p==hero for p in photos) else 0)
    heroload=img_ok(hero)
    feat=(r.get("features") or "")
    vids=r.get("videos") or []
    tags=r.get("tags") or []
    print("\n=== %s  id=%s  status=%s ==="%(r.get("name"),r["id"],st))
    print(" url:", r.get("url"))
    print(" hero:", hero, "| loads:", heroload)
    print(" photos count:", len(photos), "| tags:", len(tags), "| videos:", len(vids))
    print(" release_year:", r.get("release_year"), "| availability:", r.get("availability_status") or r.get("availability"))
    print(" country:", r.get("country"), "| categories:", r.get("categories"), "| uses:", r.get("uses"))
    print(" dof:", r.get("dof"), "wt:", r.get("weight_kg"), "L:", r.get("length_mm"), "W:", r.get("width_mm"), "H:", r.get("height_mm"), "speed:", r.get("speed"))
    print(" features[:160]:", feat[:160].replace("\n"," "))
    print(" price:", r.get("price"))
