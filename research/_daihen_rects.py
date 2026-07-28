"""Locate image placement rects on heavy EN catalog pages 4-5."""
from __future__ import annotations

import sys
from pathlib import Path

import fitz
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = Path("staging/reports/daihen_family7/rect_crops")
OUT.mkdir(parents=True, exist_ok=True)

doc = fitz.open(Path("staging/reports/daihen_family7/heavy_en.pdf"))
for pi in (4, 5):
    page = doc[pi]
    print(f"\n=== page {pi} size={page.rect} ===")
    # render full page for coordinate mapping
    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat)
    page_im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    page_path = OUT / f"page{pi}_render.jpg"
    page_im.save(page_path, quality=85)
    print("render", page_path, page_im.size)

    for ii, img in enumerate(page.get_images(full=True)):
        xref = img[0]
        rects = page.get_image_rects(xref)
        try:
            pix2 = fitz.Pixmap(doc, xref)
        except Exception:
            continue
        if pix2.width < 200 or pix2.height < 200:
            continue
        print(f"  img{ii} xref={xref} {pix2.width}x{pix2.height} rects={rects}")
        for ri, r in enumerate(rects):
            # crop from 2x render
            box = (
                int(r.x0 * 2),
                int(r.y0 * 2),
                int(r.x1 * 2),
                int(r.y1 * 2),
            )
            crop = page_im.crop(box)
            crop.save(OUT / f"p{pi}_img{ii}_r{ri}_{int(r.width)}x{int(r.height)}.jpg", quality=92)
            print(f"    saved crop {box} -> {crop.size}")
