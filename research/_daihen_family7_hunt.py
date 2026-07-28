"""Hunt alternate heroes for 7 DAIHEN family-banner robots."""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image, ImageFilter
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {
    "User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)",
    "Referer": "https://www.daihen-robot.com/",
}
OUT = Path("staging/reports/daihen_family7")
OUT.mkdir(parents=True, exist_ok=True)

PENDING = {
    3051: "FD-V80",
    1903: "FD-V100",
    1904: "FD-V130",
    3054: "FD-V350",
    2472: "FD-V400L",
    1898: "FD-V600",
    1899: "FD-V700",
}

BANNERS = {
    3051: "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V80_V100_V130.jpg",
    1903: "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V80_V100_V130.jpg",
    1904: "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V80_V100_V130.jpg",
    3054: "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V280L_V350_V400L_V600_V700.jpg",
    2472: "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V280L_V350_V400L_V600_V700.jpg",
    1898: "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V280L_V350_V400L_V600_V700.jpg",
    1899: "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V280L_V350_V400L_V600_V700.jpg",
}

# Absolute pixel boxes on 1200x430 — below title band, one robot each
# Tuned from full-banner layout (robots on right; header text on left/top)
BOXES = {
    # V80 family — start y=100 to clear large title; narrow windows
    3051: (560, 100, 740, 400),   # FD-V80 leftmost of trio
    1903: (740, 100, 940, 400),   # FD-V100
    1904: (960, 100, 1185, 400),  # FD-V130
    # Heavy family — five robots; skip V280L (not in queue)
    3054: (620, 130, 760, 420),   # FD-V350
    2472: (780, 130, 940, 420),   # FD-V400L (longer arm)
    1898: (960, 130, 1090, 420),  # FD-V600
    1899: (1090, 130, 1195, 420), # FD-V700
}

PDFS = [
    "https://www.daihen-usa.com/wp-content/uploads/documents/V100-series.pdf",
    "https://www.daihen-robot.com/assets/download/FD_V80/FD_V80_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/FD_V100/FD_V100_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/FD_V130/FD_V130_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/FD_V350/FD_V350_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/FD_V400L/FD_V400L_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/FD_V600/FD_V600_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/FD_V700/FD_V700_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/FD_V280L_V350_V400L_V600_V700/FD_V280L_V350_V400L_V600_V700_Catalog.pdf",
]

PDP_CANDIDATES = []
for name in PENDING.values():
    slug = name  # FD-V80
    PDP_CANDIDATES.extend(
        [
            f"https://www.daihen-robot.com/en/robot/items/{slug}.html",
            f"https://www.daihen-robot.com/robot/items/{slug}.html",
            f"https://www.daihen-usa.com/product/{slug.lower()}/",
            f"https://www.daihen-usa.com/product/{slug.lower().replace('fd-', 'fd-')}/",
        ]
    )


def inpaint_white(im: Image.Image) -> Image.Image:
    arr = np.array(im.convert("RGB"), dtype=np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    sat = arr.max(axis=2) - arr.min(axis=2)
    blueish = (b > r + 12) & (b > g + 5) & (b > 130)
    cream = (r > 175) & (g > 165) & (b > 140) & (r - b < 90) & ~blueish
    mask = ((lum > 228) & (sat < 45) & ~cream) | ((lum > 200) & (sat < 60) & blueish & (b > 170))
    mask_im = Image.fromarray((mask.astype(np.uint8) * 255), mode="L").filter(ImageFilter.MaxFilter(7))
    mask = np.array(mask_im) > 128
    if not mask.any():
        return im
    mean_blue = arr[blueish].mean(axis=0) if blueish.any() else np.array([120.0, 170.0, 210.0])
    filled = arr.copy()
    filled[mask] = mean_blue
    blur = Image.fromarray(filled.astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius=10))
    out = arr.copy()
    out[mask] = np.array(blur, dtype=np.float32)[mask]
    return Image.fromarray(out.astype(np.uint8))


def save(im: Image.Image, name: str) -> dict:
    path = OUT / name
    im.save(path, quality=93)
    md5 = hashlib.md5(path.read_bytes()).hexdigest()
    print(f"SAVE {name} {im.size} {md5[:10]}")
    return {"path": str(path).replace("\\", "/"), "md5": md5, "w": im.size[0], "h": im.size[1]}


def try_pdfs() -> list[dict]:
    try:
        import fitz
    except ImportError:
        print("no fitz")
        return []
    hits = []
    for url in PDFS:
        try:
            r = requests.get(url, headers=UA, timeout=60)
        except Exception as e:
            print("pdf fail", url, e)
            continue
        print("PDF", r.status_code, len(r.content), url.split("/")[-1])
        if r.status_code != 200 or len(r.content) < 5000:
            continue
        try:
            doc = fitz.open(stream=r.content, filetype="pdf")
        except Exception as e:
            print("  open fail", e)
            continue
        for pi, page in enumerate(doc):
            for ii, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                except Exception:
                    continue
                if pix.n > 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                if pix.width < 350 or pix.height < 280:
                    continue
                aspect = pix.width / max(pix.height, 1)
                # skip wide banners and tiny icons
                if aspect > 2.0:
                    continue
                name = f"pdf_{url.split('/')[-1][:30]}_p{pi}_{ii}_{pix.width}x{pix.height}.png"
                out = OUT / name
                pix.save(str(out))
                md5 = hashlib.md5(out.read_bytes()).hexdigest()
                print(f"  IMG {name} {md5[:10]}")
                hits.append({"path": str(out), "md5": md5, "w": pix.width, "h": pix.height, "src": url})
    return hits


def scrape_pdps() -> list[dict]:
    hits = []
    for url in PDP_CANDIDATES:
        try:
            r = requests.get(url, headers=UA, timeout=25)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        print("PDP", r.status_code, url)
        imgs = re.findall(r'(?:src|data-src|href)=["\']([^"\']+\.(?:jpg|jpeg|png|webp))', r.text, re.I)
        for u in imgs:
            full = urljoin(url, u)
            if any(x in full.lower() for x in ("logo", "icon", "flag", "btn_", "play")):
                continue
            if "robot" not in full.lower() and "product" not in full.lower() and "upload" not in full.lower():
                continue
            try:
                ir = requests.get(full, headers=UA, timeout=25)
            except Exception:
                continue
            if ir.status_code != 200 or len(ir.content) < 8000:
                continue
            try:
                im = Image.open(io.BytesIO(ir.content)).convert("RGB")
            except Exception:
                continue
            if im.size[0] < 300:
                continue
            md5 = hashlib.md5(ir.content).hexdigest()
            name = f"pdp_{md5[:10]}_{full.rsplit('/',1)[-1][:40]}"
            p = OUT / name
            p.write_bytes(ir.content)
            print("  PDPIMG", name, im.size)
            hits.append({"path": str(p), "url": full, "md5": md5, "size": im.size, "page": url})
    return hits


def main() -> None:
    cache: dict[str, Image.Image] = {}
    crops = []
    for rid, box in BOXES.items():
        banner = BANNERS[rid]
        if banner not in cache:
            r = requests.get(banner, headers=UA, timeout=45)
            raw = Image.open(io.BytesIO(r.content)).convert("RGB")
            cache[banner] = inpaint_white(raw)
            save(cache[banner], f"cleaned_{hashlib.md5(banner.encode()).hexdigest()[:8]}.jpg")
        im = cache[banner]
        l, t, rgt, b = box
        crop = im.crop((l, t, rgt, b))
        # second pass inpaint on crop (small labels)
        crop = inpaint_white(crop)
        meta = save(crop, f"crop_{rid}_{PENDING[rid]}.jpg")
        meta.update({"id": rid, "name": PENDING[rid], "banner": banner, "box": list(box)})
        crops.append(meta)

    # uniqueness
    by_hash: dict[str, list[int]] = {}
    for c in crops:
        by_hash.setdefault(c["md5"], []).append(c["id"])
    dups = {h: ids for h, ids in by_hash.items() if len(ids) > 1}
    print("dups", dups or "none")

    pdf_hits = try_pdfs()
    pdp_hits = scrape_pdps()
    Path("staging/reports/daihen-family7.json").write_text(
        json.dumps({"crops": crops, "pdf": pdf_hits, "pdp": pdp_hits}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
