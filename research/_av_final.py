import re, requests, hashlib
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
CJK=re.compile(r'[㐀-䶿一-鿿豈-﫿぀-ヿ가-힯]')
c=ResearchApiClient(); by={int(r['id']):r for r in c.list_robots_for_company(283)}
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0'
def ok(u):
    try:
        g=S.get(u,timeout=25); return g.ok and g.headers.get('Content-Type','').startswith('image') and len(g.content)>3000
    except: return False
TYPED=("weight_kg","width_mm","length_mm","height_mm","speed","dof","payload_kg","reach_mm")
LEG=("weight","width","length","height","runtime","voltage","connectivity","sensors","materials","charging_type","battery_capacity")
for rid in (519,1506,1509,1510):
    r=by[rid]; f=[]
    desc=(r.get('description') or '').strip(); purp=(r.get('purpose') or '').strip()
    hero=r.get('s3_image') or r.get('image')
    photos=r.get('photos') or r.get('images') or []
    vids=r.get('videos') or []
    if CJK.search(desc) or CJK.search(purp): f.append('non_english(ERR)')
    if len(photos)<4: f.append('few_photos(%d)'%len(photos))
    if not (r.get('features') or '').strip(): f.append('missing_features(ERR)')
    if not purp: f.append('missing_purpose')
    if r.get('release_year') is None: f.append('missing_release_year')
    specs=[k for k in TYPED+LEG if r.get(k) not in (None,'',[],{})]
    if not specs: f.append('missing_specs')
    if len(vids)==0: f.append('missing_video')
    heroload=ok(hero)
    print("\n%s (%s)"%(r['name'],rid))
    print("  url:", r.get('url'))
    print("  hero loads:", heroload, "| photos:", len(photos), "| videos:", len(vids))
    print("  year:", r.get('release_year'), "| specs_set:", specs[:6])
    print("  desc EN:", not CJK.search(desc), "| purpose EN:", not CJK.search(purp))
    print("  REMAINING FLAGS (excl price):", f if f else "NONE")
