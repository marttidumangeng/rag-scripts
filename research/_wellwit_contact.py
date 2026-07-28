"""Build a labeled contact sheet of the 43 Wellwit og:images for visual QA."""
from __future__ import annotations
import json, os, io
from PIL import Image, ImageDraw, ImageFont
try:
    from curl_cffi import requests as http
    def get(u): return http.get(u, impersonate="chrome124", timeout=25)
except Exception:
    import requests as http
    def get(u): return http.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)

d = json.load(open(os.path.join(os.environ["TEMP"], "wellwit_scrape.json"), encoding="utf-8"))
cell, cols = 240, 6
rows = (len(d) + cols - 1) // cols
sheet = Image.new("RGB", (cols * cell, rows * (cell + 18)), "white")
draw = ImageDraw.Draw(sheet)
for i, r in enumerate(d):
    x, y = (i % cols) * cell, (i // cols) * (cell + 18)
    label = r["name"].replace("Wellwit Robotics", "").strip()[:22]
    try:
        img = Image.open(io.BytesIO(get(r["og"]).content)).convert("RGB")
        img.thumbnail((cell - 8, cell - 8))
        sheet.paste(img, (x + 4, y + 16))
    except Exception as e:
        draw.text((x + 6, y + cell // 2), f"FAIL {type(e).__name__}", fill="red")
    draw.text((x + 4, y + 3), f"{r['id']} {label}", fill="black")
out = os.path.join(os.environ["TEMP"], "wellwit_contact.jpg")
sheet.save(out, quality=85)
print(out, sheet.size)
