import requests, hashlib
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c = ResearchApiClient()
by = {int(r["id"]): r for r in c.list_robots_for_company(283)}
S = requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
def h(u):
    try:
        g=S.get(u,timeout=30); return (g.status_code, g.headers.get("Content-Type"), len(g.content), hashlib.sha256(g.content).hexdigest()[:10] if g.ok else "-")
    except Exception as e: return ("ERR",str(e)[:30],0,"-")
# reference hashes
AVINC = h("https://www.avinc.com/wp-content/uploads/2026/03/Product-Page_UMV_Pro-5_Hero.jpg")
VHALO_BAD = "76798a4e86"  # the VigilantHalo shelter webp that was wrongly Pro5's hero
print("AVINC Pro5 render hash:", AVINC)
for rid in (1506,1509,1510):
    r=by[rid]
    hero=r.get("s3_image") or r.get("image")
    hh=h(hero)
    photos=r.get("photos") or r.get("images") or []
    print("\n%s (%s)"%(r["name"],rid))
    print("  hero:", hero)
    print("  hero probe:", hh, "IS-OLD-VHALO!" if hh[3]==VHALO_BAD else "")
    print("  gallery:", len(photos), "| videos:", len(r.get("videos") or []))
    print("  dims L/W/H:", r.get("length_mm"), r.get("width_mm"), r.get("height_mm"), "wt:", r.get("weight_kg"), "conn:", r.get("connectivity"))
