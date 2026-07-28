"""Hunt labeled FD-V350 / V600 / V700 stills from JP catalog + OEM paths."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.parse import urljoin

import fitz
import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.daihen-robot.com/"}
OUT = Path("staging/reports/daihen_family7/hunt")
OUT.mkdir(parents=True, exist_ok=True)

URLS = [
    "https://www.daihen-robot.com/assets/download/jp/FD_V280L_V350_V400L_V600_V700/FD_V280L_V350_V400L_V600_V700_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/en/FD_V280L_V350_V400L_V600_V700/FD_V280L_V350_V400L_V600_V700_Catalog_E.pdf",
]

# Known product / gallery paths to probe
PROBE = []
for model in ["FD-V350", "FD-V400L", "FD-V600", "FD-V700", "FD-V280L"]:
    base = model.replace("-", "_")
    PROBE += [
        f"https://www.daihen-robot.com/assets/img/en/robot/items/mv_{model}.jpg",
        f"https://www.daihen-robot.com/assets/img/en/robot/items/{base}_img01.jpg",
        f"https://www.daihen-robot.com/assets/img/en/robot/items/{base}_img02.jpg",
        f"https://www.daihen-robot.com/assets/img/en/robot/items/{base}_img03.jpg",
        f"https://www.daihen-robot.com/assets/img/jp/robot/items/mv_{model}.jpg",
        f"https://www.daihen-robot.com/assets/img/common/robot/{base}.jpg",
        f"https://www.daihen-robot.com/assets/img/common/robot/{model}.jpg",
        f"https://otc-daihen.com/wp-content/uploads/{model}.png",
        f"https://otc-daihen.com/wp-content/uploads/{model}.jpg",
        f"https://www.otc-daihen.com/wp-content/uploads/{model}.png",
    ]

session = requests.Session()
session.headers.update(UA)

print("=== URL probes ===")
for u in PROBE:
    try:
        r = session.get(u, timeout=20, stream=True)
        ct = r.headers.get("Content-Type", "")
        if r.status_code == 200 and ("image" in ct or u.endswith((".jpg", ".png", ".webp"))):
            data = r.content
            if len(data) < 5000:
                continue
            md5 = hashlib.md5(data).hexdigest()[:10]
            ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            name = f"probe_{md5}{ext}"
            (OUT / name).write_bytes(data)
            print(f"OK {r.status_code} {len(data)} {md5} {u}")
        else:
            pass
    except Exception as e:
        print("ERR", u, e)

# Extract JP catalog if downloadable
jp = OUT / "heavy_jp.pdf"
print("\n=== JP catalog ===")
try:
    r = session.get(URLS[0], timeout=120)
    print("JP status", r.status_code, len(r.content))
    if r.status_code == 200 and len(r.content) > 100000:
        jp.write_bytes(r.content)
except Exception as e:
    print("JP fail", e)

if jp.is_file():
    doc = fitz.open(jp)
    print("JP pages", doc.page_count)
    seen = set()
    for pi in range(min(doc.page_count, 12)):
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
            if pix.width < 300 or pix.height < 300:
                continue
            mode = "RGB" if pix.n < 4 else "RGBA"
            im = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            if mode == "RGBA":
                im = im.convert("RGB")
            md5 = hashlib.md5(im.tobytes()).hexdigest()
            if md5 in seen:
                continue
            seen.add(md5)
            path = OUT / f"jp_p{pi:02d}_i{ii:02d}_{pix.width}x{pix.height}.jpg"
            im.save(path, quality=92)
            print(path.name)
print("done")
