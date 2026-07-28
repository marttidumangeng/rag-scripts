"""Deep image dump for the weak FANUC pages: pull EVERY cdn.craft image (+og:image, picture/source, webp) so we can pick a clean render."""
import html as htmllib, os, re, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import requests
from web_extract import WebFetcher

PAGES = {
    "M-2iA (4101/4102)": "https://www.fanucamerica.com/products/robots/series/m-2ia",
    "R-2000iD (4109-4113)": "https://www.fanucamerica.com/products/robots/series/r-2000",
    "SR-12iA (4122)": "https://www.fanucamerica.com/products/robots/series/sr",
}
f = WebFetcher(stealth=False)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
os.makedirs("staging/_fdeep", exist_ok=True)
REJECT = ("navigation/", "case-studies", "logo", "icon", "sprite", "favicon",
          "cnc-controls", "robodrill", "roboshot", "robocut", "placeholder", "-header", "banner", "case-study")
paths = []
for label, url in PAGES.items():
    h = f.get(url) or ""
    seen = []
    # any cdn.craft image, any ext, plus og:image
    for m in re.finditer(r'https://cdn\.craft\.cloud/[^"\')\s]+?\.(?:png|jpg|jpeg|webp)', h, re.I):
        img = htmllib.unescape(m.group(0)); low = img.lower()
        if any(k in low for k in REJECT):
            continue
        if img not in seen:
            seen.append(img)
    print(f"\n### {label}  ({len(seen)} imgs)")
    for i, im in enumerate(seen[:14]):
        print(f"   {i:2} {im.split('/')[-1]}")
        try:
            resp = S.get(im, timeout=40)
            if resp.ok and resp.headers.get("Content-Type", "").startswith("image") and len(resp.content) > 6000:
                ext = "webp" if im.lower().endswith("webp") else "png"
                p = f"staging/_fdeep/{label.split()[0]}_{i}.{ext}"
                open(p, "wb").write(resp.content); paths.append((f"{label.split()[0]} #{i}", p, im))
        except Exception:
            pass
    time.sleep(0.3)

# contact sheet
try:
    from PIL import Image, ImageDraw
    cell = 240; cols = 7; rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols*cell, max(rows,1)*cell), (240,240,244)); d = ImageDraw.Draw(sheet)
    for i,(label,p,_u) in enumerate(paths):
        try:
            im = Image.open(p).convert("RGB"); im.thumbnail((cell-12, cell-30))
            x=(i%cols)*cell+6; y=(i//cols)*cell+22; sheet.paste(im,(x,y)); d.text((x,y-14),label,fill=(0,0,0))
        except Exception: pass
    sheet.save("staging/_fdeep/_contact.png"); print("\ncontact -> staging/_fdeep/_contact.png")
except Exception as e:
    print("PIL", str(e)[:50])
import json
json.dump([{"label":l,"url":u} for l,_p,u in paths], open("staging/_fdeep/idx.json","w"), indent=2)
