"""Scrape J&J / Auris Monarch Quest pages."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

from load_env import load_research_env

load_research_env()
from product_url_search import _serper_google_search
from web_extract import WebFetcher, parse_page

OUT = Path("staging/reports/auris-scrape.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

urls = [
    "https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/",
    "https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform",
    "https://www.jnjmedtech.com/en-US/product/monarch-platform",
    "https://www.jnjmedtech.com/en-US/service/monarch",
]

results = []
fetcher = WebFetcher(stealth=False)
for url in urls:
    entry = {"url": url}
    try:
        p = parse_page(fetcher, url, rendered=False)
    except Exception as e:
        entry["error"] = str(e)
        results.append(entry)
        print(f"ERR {url}: {e}", flush=True)
        continue
    if not p:
        entry["error"] = "empty"
        results.append(entry)
        print(f"EMPTY {url}", flush=True)
        continue
    entry["chars"] = len(p.text or "")
    entry["title"] = p.title or ""
    entry["text"] = (p.text or "")[:5000]
    imgs = []
    for im in p.images or []:
        u = im.get("url") if isinstance(im, dict) else str(im)
        if u and not str(u).startswith("data:"):
            imgs.append(urljoin(url, str(u)))
    entry["images"] = imgs[:25]
    print(f"OK {url} chars={entry['chars']} imgs={len(imgs)}", flush=True)
    results.append(entry)

# Serper
searches = {}
for q in [
    'site:jnjmedtech.com "Monarch Quest"',
    'site:jnjmedtech.com Monarch Platform bronchoscopy',
    '"Monarch Quest" Auris OR "Johnson & Johnson" OR JNJ robot',
    'Monarch Platform bronchoscopy official',
]:
    items = []
    for r in _serper_google_search(q, max_results=8):
        items.append({"link": r.get("link"), "title": r.get("title"), "snippet": r.get("snippet")})
    searches[q] = items
    print(f"SERPER {q!r}: {len(items)}", flush=True)
    for it in items[:4]:
        print(f"  {it['link']}", flush=True)

OUT.write_text(
    json.dumps({"pages": results, "serper": searches}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"wrote {OUT}", flush=True)
