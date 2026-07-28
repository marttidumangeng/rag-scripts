"""Extract product name -> hero image mapping from Jaten AGV list page."""
from __future__ import annotations

import json
import re
from pathlib import Path
from html import unescape
from urllib.parse import urljoin

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
LIST = "https://jaten-robotics.com/index/Agv/index.html"
OUT = Path(__file__).resolve().parent / "staging" / "reports" / "jaten-url-map.json"

html = requests.get(LIST, headers=HEADERS, timeout=60).text
print("list html len", len(html))

# Find detail links and nearby images / titles
# Typical pattern: detail.html?id=NNNN with img src=/upload/...
detail_re = re.compile(
    r'href=["\']([^"\']*Agv/detail\.html\?id=(\d+)[^"\']*)["\']',
    re.I,
)
img_re = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)

# Split into product-ish blocks around detail links
entries = []
seen_ids = set()
for m in detail_re.finditer(html):
    pid = m.group(2)
    if pid in seen_ids:
        continue
    seen_ids.add(pid)
    href = urljoin(LIST, unescape(m.group(1)))
    # window around match
    start = max(0, m.start() - 1500)
    end = min(len(html), m.end() + 1500)
    block = html[start:end]
    imgs = [urljoin(LIST, unescape(u)) for u in img_re.findall(block)]
    # filter logos
    imgs = [
        u for u in imgs
        if "/upload/" in u.lower()
        and not any(x in u.lower() for x in ("logo", "icon", "banner", "favicon", "wx", "qr"))
    ]
    # try to find product name near
    name = ""
    name_m = re.search(r"(R2SDM[\w\-]+|SDM[\w\-]+|MN[\w\-]+|AGV[\w\-]+)", block, re.I)
    if name_m:
        name = name_m.group(1)
    # also look for title tags / h / p
    title_m = re.search(
        r"(?:title|alt)=[\"']([^\"']{3,80})[\"']",
        block,
        re.I,
    )
    alt = title_m.group(1) if title_m else ""
    entries.append({
        "id": pid,
        "url": href,
        "name_guess": name,
        "alt": alt,
        "images": imgs[:5],
        "hero": imgs[0] if imgs else "",
    })

OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"entries={len(entries)} -> {OUT}")
for e in entries:
    print(f"id={e['id']} name={e['name_guess']!r} hero={e['hero'][-60:] if e['hero'] else '-'} url={e['url']}")
