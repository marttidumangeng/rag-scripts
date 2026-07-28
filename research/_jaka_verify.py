import requests, hashlib, os
from collections import Counter, defaultdict
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
from PIL import Image, ImageDraw
c=ResearchApiClient()
rs=[r for r in c.list_robots_for_company(771) if str(r.get("status") or "").lower()=="pending_review"]
rs.sort(key=lambda x:int(x["id"]))
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"; os.makedirs("staging/_jkv",exist_ok=True)
QR={"f479bc41bd","5ae5feb91a","75eae86858","45a5021f9a"}  # the 4 QR hashes
LINEUP="98cddfc432"
herohash=Counter(); allhash=defaultdict(set); paths=[]
def sha(u):
    try:
        g=S.get(u,timeout=25); return (g.content, hashlib.sha256(g.content).hexdigest()[:10])
    except: return (None,None)
for r in rs:
    rid=int(r["id"]); hero=r.get("s3_image") or r.get("image")
    content,h=sha(hero); herohash[h]+=1
    if content:
        p="staging/_jkv/%d.img"%rid; open(p,"wb").write(content); paths.append((r["name"].replace("JAKA","").strip()+" "+(h or ""),p))
    for pp in (r.get("photos") or r.get("images") or []):
        u=(pp.get("s3_image") or pp.get("url")) if isinstance(pp,dict) else pp
        _,ph=sha(u); allhash[ph].add(rid)
print("HERO hashes (want all distinct):")
for h,n in herohash.most_common(): print("  ",h,"->",n,"robots")
print("distinct heroes:",len(herohash),"/",len(rs))
qr_left=[h for h in allhash if h in QR]; lineup_left=LINEUP in allhash
print("QR codes remaining:",qr_left)
print("lineup remaining:",lineup_left)
cell=250; cols=6; rows=(len(paths)+cols-1)//cols
sheet=Image.new("RGB",(cols*cell,max(rows,1)*cell),(240,240,244)); d=ImageDraw.Draw(sheet)
for i,(l,p) in enumerate(paths):
    x=(i%cols)*cell+6; y=(i//cols)*cell+22
    try:
        im=Image.open(p).convert("RGB"); im.thumbnail((cell-12,cell-30)); sheet.paste(im,(x,y)); d.text((x,y-14),l,fill=(0,0,0))
    except Exception as e: d.text((x,y),str(e)[:14],fill=(200,0,0))
sheet.save("staging/_jkv/_heroes.png"); print("-> staging/_jkv/_heroes.png")
