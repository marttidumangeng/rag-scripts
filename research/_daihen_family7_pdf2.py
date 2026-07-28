"""Finish V80 catalog extract + scrape family product pages for images."""
from __future__ import annotations

import hashlib
import io
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import fitz
import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.daihen-robot.com/"}
OUT = Path("staging/reports/daihen_family7")
OUT.mkdir(parents=True, exist_ok=True)

URLS = [
    "https://www.daihen-robot.com/assets/download/FD_V80_V100_V130/FD_V80_V100_V130_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/en/FD_V80_V100_V130/FD_V80_V100_V130_Catalog_E.pdf",
    "https://portalimages.blob.core.windows.net/products/pdfs/u4en1g4o_MAP_OTC-DAIHEN-FD-V80-V100-V130.pdf",
    "https://www.daihen.mx/wp-content/uploads/2025/07/FD-V100-USA-1.pdf",
]

PAGES = [
    "https://www.daihen-robot.com/en/items/fd_v80_v100_v130",
    "https://www.daihen-robot.com/en/items/fd_v280l_v350_v400l_v600_v700",
    "https://www.daihen-robot.com/items/fd_v80_v100_v130",
    "https://www.daihen-robot.com/items/fd_v280l_v350_v400l_v600_v700",
]


def save_pixmap(pix: fitz.Pixmap, path: Path) -> None:
    if pix.n > 4 or pix.colorspace not in (fitz.csRGB, None):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    # write via PIL for safety
    mode = "RGB" if pix.n < 4 else "RGBA"
    im = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if mode == "RGBA":
        im = im.convert("RGB")
    im.save(path, quality=93 if path.suffix.lower() == ".jpg" else None)


def extract_pdf(url: str, key: str) -> None:
    try:
        r = requests.get(url, headers=UA, timeout=90)
    except Exception as e:
        print("fail", key, e)
        return
    print(key, r.status_code, len(r.content))
    if r.status_code != 200 or len(r.content) < 20000:
        return
    (OUT / f"{key}.pdf").write_bytes(r.content)
    doc = fitz.open(stream=r.content, filetype="pdf")
    for pi in range(min(len(doc), 3)):
        page = doc[pi]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        path = OUT / f"{key}_page{pi}.png"
        pix.save(str(path))
        print(" page", path.name)
        for ii, img in enumerate(page.get_images(full=True)):
            try:
                ipix = fitz.Pixmap(doc, img[0])
            except Exception:
                continue
            if ipix.width < 400 or ipix.height < 300:
                continue
            if ipix.width / max(ipix.height, 1) > 2.2:
                continue
            op = OUT / f"{key}_p{pi}_i{ii}_{ipix.width}x{ipix.height}.jpg"
            try:
                save_pixmap(ipix, op)
            except Exception as e:
                print("  skip", e)
                continue
            md5 = hashlib.md5(op.read_bytes()).hexdigest()
            print("  emb", op.name, md5[:10])


def scrape_pages() -> None:
    for url in PAGES:
        try:
            r = requests.get(url, headers=UA, timeout=40)
        except Exception as e:
            print("page fail", url, e)
            continue
        print("PAGE", r.status_code, len(r.content), url)
        if r.status_code != 200:
            continue
        (OUT / f"page_{url.rstrip('/').split('/')[-1]}.html").write_text(
            r.text, encoding="utf-8"
        )
        imgs = re.findall(
            r'(?:src|data-src|href)=["\']([^"\']+\.(?:jpg|jpeg|png|webp))',
            r.text,
            re.I,
        )
        for u in list(dict.fromkeys(imgs)):
            full = urljoin(url, u)
            if any(x in full.lower() for x in ("logo", "icon", "btn_", "flag", "play")):
                continue
            try:
                ir = requests.get(full, headers=UA, timeout=30)
            except Exception:
                continue
            if ir.status_code != 200 or len(ir.content) < 10000:
                continue
            try:
                im = Image.open(io.BytesIO(ir.content)).convert("RGB")
            except Exception:
                continue
            if min(im.size) < 280:
                continue
            md5 = hashlib.md5(ir.content).hexdigest()
            name = f"web_{md5[:10]}_{full.rsplit('/',1)[-1][:50]}"
            p = OUT / name
            if not p.exists():
                p.write_bytes(ir.content)
            print("  img", name, im.size, "bannerish" if im.size[0] / max(im.size[1], 1) > 2 else "ok")


def main() -> None:
    # already have v80a.pdf locally from prior run
    local = OUT / "v80a.pdf"
    if local.is_file():
        print("re-extract local v80a.pdf")
        doc = fitz.open(local)
        for pi in range(min(len(doc), 3)):
            page = doc[pi]
            for ii, img in enumerate(page.get_images(full=True)):
                try:
                    ipix = fitz.Pixmap(doc, img[0])
                except Exception:
                    continue
                if ipix.width < 400 or ipix.height < 300:
                    continue
                if ipix.width / max(ipix.height, 1) > 2.2:
                    continue
                op = OUT / f"v80a_p{pi}_i{ii}_{ipix.width}x{ipix.height}.jpg"
                try:
                    save_pixmap(ipix, op)
                    print(" local emb", op.name)
                except Exception as e:
                    print(" local skip", e)

    for i, url in enumerate(URLS):
        extract_pdf(url, f"v80alt{i}")
    scrape_pages()


if __name__ == "__main__":
    main()
