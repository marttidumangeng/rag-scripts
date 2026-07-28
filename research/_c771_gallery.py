import requests, hashlib, os
from collections import defaultdict
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
from PIL import Image, ImageDraw
c=ResearchApiClient()
rs=[r for r in c.list_robots_for_company(771) if str(r.get("status") or "").lower()=="pending_review"]
rs.sort(key=lambda x:int(x["id"]))
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"; os.makedirs("staging/_jaka",exist_ok=True)
cache={}
def get(u):
    if u in cache: return cache[u]
    try:
        g=S.get(u,timeout=20); r=(g.content if g.ok else None, hashlib.sha256(g.content).hexdigest()[:10] if g.ok else None)
    except: r=(None,None)
    cache[u]=r; return r
hashrobots=defaultdict(set); hashbytes={}
for r in rs:
    rid=int(r["id"])
    urls=[]
    hero=r.get("s3_image") or r.get("image")
    if hero: urls.append(hero)
    for p in (r.get("photos") or r.get("images") or []):
        u=(p.get("s3_image") or p.get("url")) if isinstance(p,dict) else p
        if u: urls.append(u)
    for u in urls:
        content,h=get(u)
        if h: hashrobots[h].add(rid); hashbytes[h]=content
print("distinct image hashes across all pending galleries:", len(hashrobots))
print("\nhash -> #robots (shared across robots = defect):")
saved=[]
for h,ids in sorted(hashrobots.items(), key=lambda kv:-len(kv[1])):
    print(" ",h,"on",len(ids),"robots")
    if hashbytes.get(h):
        p="staging/_jaka/%s.img"%h; open(p,"wb").write(hashbytes[h]); saved.append((h+" x"+str(len(ids)),p))
# contact of distinct images
cell=240; cols=6; rows=(len(saved)+cols-1)//cols
sheet=Image.new("RGB",(cols*cell,max(rows,1)*cell),(240,240,244)); d=ImageDraw.Draw(sheet)
for i,(l,p) in enumerate(saved):
    x=(i%cols)*cell+6; y=(i//cols)*cell+22
    try:
        im=Image.open(p).convert("RGB"); im.thumbnail((cell-12,cell-30)); sheet.paste(im,(x,y)); d.text((x,y-14),l,fill=(0,0,0))
    except Exception as e: d.text((x,y),str(e)[:16],fill=(200,0,0))
sheet.save("staging/_jaka/_distinct.png"); print("\ndistinct images ->",len(saved),"staging/_jaka/_distinct.png")
