"""Scrape all Jaten AGV PDPs for company 1461 and dump structured data."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from web_extract import WebFetcher, parse_page

OUT = Path(__file__).resolve().parent / "staging" / "reports" / "jaten-scrape.json"
COMPANY_ID = 1461

c = ResearchApiClient()
robots = list(c.list_robots_for_company(COMPANY_ID))
fetcher = WebFetcher(stealth=False)
results = []

for r in robots:
    url = r.get("url") or ""
    entry = {
        "id": r["id"],
        "name": r["name"],
        "url": url,
        "chars": 0,
        "title": "",
        "text": "",
        "images": [],
        "og_image": "",
    }
    if not url:
        results.append(entry)
        continue
    try:
        p = parse_page(fetcher, url, rendered=False)
    except Exception as e:
        entry["error"] = str(e)
        results.append(entry)
        continue
    if not p:
        entry["error"] = "empty parse"
        results.append(entry)
        continue
    entry["chars"] = len(p.text or "")
    entry["title"] = p.title or ""
    entry["text"] = (p.text or "")[:4000]
    imgs = []
    for im in p.images or []:
        if isinstance(im, dict):
            u = im.get("url") or im.get("src") or ""
        else:
            u = str(im)
        if u and not u.startswith("data:"):
            imgs.append(urljoin(url, u))
    # dedupe preserve order
    seen = set()
    deduped = []
    for u in imgs:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    entry["images"] = deduped[:20]
    # og from meta if available
    meta = getattr(p, "meta", None) or {}
    entry["og_image"] = meta.get("og:image") or meta.get("og_image") or ""
    results.append(entry)
    print(f"OK {r['id']} {r['name']} chars={entry['chars']} imgs={len(entry['images'])}", flush=True)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {OUT}", flush=True)
