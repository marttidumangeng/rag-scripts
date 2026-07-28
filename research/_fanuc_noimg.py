"""Scrape a real product render for each of the 22 no-image FANUC robots from its source page."""
import html as htmllib, os, re, sys, time, hashlib
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import requests
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
from web_extract import WebFetcher

c = ResearchApiClient()
robots = None
for a in range(12):
    try:
        robots = c.list_robots_for_company(189); break
    except Exception:
        time.sleep(5)
pend = [r for r in robots if str(r.get("status") or "").lower() == "pending_review"]
no_img = [r for r in pend if not (r.get("s3_image") or r.get("image"))]
print("no-image robots:", len(no_img))

f = WebFetcher(stealth=False)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
os.makedirs("staging/_fni", exist_ok=True)
REJECT = ("navigation/", "case-studies", "logo", "icon", "sprite", "favicon",
          "cnc-controls", "robodrill", "roboshot", "robocut", "placeholder", "-header", "banner")
out = {}
paths = []
for r in sorted(no_img, key=lambda x: x["id"]):
    u = (r.get("url") or "").strip()
    if not u:
        print(f"  {r['id']} {r['name']}: NO URL"); out[r["id"]] = []; continue
    h = f.get(u) or ""
    model = re.match(r"([A-Za-z]+-?\d+)", r["name"].replace("FANUC", "").strip())
    tok = (model.group(1).lower().replace("-", "") if model else "")
    imgs = []
    for m in re.finditer(r'(?:src|data-src)="(https://cdn\.craft\.cloud/[^"]+/assets/images/[^"?]+\.(?:png|jpg|jpeg))', h, re.I):
        img = htmllib.unescape(m.group(1)); low = img.lower()
        if any(k in low for k in REJECT):
            continue
        fn = low.split("/")[-1].replace("-", "").replace("_", "")
        # prefer filename that carries the model token; else any product image
        score = 0 if tok and tok in fn else 1
        imgs.append((score, img))
    imgs.sort()
    picked = [i for _, i in imgs][:2]
    out[r["id"]] = picked
    print(f"  {r['id']:<6}{r['name'][:24]:<25} -> {len(picked)} img(s)"
          + (f"  {picked[0].split('/')[-1][:44]}" if picked else "  NONE"))
    for i, im in enumerate(picked[:1]):
        try:
            resp = S.get(im, timeout=40)
            if resp.ok and resp.headers.get("Content-Type", "").startswith("image") and len(resp.content) > 8000:
                p = f"staging/_fni/{r['id']}_{i}.png"; open(p, "wb").write(resp.content); paths.append((str(r["id"]) + " " + r["name"][:14], p))
        except Exception:
            pass
    time.sleep(0.2)

import json
json.dump(out, open("staging/reports/fanuc-noimg.json", "w", encoding="utf-8"), indent=2)
have = sum(1 for v in out.values() if v)
print(f"\nrobots with a candidate render: {have}/{len(no_img)}")
try:
    from PIL import Image, ImageDraw
    cell = 260; cols = 6; rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, max(rows, 1) * cell), (238, 238, 242)); d = ImageDraw.Draw(sheet)
    for i, (label, p) in enumerate(paths):
        try:
            im = Image.open(p).convert("RGB"); im.thumbnail((cell - 12, cell - 32))
            x = (i % cols) * cell + 6; y = (i // cols) * cell + 24
            sheet.paste(im, (x, y)); d.text((x, y - 16), label[:30], fill=(0, 0, 0))
        except Exception:
            pass
    sheet.save("staging/_fni/_contact.png"); print("contact -> staging/_fni/_contact.png")
except Exception as e:
    print("PIL", str(e)[:40])
