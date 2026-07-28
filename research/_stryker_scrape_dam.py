"""Scrape Stryker DAM image paths from Mako pages."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

pages = [
    "https://www.stryker.com/us/en/joint-replacement/systems/Mako_SmartRobotics_Overview.html",
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-total-knee.html",
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-total-hip.html",
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-partial-knee.html",
]
pat = re.compile(r"/content/dam/stryker/[^\s\"'<>]+", re.I)

for url in pages:
    print("===", url)
    html = requests.get(url, timeout=60).text
    hits = sorted(set(pat.findall(html)))
    for m in hits:
        low = m.lower()
        if any(x in low for x in (".jpg", ".png", ".webp", ".jpeg", "mako", "family", "hero")):
            if "globe" in low or "favicon" in low or "icon" in low:
                continue
            print(" ", m[:200])
