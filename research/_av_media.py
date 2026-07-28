import re, json, html as htmllib
from web_extract import WebFetcher
f = WebFetcher(stealth=False)
PAGES = {
    "519 Wasp": "https://www.avinc.com/solution/wasp/",
    "1506 VigilantHalo": "https://www.avinc.com/solution/vigilanthalo/",
    "1509 Pro 5": "https://www.avinc.com/solution/pro-5/",
    "1510 Defender": "https://www.avinc.com/solution/defender/",
}
for label, url in PAGES.items():
    h = f.get(url) or ""
    ogi = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', h)
    wp = list(dict.fromkeys(re.findall(r'https://www\.avinc\.com/wp-content/uploads/[^"\')\s]+?\.(?:jpg|jpeg|png|webp)', h, re.I)))
    wp = [u for u in wp if not any(k in u.lower() for k in ("logo","icon","favicon","-150x","-thumb","menu"))]
    yt = list(dict.fromkeys(re.findall(r'(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=)|youtu\.be/)([A-Za-z0-9_-]{11})', h)))
    print("\n####", label)
    print(" og:image:", ogi.group(1) if ogi else None)
    print(" youtube:", yt[:8])
    print(" wp-images(%d):"%len(wp))
    for u in wp[:20]: print("    ", u)
