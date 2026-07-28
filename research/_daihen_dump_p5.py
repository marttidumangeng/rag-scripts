"""Dump ALL embedded images from heavy EN catalog page 5 (heavy-load photos)."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import fitz
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = Path("staging/reports/daihen_family7/page5_imgs")
OUT.mkdir(parents=True, exist_ok=True)

doc = fitz.open(Path("staging/reports/daihen_family7/heavy_en.pdf"))
page = doc[5]
print("page size", page.rect)
for ii, img in enumerate(page.get_images(full=True)):
    try:
        pix = fitz.Pixmap(doc, img[0])
    except Exception as e:
        print(ii, "fail", e)
        continue
    if pix.n >= 4 or (pix.colorspace and pix.colorspace != fitz.csRGB):
        try:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        except Exception as e:
            print(ii, "cs fail", e)
            continue
    if pix.width < 200 or pix.height < 200:
        continue
    mode = "RGB" if pix.n < 4 else "RGBA"
    im = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if mode == "RGBA":
        im = im.convert("RGB")
    path = OUT / f"i{ii:02d}_{pix.width}x{pix.height}.jpg"
    im.save(path, quality=92)
    md5 = hashlib.md5(path.read_bytes()).hexdigest()
    print(f"{path.name} {md5[:10]}")
