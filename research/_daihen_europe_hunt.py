"""Scrape OTC Europe for FD-V350 / V600 / V700 product images."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path("staging/reports/daihen_family7/europe")
OUT.mkdir(parents=True, exist_ok=True)
session = requests.Session()
session.headers.update(UA)

# Discover V350 product URL from listing / search
seeds = [
    "https://otc-daihen.com/automation/robots/6-axis.html",
    "https://otc-daihen.com/search?q=FD-V350",
    "https://otc-daihen.com/search?sSearch=FD-V350",
    "https://otc-daihen.com/?s=FD-V350",
]
# common shopware/typo3 patterns
guesses = [
    "https://otc-daihen.com/automation/robots/6-axis/fd-v350.html",
    "https://otc-daihen.com/automation/robots/fd-v350.html",
    "https://otc-daihen.com/products/fd-v350.html",
    "https://otc-daihen.com/en/products/fd-v350/",
    "https://otc-daihen.com/automation/robots/6-axis/fd19-v350.html",
    "https://otc-daihen.com/automation/robots/6-axis/robot-module-fd19-v350-350kg-payload.html",
]

found_pages = []
for u in seeds + guesses:
    try:
        r = session.get(u, timeout=30, allow_redirects=True)
    except Exception as e:
        print("ERR", u, e)
        continue
    print("PAGE", r.status_code, len(r.content), r.url)
    if r.status_code != 200:
        continue
    text = r.text
    (OUT / "last.html").write_text(text, encoding="utf-8")
    # find product links mentioning v350
    for m in re.findall(r'href=["\']([^"\']+)["\']', text):
        if re.search(r"v350|v600|v700|v400", m, re.I):
            full = urljoin(r.url, m)
            print("  href", full)
            found_pages.append(full)
    for m in re.findall(r'(https?://[^"\']+\.(?:jpg|jpeg|png|webp)|/[^"\']+\.(?:jpg|jpeg|png|webp))', text, re.I):
        if re.search(r"v350|v600|v700|350|600|700|robot|product", m, re.I):
            print("  img", m[:140])

# Visit unique candidate product pages
for u in sorted(set(found_pages))[:30]:
    try:
        r = session.get(u, timeout=30)
    except Exception:
        continue
    if r.status_code != 200 or len(r.content) < 2000:
        continue
    print("\nVISIT", r.status_code, r.url)
    imgs = re.findall(
        r'(?:src|data-src|content)=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']',
        r.text,
        re.I,
    )
    for img in sorted(set(imgs)):
        full = urljoin(r.url, img)
        if any(x in full.lower() for x in ("logo", "icon", "sprite", "flag", "banner-home")):
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
        if not path.exists():
            path.write_bytes(ir.content)
            print("  SAVE", path.name, len(ir.content), full[:120])
