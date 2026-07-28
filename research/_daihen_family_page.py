"""Fetch family page + probe alternate catalogs; hash key candidates."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.daihen-robot.com/"}
OUT = Path("staging/reports/daihen_family7")
session = requests.Session()
session.headers.update(UA)

u = "https://www.daihen-robot.com/en/items/fd_v280l_v350_v400l_v600_v700"
r = session.get(u, timeout=45)
print("family page", r.status_code, len(r.content), r.url)
(OUT / "family_page.html").write_text(r.text, encoding="utf-8")
imgs = re.findall(
    r'(?:src|href)=["\']([^"\']+\.(?:jpg|jpeg|png|webp|pdf))["\']',
    r.text,
    re.I,
)
for i in sorted(set(imgs)):
    print(" ", i)

cands = [
    "https://www.daihen-robot.com/assets/download/FD_V280L_V350_V400L_V600_V700/FD_V280L_V350_V400L_V600_V700_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/FD_V350/FD_V350_Catalog.pdf",
    "https://www.daihen-robot.com/assets/download/en/FD_V350/FD_V350_Catalog_E.pdf",
    "https://portalimages.blob.core.windows.net/products/pdfs/MAP_OTC-DAIHEN-FD-V350.pdf",
    "https://portalimages.blob.core.windows.net/products/pdfs/u4en1g4o_MAP_OTC-DAIHEN-FD-V280L-V350.pdf",
]
for c in cands:
    try:
        rr = session.get(c, timeout=60, stream=True)
        cl = rr.headers.get("Content-Length", "?")
        print("GET", rr.status_code, cl, c[:90])
        if rr.status_code == 200 and int(cl or 0) > 50000:
            path = OUT / f"dl_{hashlib.md5(c.encode()).hexdigest()[:8]}.pdf"
            path.write_bytes(rr.content)
            print("  saved", path, len(rr.content))
    except Exception as e:
        print("ERR", c, e)

# Hash comparison of key stills
files = {
    "v80": OUT / "v80alt2_p0_i3_938x2517.jpg",
    "v100": OUT / "v80alt2_p0_i1_835x2652.jpg",
    "v130": OUT / "v80alt2_p0_i2_778x2652.jpg",
    "otc400": OUT / "otc_2472_0c5932919b_FD-V400L.png",
    "otc600": OUT / "otc_1898_b1dacb82a2_FD-V600_700.png",
    "otc350": OUT / "otc_3054_a5ca76dc41_FD-V350.png",
    "p5_i00": OUT / "page5_imgs/i00_628x606.jpg",
    "p5_i01": OUT / "page5_imgs/i01_536x689.jpg",
    "p5_i04": OUT / "page5_imgs/i04_512x748.jpg",
    "cover": OUT / "heavy_en_p0_i0_1701x1827.jpg",
}
print("\n=== hashes ===")
for k, p in files.items():
    if not p.is_file():
        print(k, "MISSING")
        continue
    md5 = hashlib.md5(p.read_bytes()).hexdigest()
    im = Image.open(p)
    print(f"{k:10} {im.size} {md5[:12]} {p.name}")
