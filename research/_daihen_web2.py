"""Scrape otc.co.id + ATC Baltic + kontur for V350/V600/V700 images."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path("staging/reports/daihen_family7/web2")
OUT.mkdir(parents=True, exist_ok=True)
session = requests.Session()
session.headers.update(UA)

PAGES = [
    "https://www.otc.co.id/product/fd-350/",
    "https://www.otc.co.id/product/fd-v350/",
    "https://www.otc.co.id/product/fd-400l/",
    "https://www.otc.co.id/product/fd-v600/",
    "https://www.otc.co.id/product/fd-v700/",
    "https://www.otc.co.id/product_category/heavy-payload-robot/",
    "https://atcbaltic.com/en/produktai/industrial-robots/palletizing-robot/fd-v350-2/",
    "https://k97.ru/catalog/roboty-manipulyatory/fd-v350/",
    "https://www.europages.co.uk/en/company/otc-daihen-europe-gmbh-22212240/products/6-achsroboter-fd-v350-fuer-handhabungsaufgaben-von-maximal-schweren-traglasten-35763376",
]

for url in PAGES:
    try:
        r = session.get(url, timeout=40)
    except Exception as e:
        print("ERR", url, e)
        continue
    print("\nPAGE", r.status_code, len(r.content), r.url)
    if r.status_code != 200:
        continue
    slug = re.sub(r"[^a-z0-9]+", "_", url.lower())[:60]
    (OUT / f"{slug}.html").write_text(r.text, encoding="utf-8")
    imgs = re.findall(
        r'(?:src|data-src|data-lazy-src|content)=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']',
        r.text,
        re.I,
    )
    # also og:image
    imgs += re.findall(r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', r.text, re.I)
    imgs += re.findall(r'content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', r.text, re.I)
    for img in sorted(set(imgs)):
        full = urljoin(r.url, img)
        if any(x in full.lower() for x in ("logo", "icon", "sprite", "wp-includes", "emoji", "avatar")):
            continue
        try:
            ir = session.get(full, timeout=30)
        except Exception:
            continue
        if ir.status_code != 200 or len(ir.content) < 8000:
            continue
        md5 = hashlib.md5(ir.content).hexdigest()[:10]
        ext = ".png" if ir.content[:8].startswith(b"\x89PNG") else ".jpg"
        path = OUT / f"{md5}{ext}"
        if path.exists():
            print("  have", path.name, full[-70:])
            continue
        path.write_bytes(ir.content)
        try:
            im = Image.open(path)
            jpg = OUT / f"{md5}.jpg"
            im.convert("RGB").save(jpg, quality=92)
            print("  SAVE", path.name, im.size, full[-90:])
        except Exception as e:
            print("  SAVE raw", path.name, len(ir.content), e)
