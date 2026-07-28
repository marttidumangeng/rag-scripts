import re, html as htmllib, json, sys
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
from web_extract import WebFetcher
c=ResearchApiClient()
# the rejected robots now under Xiaomi 115 (+ 2660 CyberDog2, 4362 Xiaomi Robotics)
rs=[r for r in c.list_robots_for_company(115) if str(r.get("status") or "").lower()=="rejected"]
f=WebFetcher(stealth=True)
out={}
for r in sorted(rs,key=lambda x:int(x["id"])):
    rid=int(r["id"]); url=(r.get("url") or "").strip()
    h=f.get(url) or ""
    ogi=re.search(r'property="og:image"[^>]+content="([^"]+)"',h) or re.search(r'name="og:image"[^>]+content="([^"]+)"',h)
    imgs=list(dict.fromkeys(re.findall(r'https://[^"\')\s]*appmifile[^"\')\s]+?\.(?:jpg|jpeg|png|webp)',h,re.I)))
    imgs=[u for u in imgs if not any(k in u.lower() for k in ("logo","icon","-100","-64","avatar","flag"))]
    # specs: suction Pa, battery mAh, runtime
    text=htmllib.unescape(re.sub(r"<[^>]+>","\n",re.sub(r"<script[\s\S]*?</script>"," ",h)))
    pa=re.findall(r'([\d,]{3,6})\s*Pa',text); mah=re.findall(r'([\d,]{3,6})\s*mAh',text); mins=re.findall(r'(\d{2,3})\s*min',text)
    out[rid]={"name":r.get("name"),"url":url,"og":ogi.group(1) if ogi else None,"imgs":imgs[:6],
              "pa":pa[:3],"mah":mah[:2],"mins":mins[:2]}
    print("%d %-30s og=%s imgs=%d pa=%s mah=%s"%(rid,r.get("name")[:30],bool(ogi),len(imgs),pa[:1],mah[:1]))
json.dump(out, open("staging/reports/xiaomi-vac.json","w",encoding="utf-8"), indent=1, ensure_ascii=False)
print("saved",len(out))
