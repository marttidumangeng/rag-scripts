"""Extract heavy EN catalog stills + scrape otc.co.id product heroes."""
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

HEAVY_EN = "https://www.daihen-robot.com/assets/download/en/FD_V280L_V350_V400L_V600_V700/FD_V280L_V350_V400L_V600_V700_Catalog_E.pdf"

OTC = {
    3054: "https://www.otc.co.id/product/fd-350/",
    2472: "https://www.otc.co.id/product/fd-400l/",
    1898: "https://www.otc.co.id/product/fd-v600/",
    1899: "https://www.otc.co.id/product/fd-v700/",
    3051: "https://www.otc.co.id/product/fd-v80/",
    1903: "https://www.otc.co.id/product/fd-v100/",
    1904: "https://www.otc.co.id/product/fd-v130/",
}


def save_pixmap(pix: fitz.Pixmap, path: Path) -> None:
    if pix.n >= 4 or (pix.colorspace and pix.colorspace != fitz.csRGB):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    mode = "RGB" if pix.n < 4 else "RGBA"
    im = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if mode == "RGBA":
        im = im.convert("RGB")
    im.save(path, quality=92)


def main() -> None:
    print("Downloading heavy EN catalog…")
    r = requests.get(HEAVY_EN, headers=UA, timeout=180)
    print("heavy EN", r.status_code, len(r.content))
    r.raise_for_status()
    (OUT / "heavy_en.pdf").write_bytes(r.content)
    doc = fitz.open(stream=r.content, filetype="pdf")
    print("pages", len(doc))
    for pi in range(min(len(doc), 6)):
        page = doc[pi]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        pix.save(str(OUT / f"heavy_en_page{pi}.png"))
        print("page", pi, pix.width, pix.height)
        for ii, img in enumerate(page.get_images(full=True)):
            try:
                ipix = fitz.Pixmap(doc, img[0])
            except Exception:
                continue
            if ipix.width < 350 or ipix.height < 400:
                continue
            aspect = ipix.width / max(ipix.height, 1)
            # prefer tall product stills
            if aspect > 1.6:
                continue
            if aspect < 0.25:
                continue
            op = OUT / f"heavy_en_p{pi}_i{ii}_{ipix.width}x{ipix.height}.jpg"
            try:
                save_pixmap(ipix, op)
            except Exception as e:
                print(" skip", e)
                continue
            md5 = hashlib.md5(op.read_bytes()).hexdigest()
            print(" emb", op.name, md5[:10], f"aspect={aspect:.2f}")

    for rid, url in OTC.items():
        try:
            resp = requests.get(url, headers=UA, timeout=40)
        except Exception as e:
            print("otc fail", rid, e)
            continue
        print("OTC", rid, resp.status_code, url)
        if resp.status_code != 200:
            continue
        imgs = re.findall(
            r'(?:src|data-src|data-lazy-src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp))',
            resp.text,
            re.I,
        )
        for u in list(dict.fromkeys(imgs))[:20]:
            full = urljoin(url, u)
            if any(x in full.lower() for x in ("logo", "icon", "avatar", "wp-includes")):
                continue
            try:
                ir = requests.get(full, headers=UA, timeout=30)
            except Exception:
                continue
            if ir.status_code != 200 or len(ir.content) < 8000:
                continue
            try:
                im = Image.open(io.BytesIO(ir.content)).convert("RGB")
            except Exception:
                continue
            if min(im.size) < 250:
                continue
            md5 = hashlib.md5(ir.content).hexdigest()
            name = f"otc_{rid}_{md5[:10]}_{full.rsplit('/',1)[-1][:40]}"
            p = OUT / name
            p.write_bytes(ir.content)
            print(" ", name, im.size)


if __name__ == "__main__":
    main()
