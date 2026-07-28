"""Fetch DINGS USA + DirectIndustry + HTTP FR gripper catalog."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
OUT = Path("staging/reports/dings-detail.json")
MEDIA = Path("staging/media/dings")
MEDIA.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update(HEADERS)

pages = []
for url in [
    "https://www.dingsmotionusa.com/robotic-grippers",
    "https://www.dingsmotionusa.com/",
    "https://www.directindustry.com/prod/jiangsu-dings-intelligent-control-technology/product-197151-2467187.html",
]:
    try:
        r = session.get(url, timeout=60)
        text = re.sub(r"<script[\s\S]*?</script>", " ", r.text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        imgs = [
            urljoin(url, u)
            for u in re.findall(
                r"(?:src|data-src)=[\"']([^\"']+\.(?:png|jpe?g|webp)[^\"']*)[\"']",
                r.text,
                re.I,
            )
        ]
        pages.append({
            "url": str(r.url),
            "status": r.status_code,
            "chars": len(text),
            "text": text[:9000],
            "images": imgs[:40],
        })
        print(f"OK {r.status_code} {url} chars={len(text)} imgs={len(imgs)}", flush=True)
    except Exception as e:
        pages.append({"url": url, "error": str(e)})
        print(f"ERR {url}: {e}", flush=True)

pdf_paths: list[str] = []
pdf_url = "http://fr.dingsmotion.com/downloads/catalog/Gripper_Product%20Catalog_ENG.pdf"
try:
    r = session.get(pdf_url, timeout=90)
    path = MEDIA / "Gripper_Product_Catalog_ENG.pdf"
    if r.status_code == 200 and len(r.content) > 20000:
        path.write_bytes(r.content)
        pdf_paths.append(str(path))
        print(f"PDF OK {path.name} {len(r.content)}", flush=True)
    else:
        print(f"PDF FAIL status={r.status_code} len={len(r.content)}", flush=True)
except Exception as e:
    print(f"PDF ERR {e}", flush=True)

try:
    import fitz
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymupdf", "-q"])
    import fitz

pdf_extract = []
for p in pdf_paths:
    doc = fitz.open(p)
    texts = []
    saved = []
    for i, page in enumerate(doc):
        texts.append(page.get_text() or "")
        if len(saved) >= 10:
            continue
        for img in page.get_images(full=True):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            if pix.n >= 5:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if pix.width < 180 or pix.height < 120 or pix.width * pix.height < 50000:
                continue
            out = MEDIA / f"catalog_p{i}_x{xref}.png"
            pix.save(str(out))
            saved.append(str(out))
            print(f"  img {out.name} {pix.width}x{pix.height}", flush=True)
            if len(saved) >= 10:
                break
    joined = "\n".join(texts)
    pdf_extract.append({
        "path": p,
        "pages": doc.page_count,
        "text": joined[:16000],
        "images": saved,
    })
    print(f"PDF pages={doc.page_count} chars={len(joined)}", flush=True)

OUT.write_text(
    json.dumps({"pages": pages, "pdf_extract": pdf_extract}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"wrote {OUT}", flush=True)
