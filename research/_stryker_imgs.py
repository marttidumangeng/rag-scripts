"""Extract full image URLs from Stryker Mako pages."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from web_extract import WebFetcher

f = WebFetcher()
urls = [
    "https://www.stryker.com/us/en/joint-replacement/systems/Mako_SmartRobotics_Overview.html",
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-total-knee.html",
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-total-hip.html",
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-partial-knee.html",
    "https://www.stryker.com/content/dam/stryker/joint-replacement/systems/mako-spine/JR-MKOSYM-AD-1533699-EN_US.pdf",
]
pat = re.compile(
    r"https?://[^\"'\s>]+\.(?:jpg|jpeg|png|webp|gif)",
    re.I,
)
dam = re.compile(r"/content/dam/stryker/[^\"'\s>]+\.(?:jpg|jpeg|png|webp)", re.I)

for url in urls:
    print("===", url)
    try:
        r = f.fetch(url)
        html = r.text if hasattr(r, "text") else str(r)
        print("len", len(html or ""))
        found = sorted(set(pat.findall(html or "")))
        found2 = sorted(set("https://www.stryker.com" + m if m.startswith("/") else m for m in dam.findall(html or "")))
        for u in found[:40]:
            if "globe_icon" in u or "flag" in u.lower():
                continue
            print(" ", u[:160])
        print("  dam-rel", len(found2))
        for u in found2[:30]:
            if "globe" in u:
                continue
            print("  r", u[:160])
    except Exception as e:
        print("ERR", e)
