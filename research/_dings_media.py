"""Continue PDF image extract + download USA site heroes."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
MEDIA = Path("staging/media/dings")
MEDIA.mkdir(parents=True, exist_ok=True)
OUT = Path("staging/reports/dings-detail.json")

# Load existing report if present
report = {}
if OUT.exists():
    try:
        report = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        report = {}

# Re-read USA page images and download candidates
session = requests.Session()
session.headers.update(HEADERS)
usa = session.get("https://www.dingsmotionusa.com/robotic-grippers", timeout=60)
imgs = [
    urljoin(usa.url, u)
    for u in re.findall(
        r"(?:src|data-src|href)=[\"']([^\"']+\.(?:png|jpe?g|webp)[^\"']*)[\"']",
        usa.text,
        re.I,
    )
]
# also background images
imgs += [
    urljoin(usa.url, u)
    for u in re.findall(r"url\(([^)]+\.(?:png|jpe?g|webp)[^)]*)\)", usa.text, re.I)
]
seen = set()
uniq = []
for u in imgs:
    u = u.strip().strip("'\"")
    if u not in seen:
        seen.add(u)
        uniq.append(u)

print(f"usa imgs={len(uniq)}", flush=True)
downloaded = []
for i, u in enumerate(uniq[:20]):
    low = u.lower()
    if any(x in low for x in ("logo", "icon", "favicon", "sprite", "1x1", "pixel")):
        continue
    try:
        r = session.get(u, timeout=40)
        ctype = (r.headers.get("content-type") or "").lower()
        if r.status_code != 200 or "image" not in ctype or len(r.content) < 15000:
            print(f"skip {len(r.content)} {u[:90]}", flush=True)
            continue
        ext = ".png" if "png" in ctype or u.lower().endswith(".png") else ".jpg"
        path = MEDIA / f"usa_{i}{ext}"
        path.write_bytes(r.content)
        downloaded.append({"url": u, "path": str(path), "bytes": len(r.content)})
        print(f"OK {path.name} {len(r.content)} {u[:100]}", flush=True)
        if len(downloaded) >= 8:
            break
    except Exception as e:
        print(f"ERR {e}", flush=True)

# PDF images with jpeg fallback for unsupported colorspace
import fitz

pdf = MEDIA / "Gripper_Product_Catalog_ENG.pdf"
pdf_imgs = []
pdf_text = ""
if pdf.exists():
    doc = fitz.open(pdf)
    chunks = []
    for i, page in enumerate(doc):
        chunks.append(page.get_text() or "")
        if len(pdf_imgs) >= 12:
            continue
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n >= 5:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                if pix.width < 180 or pix.height < 120 or pix.width * pix.height < 40000:
                    continue
                out = MEDIA / f"catalog_p{i}_x{xref}.jpg"
                # save as PNG if RGB else convert
                try:
                    if pix.alpha:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    pix.save(str(out.with_suffix(".png")))
                    out = out.with_suffix(".png")
                except Exception:
                    from PIL import Image
                    import io
                    # use pillow via samples
                    mode = "RGB" if pix.n < 4 else "RGBA"
                    im = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                    im = im.convert("RGB")
                    im.save(out, "JPEG", quality=90)
                pdf_imgs.append(str(out))
                print(f"pdf img {out.name} {pix.width}x{pix.height}", flush=True)
                if len(pdf_imgs) >= 12:
                    break
            except Exception as e:
                print(f"pdf img skip {e}", flush=True)
    pdf_text = "\n".join(chunks)

# Extract useful product names from USA page
text = re.sub(r"<[^>]+>", " ", usa.text)
text = re.sub(r"\s+", " ", text)

report["usa_images"] = downloaded
report["pdf_images"] = pdf_imgs
report["pdf_text"] = pdf_text[:18000]
report["usa_text"] = text[:9000]
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {OUT} usa={len(downloaded)} pdf_imgs={len(pdf_imgs)}", flush=True)
