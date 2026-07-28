"""Parse OTC Europe 6-axis listing for V350/V600/V700 cards + download product images."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path("staging/reports/daihen_family7/europe")
OUT.mkdir(parents=True, exist_ok=True)
session = requests.Session()
session.headers.update(UA)

r = session.get("https://otc-daihen.com/automation/robots/6-axis.html", timeout=45)
soup = BeautifulSoup(r.text, "html.parser")
(OUT / "sixaxis.html").write_text(r.text, encoding="utf-8")

# Find any text nodes containing V350
for el in soup.find_all(string=re.compile(r"V350|V600|V700|V400", re.I)):
    parent = el.parent
    print("TEXT:", el.strip()[:80])
    # climb for link + img
    node = parent
    for _ in range(8):
        if node is None:
            break
        a = node.find("a") if hasattr(node, "find") else None
        img = node.find("img") if hasattr(node, "find") else None
        if a and a.get("href"):
            print("  a", urljoin(r.url, a["href"]))
        if img:
            src = img.get("src") or img.get("data-src")
            alt = img.get("alt")
            print("  img", alt, urljoin(r.url, src) if src else None)
        node = node.parent

# Also regex product links near V350
for m in re.finditer(r'.{0,200}FD-V350.{0,400}', r.text, re.I | re.S):
    chunk = m.group(0)
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', chunk)
    imgs = re.findall(r'(?:src|data-src)=["\']([^"\']+)["\']', chunk)
    print("CHUNK hrefs", hrefs[:5], "imgs", imgs[:3])

# Download ALL productImages from listing at full size if possible
imgs = re.findall(r'/assets/image-cache//storage/productImages/([^"\']+)', r.text)
print("n productImages", len(set(imgs)))
for name in sorted(set(imgs)):
    # try original storage path without cache
    variants = [
        f"https://otc-daihen.com/assets/image-cache//storage/productImages/{name}",
        f"https://otc-daihen.com/storage/productImages/{name.split('.')[0]}",
    ]
    # strip cache hash suffix .6fa0d29a.webp
    base = name
    for v in variants:
        try:
            ir = session.get(v, timeout=30)
        except Exception:
            continue
        if ir.status_code == 200 and len(ir.content) > 5000:
            md5 = hashlib.md5(ir.content).hexdigest()[:10]
            path = OUT / f"prod_{md5}.webp"
            path.write_bytes(ir.content)
            print("OK", path.name, len(ir.content), v[-60:])
            break
