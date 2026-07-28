import os, requests, hashlib
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
from PIL import Image, ImageDraw
c = ResearchApiClient()
rs = [r for r in c.list_robots_for_company(1028) if str(r.get("status") or "").lower()=="pending_review"]
rs.sort(key=lambda x:int(x["id"]))
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
os.makedirs("staging/_nl", exist_ok=True)
items=[]; hashes={}
for r in rs:
    hero=r.get("s3_image") or r.get("image")
    lbl="%s %s"%(r["id"], (r.get("name") or "").replace("Noblelift","").strip()[:20])
    p=None
    try:
        g=S.get(hero,timeout=25)
        if g.ok:
            h=hashlib.sha256(g.content).hexdigest()[:8]; hashes.setdefault(h,[]).append(r["id"])
            sz=len(g.content)
            p="staging/_nl/%s.img"%r["id"]; open(p,"wb").write(g.content)
            if sz<2000: lbl+=" [TINY %db]"%sz
    except Exception as e:
        lbl+=" [ERR]"
    items.append((lbl,p))
# sheet
cell=210; cols=8; rows=(len(items)+cols-1)//cols
sheet=Image.new("RGB",(cols*cell,rows*cell),(238,238,242)); d=ImageDraw.Draw(sheet)
for i,(lbl,p) in enumerate(items):
    x=(i%cols)*cell+5; y=(i//cols)*cell+22
    if p:
        try:
            im=Image.open(p).convert("RGB"); im.thumbnail((cell-12,cell-32)); sheet.paste(im,(x,y))
        except Exception: d.text((x,y),"decode-err",fill=(200,0,0))
    d.text((x,y-16),lbl,fill=(0,0,0))
sheet.save("staging/_nl/_contact.png")
print("robots:",len(items),"-> staging/_nl/_contact.png")
print("\nSHARED heroes (same content hash on multiple robots):")
for h,ids in sorted(hashes.items(), key=lambda kv:-len(kv[1])):
    if len(ids)>1: print(" ",h, ids)
