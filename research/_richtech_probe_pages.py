"""Probe Richtech product pages with stealth."""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from web_extract import WebFetcher, parse_page

URLS = [
    "https://richtechrobotics.com/solutions",
    "https://richtechrobotics.com/solutions/dex",
    "https://richtechrobotics.com/solutions/adam",
    "https://richtechrobotics.com/solutions/scorpion",
    "https://richtechrobotics.com/solutions/matradee-plus",
    "https://richtechrobotics.com/solutions/matradee",
    "https://richtechrobotics.com/solutions/matradee-l",
    "https://richtechrobotics.com/solutions/titan",
    "https://richtechrobotics.com/solutions/dust-e-sx",
    "https://richtechrobotics.com/solutions/dust-e-s",
    "https://richtechrobotics.com/solutions/ace",
    "https://richtechrobotics.com/see-all-robots",
    "https://richtechrobotics.com/robots",
]

f = WebFetcher(stealth=True)
for url in URLS:
    p = parse_page(f, url, rendered=False)
    n = len(p.text) if p else 0
    print(f"=== {url} chars={n}")
    if not p or n < 200:
        continue
    print((p.text or "")[:400].replace("\n", " | "))
    for im in (p.images or [])[:6]:
        u = im if isinstance(im, str) else (im.get("url") or im.get("src") or "")
        print(" IMG", u[:130])
    print()
