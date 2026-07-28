"""Extract embedded images from Jaten PDFs."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymupdf", "-q"])
    import fitz

OUT = Path("staging/media/jaten/pdf_imgs")
OUT.mkdir(parents=True, exist_ok=True)

for pdf_name in [
    "Jaten%20AGV%20Catolog%20-3m.pdf",
    "7e459a2dee73ff38a530666d1d9f6c58.pdf",
]:
    path = Path("staging/media/jaten") / pdf_name
    if not path.exists():
        continue
    doc = fitz.open(path)
    print(f"=== {pdf_name} ===", flush=True)
    n = 0
    for i, page in enumerate(doc):
        for img in page.get_images(full=True):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            if pix.n >= 5:  # CMYK
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if pix.width < 200 or pix.height < 150:
                continue
            if pix.width * pix.height < 80000:
                continue
            out = OUT / f"{pdf_name[:8]}_p{i}_x{xref}_{pix.width}x{pix.height}.png"
            pix.save(str(out))
            n += 1
            print(f"  saved {out.name}", flush=True)
    print(f"total large imgs {n}", flush=True)
print("done", flush=True)
