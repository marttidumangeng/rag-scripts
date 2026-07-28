"""Scrape AMP Sortation OEM pages for Delta heroes + reject plan."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
OUT = Path("staging/tmp/amp-heroes")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    "https://ampsortation.com/technologies/delta",
    "https://www.amprobotics.com/robotic-system",
    "https://www.amprobotics.com/compact-robotic-sorting",
    "https://ampsortation.com/",
    "https://www.amprobotics.com/",
]

# Known datasheet
PDFS = [
    "https://easyfairsassets.com/sites/183/2023/01/A4_CortexSingle_DataSheet_3.0.pdf",
]

seen: set[str] = set()
for url in PAGES:
    print("===", url)
    try:
        html = requests.get(url, headers=UA, timeout=60).text
    except requests.RequestException as e:
        print(" ERR", e)
        continue
    print(" html", len(html))
    found = set()
    for m in re.findall(r"https?://[^\s\"'<>]+", html):
        low = m.lower()
        if not any(x in low for x in (".jpg", ".jpeg", ".png", ".webp", ".avif", "image", "cdn", "uploads")):
            continue
        if any(x in low for x in ("logo", "favicon", "icon", "sprite", "font")):
            continue
        found.add(m.split("?")[0])
    for m in re.findall(r'/(?:_next/image|uploads|wp-content)[^"\']+', html):
        if m.startswith("http"):
            found.add(m)
        else:
            base = "https://ampsortation.com" if "ampsortation" in url else "https://www.amprobotics.com"
            found.add(base + m.split("?")[0])
    for u in sorted(found):
        if u in seen:
            continue
        seen.add(u)
        try:
            r = requests.get(u, headers=UA, timeout=60)
        except requests.RequestException:
            continue
        if r.status_code != 200 or len(r.content) < 15000:
            print("  skip", r.status_code, len(r.content), u[:100])
            continue
        h = hashlib.md5(r.content).hexdigest()[:12]
        magic = r.content[:12]
        if r.content[:4] == b"RIFF":
            ext = ".webp"
        elif r.content[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif r.content[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif b"ftypavif" in r.content[:32]:
            ext = ".avif"
        else:
            ext = ".bin"
        p = OUT / f"{h}{ext}"
        p.write_bytes(r.content)
        try:
            im = Image.open(p).convert("RGB")
            t = im.copy()
            t.thumbnail((800, 800))
            t.save(OUT / f"{h}.qa.jpg", quality=85)
            print("  OK", h, im.size, len(r.content), u[:110])
        except Exception as e:
            print("  SAVED", h, ext, len(r.content), e, u[:90])

print("done files", len(list(OUT.glob("*"))))
