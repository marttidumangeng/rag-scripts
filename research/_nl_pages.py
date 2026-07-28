import re, html as htmllib, sys
from web_extract import WebFetcher
f = WebFetcher(stealth=False)
PAGES = {
 "3187 RT16P/20P AGV (itemid=651)": "https://www.noblelift.com/AGV/info.aspx?itemid=651&lcid=56",
 "3378 Counterbalanced Forklift (746)": "https://www.noblelift.com/wlbysb/info.aspx?itemid=746&lcid=63",
 "3379 Reach Truck (747)": "https://www.noblelift.com/wlbysb/info.aspx?itemid=747&lcid=63",
 "3332 PS20 spec-check (650)": "https://www.noblelift.com/AGV/info.aspx?itemid=650&lcid=51",
}
for lbl,url in PAGES.items():
    h = f.get(url) or ""
    imgs=[]
    for m in re.finditer(r'(?:src|data-src|data-original)="([^"]+?\.(?:jpg|jpeg|png|webp))"', h, re.I):
        u=htmllib.unescape(m.group(1))
        if u.startswith("/"): u="https://www.noblelift.com"+u
        if any(k in u.lower() for k in ("logo","icon","favicon","banner","sprite","weixin","qrcode","/ad/")): continue
        if u not in imgs: imgs.append(u)
    # spec table text
    txt=re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>"," ",h)
    txt=re.sub(r"<[^>]+>","\n",txt); txt=htmllib.unescape(txt)
    lines=[l.strip() for l in txt.splitlines() if l.strip()]
    specs=[l for l in lines if re.search(r"(kg|mm|km/h|载重|额定|capacity|load|lift|height|width|length|weight|voltage|battery|V\b|Ah)", l, re.I) and len(l)<70]
    print("\n#### %s  (len=%d)"%(lbl,len(h)))
    print(" imgs(%d):"%len(imgs))
    for u in imgs[:12]: print("   ",u)
    print(" spec-ish lines:")
    for s in specs[:25]: print("   |",s)
