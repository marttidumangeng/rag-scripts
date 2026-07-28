"""Probe DINGS Motion OEM pages + Serper for company 1512 Gripper."""
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

OUT = Path("staging/reports/dings-scrape.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
MEDIA = Path("staging/media/dings")
MEDIA.mkdir(parents=True, exist_ok=True)

URLS = [
    "https://www.dingsmotion.com/products/products-middle-10.php",
    "https://www.dingsmotion.com/",
    "https://www.dingsmotion.com/products/",
    "https://www.dingsmotion.com/en/",
    "https://www.dingsmotion.com/en/products/",
]

fetcher = WebFetcher(stealth=False)
pages = []
for url in URLS:
    entry = {"url": url}
    try:
        p = parse_page(fetcher, url, rendered=False)
    except Exception as e:
        entry["error"] = str(e)
        pages.append(entry)
        print(f"ERR {url}: {e}", flush=True)
        continue
    if not p:
        # raw fetch fallback
        try:
            r = requests.get(url, headers=HEADERS, timeout=40)
            entry["status"] = r.status_code
            entry["raw_len"] = len(r.text)
            entry["raw_snip"] = re.sub(r"\s+", " ", r.text)[:1500]
            print(f"RAW {url} status={r.status_code} len={len(r.text)}", flush=True)
        except Exception as e2:
            entry["error"] = str(e2)
            print(f"EMPTY {url}: {e2}", flush=True)
        pages.append(entry)
        continue
    imgs = []
    for im in p.images or []:
        u = im.get("url") if isinstance(im, dict) else str(im)
        if u and not str(u).startswith("data:"):
            imgs.append(urljoin(url, str(u)))
    entry.update({
        "title": p.title or "",
        "chars": len(p.text or ""),
        "text": (p.text or "")[:6000],
        "images": imgs[:40],
    })
    pages.append(entry)
    print(f"OK {url} chars={entry['chars']} imgs={len(imgs)} title={(p.title or '')[:60].encode('ascii','replace').decode()}", flush=True)

searches = {}
for q in [
    'site:dingsmotion.com Gripper',
    'site:dingsmotion.com electric gripper',
    '"DINGS" Gripper robot OR actuator OR electric',
    "Jiangsu DINGS Intelligent Control gripper",
    "dingsmotion.com gripper",
]:
    items = []
    for r in _serper_google_search(q, max_results=8):
        items.append({"link": r.get("link"), "title": r.get("title"), "snippet": r.get("snippet")})
    searches[q] = items
    print(f"SERPER {q!r}: {len(items)}", flush=True)
    for it in items[:5]:
        print(f"  {it['link']}", flush=True)

OUT.write_text(json.dumps({"pages": pages, "serper": searches}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {OUT}", flush=True)
