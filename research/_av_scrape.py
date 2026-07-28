import sys, re, json, html as htmllib
from web_extract import WebFetcher
f = WebFetcher(stealth=False)
PAGES = {
    "519 Wasp": "https://www.avinc.com/solution/wasp/",
    "1506 VigilantHalo": "https://www.avinc.com/solution/vigilanthalo/",
    "1509 Pro 5": "https://www.avinc.com/solution/pro-5/",
    "1510 Defender": "https://www.avinc.com/solution/defender/",
}
out = {}
for label, url in PAGES.items():
    h = f.get(url) or ""
    # images
    imgs = []
    for m in re.finditer(r'(?:src|data-src|data-lazy-src)="(https://[^"]+?\.(?:jpg|jpeg|png|webp))"', h, re.I):
        u = htmllib.unescape(m.group(1))
        if u not in imgs and not any(k in u.lower() for k in ("logo","icon","favicon","sprite","placeholder")):
            imgs.append(u)
    # youtube
    yt = list(dict.fromkeys(re.findall(r'(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)([A-Za-z0-9_-]{11})', h)))
    # og:title / meta desc
    ogt = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', h)
    ogd = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', h)
    # spec-ish lines: look for pairs like "Wingspan 3.3 ft" / table rows / dl
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", h)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = htmllib.unescape(text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    spec_hits = []
    KEYS = ("wingspan","weight","length","width","height","endurance","range","speed","depth","payload",
            "diameter","operating","altitude","thruster","knot","meter","kg","lb","ft","cm","mm","hour","min")
    for i, l in enumerate(lines):
        ll = l.lower()
        if any(k in ll for k in KEYS) and len(l) < 90:
            spec_hits.append(l)
    out[label] = {"url": url, "og_title": ogt.group(1) if ogt else None,
                  "desc": (ogd.group(1) if ogd else "")[:300],
                  "imgs": imgs[:14], "youtube": yt[:8], "spec_lines": spec_hits[:40]}
    print("\n#### %s"%label)
    print(" og:", out[label]["og_title"])
    print(" desc:", out[label]["desc"])
    print(" imgs(%d):"%len(imgs))
    for u in imgs[:14]: print("    ", u)
    print(" youtube:", yt[:8])
    print(" spec_lines:")
    for s in spec_hits[:40]: print("    |", s)
json.dump(out, open("staging/reports/av-scrape.json","w",encoding="utf-8"), indent=2, ensure_ascii=False)
