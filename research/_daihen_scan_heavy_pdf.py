"""Scan all pages of heavy EN catalog for labeled robot embeds."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import fitz
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = Path("staging/reports/daihen_family7/heavy_all")
OUT.mkdir(parents=True, exist_ok=True)

doc = fitz.open(Path("staging/reports/daihen_family7/heavy_en.pdf"))
print("pages", doc.page_count)
seen: set[str] = set()
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
        if pix.width < 250 or pix.height < 250:
            continue
        mode = "RGB" if pix.n < 4 else "RGBA"
        im = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        if mode == "RGBA":
            im = im.convert("RGB")
        raw = im.tobytes()
        md5 = hashlib.md5(raw).hexdigest()
        if md5 in seen:
            continue
        seen.add(md5)
        path = OUT / f"p{pi:02d}_i{ii:02d}_{pix.width}x{pix.height}.jpg"
        im.save(path, quality=92)
        print(f"{path.name} {md5[:10]}")
print("unique", len(seen))
