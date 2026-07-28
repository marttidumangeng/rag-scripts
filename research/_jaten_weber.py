"""Fetch Weber.ru Jaten pages for MN100 / missing models."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
OUT = Path("staging/reports/jaten-weber.json")
MEDIA = Path("staging/media/jaten")

urls = [
    "https://weber.ru/device/avtomaticheskie-upravlyaemye-telezhki-agv/mn30-164-30kg/",
    "https://weber.ru/device/avtomaticheskie-upravlyaemye-telezhki-agv/agv-31-mc500-500kg/",
    "https://weber.ru/device/avtomaticheskie-upravlyaemye-telezhki-agv/",
]

results = []
session = requests.Session()
session.headers.update(HEADERS)
for url in urls:
    try:
        r = session.get(url, timeout=40)
    except Exception as e:
        results.append({"url": url, "error": str(e)})
        continue
    imgs = [urljoin(url, u) for u in re.findall(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']', r.text, re.I)]
    imgs = [u for u in imgs if "logo" not in u.lower() and "icon" not in u.lower()]
    text = re.sub(r"<[^>]+>", " ", r.text)
    text = re.sub(r"\s+", " ", text)[:2000]
    entry = {"url": url, "status": r.status_code, "imgs": imgs[:12], "text": text}
    results.append(entry)
    print(url, r.status_code, "imgs", len(imgs), flush=True)
    for i, im in enumerate(imgs[:3]):
        try:
            ir = session.get(im, timeout=30)
            if ir.ok and len(ir.content) > 10000:
                ext = ".png" if "png" in im.lower() else ".jpg"
                path = MEDIA / f"weber_{Path(url).name[:20]}_{i}{ext}"
                path.write_bytes(ir.content)
                print("  saved", path.name, len(ir.content), flush=True)
        except Exception as e:
            print("  img err", e, flush=True)

# Also search weber for other models
for q in ["mn100-164", "sdm500-d228", "sdm1000", "sdm2000", "sdm3000"]:
    page = f"https://weber.ru/search/?q={q}"
    try:
        r = session.get(page, timeout=30)
        links = re.findall(r'href=["\']([^"\']*device[^"\']*)["\']', r.text)
        print(q, "links", links[:5], flush=True)
    except Exception as e:
        print(q, e, flush=True)

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
