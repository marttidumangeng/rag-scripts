"""Scrape Aethon OEM pages for catalog truth."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
from web_extract import WebFetcher, extract_image_urls

load_research_env()
f = WebFetcher()
urls = [
    "https://www.aethon.com/",
    "https://aethon.com/t3/",
    "https://aethon.com/zena-rx/",
    "https://aethon.com/hospitality-robot-zena/",
    "https://aethon.com/tug/",
]
for url in urls:
    html = f.get(url) or ""
    print("===", url, "len", len(html))
    if len(html) < 800:
        html = f.get_rendered(url) or ""
        print(" rendered", len(html))
    if not html:
        continue
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    print(text[:1800])
    print("--- imgs ---")
    for u in extract_image_urls(html, base_url=url)[:18]:
        low = u.lower()
        if any(x in low for x in ("logo", "icon", "favicon", "sprite", "emoji")):
            continue
        print(" ", u[:130])
    print()
