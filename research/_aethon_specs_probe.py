"""Pull Aethon T3 + Zena specs/images; compare duplicate records."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env
from web_extract import WebFetcher, extract_image_urls

load_research_env()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
OUT = Path("staging/tmp/aethon-qa")
OUT.mkdir(parents=True, exist_ok=True)

f = WebFetcher()
pages = {
    "t3": "https://www.aethon.com/t3/",
    "zena-rx": "https://www.aethon.com/zena-rx/",
    "zena": "https://www.aethon.com/hospitality-robot-zena/",
}
for key, url in pages.items():
    html = f.get(url) or ""
    print("===", key, len(html), url)
    if len(html) < 1000:
        r = requests.get(url, headers=UA, timeout=60)
        html = r.text
        print(" requests", r.status_code, len(html))
    soup = BeautifulSoup(html, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    # find number-ish claims
    for pat in [
        r".{0,40}\d[\d,\.]*\s*(?:kg|lb|lbs|kg\.|pounds).{0,40}",
        r".{0,40}\d[\d,\.]*\s*(?:mph|km/h|m/s|ft/min).{0,40}",
        r".{0,40}\d[\d,\.]*\s*(?:hours?|hrs?|minutes?).{0,40}",
        r".{0,40}(?:payload|capacity|weight|speed|battery|dimension).{0,60}",
        r".{0,30}\d[\d,\.]*\s*(?:cubic inches|liters|L\b).{0,40}",
    ]:
        for m in re.finditer(pat, text, re.I):
            s = m.group(0).strip()
            if len(s) > 20:
                print(" ", s[:120])
    imgs = []
    for u in extract_image_urls(html, base_url=url):
        low = u.lower()
        if any(x in low for x in ("logo", "icon", "favicon", "sprite", "st-engineering")):
            continue
        if "spec_" in low or "robot" in low or "zena" in low or "t3" in low or "tug" in low:
            imgs.append(u)
    for u in imgs[:10]:
        print(" IMG", u)
        try:
            rr = requests.get(u, headers=UA, timeout=60)
            if rr.ok and len(rr.content) > 3000:
                name = key + "-" + Path(u.split("?")[0]).name
                (OUT / name).write_bytes(rr.content)
                print("  saved", name, len(rr.content))
        except Exception as exc:
            print("  fail", exc)

# Compare duplicate pairs
c = ResearchApiClient()
pairs = [
    (1533, 1766, "T3"),
    (1534, 1767, "T3 XL"),
    (1532, 1768, "Zena RX"),
]
for a, b, label in pairs:
    da = c._get(f"robots/robots/{a}/")
    db = c._get(f"robots/robots/{b}/")
    print(f"\nPAIR {label}: {a} vs {b}")
    for rid, d in ((a, da), (b, db)):
        print(
            rid,
            d.get("name"),
            "feat",
            len(d.get("features") or ""),
            "img",
            (d.get("image") or "")[-50:],
            "url",
            (d.get("url") or "")[:50],
        )
