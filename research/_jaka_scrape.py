import re, html as htmllib, json
from web_extract import WebFetcher
f = WebFetcher(stealth=False)
PAGES = {
 "Zu": "https://www.jaka.com/en_eu/productList/JAKA_Zu_Series",
 "S":  "https://www.jaka.com/en_eu/productList/JAKA_S_Series",
 "Pro":"https://www.jaka.com/en_eu/productList/JAKA_Pro_Series",
 "Mini":"https://www.jaka.com/en_eu/productList/JAKA_Mini_Series",
}
out={}
for lbl,url in PAGES.items():
    h=f.get(url) or ""
    imgs=[]
    for m in re.finditer(r'(?:src|data-src|data-original|content)="([^"]+?\.(?:jpg|jpeg|png|webp))"', h, re.I):
        u=htmllib.unescape(m.group(1))
        if u.startswith("//"): u="https:"+u
        if u.startswith("/"): u="https://www.jaka.com"+u
        if any(k in u.lower() for k in ("logo","icon","favicon","qrcode","qr_","/qr","sprite","wechat","weixin")): continue
        if u not in imgs: imgs.append(u)
    # model detail links
    links=list(dict.fromkeys(re.findall(r'href="(/en_eu/product[^"]*)"', h)))
    print("\n####",lbl,"(len",len(h),")")
    print(" imgs(%d):"%len(imgs))
    for u in imgs[:20]: print("   ",u)
    print(" product links:", links[:15])
    out[lbl]={"imgs":imgs,"links":links}
json.dump(out, open("staging/reports/jaka-scrape.json","w"), indent=1)
