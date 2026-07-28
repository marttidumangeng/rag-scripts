"""Extract unique product stills from JP heavy catalog; crop V350 from family banner."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import fitz
import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = Path("staging/reports/daihen_family7")
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.daihen-robot.com/"}

# Scan JP PDF
pdf = OUT / "dl_4bf757b0.pdf"
doc = fitz.open(pdf)
print("JP pages", doc.page_count)
seen: set[str] = set()
jp_out = OUT / "jp_imgs"
jp_out.mkdir(exist_ok=True)
for pi in range(doc.page_count):
    page = doc[pi]
    for ii, img in enumerate(page.get_images(full=True)):
        try:
            pix = fitz.Pixmap(doc, img[0])
        except Exception:
            continue
        if pix.n >= 4 or (pix.colorspace and pix.colorspace != fitz.csRGB):
            try:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            except Exception:
                continue
        if pix.width < 350 or pix.height < 350:
            continue
        mode = "RGB" if pix.n < 4 else "RGBA"
        im = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        if mode == "RGBA":
            im = im.convert("RGB")
        md5 = hashlib.md5(im.tobytes()).hexdigest()
        if md5 in seen:
            continue
        seen.add(md5)
        # skip if same as known EN embeds
        path = jp_out / f"p{pi:02d}_i{ii:02d}_{pix.width}x{pix.height}_{md5[:8]}.jpg"
        im.save(path, quality=92)
        print(path.name)

# Family banner per-robot crops (below title band)
banner_url = "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V280L_V350_V400L_V600_V700.jpg"
r = requests.get(banner_url, headers=UA, timeout=45)
banner = OUT / "heavy_banner_full.jpg"
banner.write_bytes(r.content)
im = Image.open(banner).convert("RGB")
print("banner", im.size)
w, h = im.size
# Typical 1200x430; title across mid-left; robots on right half
# Five robots L→R: V280L, V350, V400L, V600, V700
# Take lower 70% and slice horizontally
crop_dir = OUT / "banner_slices"
crop_dir.mkdir(exist_ok=True)
# After visual: robots occupy roughly x 500-1200, y 100-430 on 1200x430
top = int(h * 0.22)  # below title band
# equal fifths of robot zone
left0 = int(w * 0.42)
right1 = w
zone_w = right1 - left0
for i, name in enumerate(["v280l", "v350", "v400l", "v600", "v700"]):
    x0 = left0 + int(zone_w * i / 5) - 10
    x1 = left0 + int(zone_w * (i + 1) / 5) + 10
    x0 = max(0, x0)
    x1 = min(w, x1)
    crop = im.crop((x0, top, x1, h))
    path = crop_dir / f"{name}.jpg"
    crop.save(path, quality=93)
    print("slice", name, crop.size, path.name)

# Also try OCR
try:
    import pytesseract

    for p in [
        OUT / "page5_imgs/i04_512x748.jpg",
        OUT / "page5_imgs/i01_536x689.jpg",
        OUT / "otc_3054_a5ca76dc41_FD-V350.png",
        OUT / "otc_1898_b1dacb82a2_FD-V600_700.png",
    ]:
        text = pytesseract.image_to_string(Image.open(p))
        print("OCR", p.name, "->", repr(text[:200]))
except Exception as e:
    print("no tesseract", e)
