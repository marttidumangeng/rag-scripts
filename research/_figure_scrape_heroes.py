"""Scrape Figure OEM for Figure 03 hero candidates (not F.02)."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
OUT = Path("staging/tmp/figure-heroes")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    "https://www.figure.ai/figure",
    "https://www.figure.ai/news/introducing-figure-03",
    "https://www.figure.ai/",
    "https://www.figure.ai/news/ramping-figure-03-production",
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
    for m in re.findall(r"https://[^\s\"'<>]+", html):
        low = m.lower()
        if not any(x in low for x in (".jpg", ".jpeg", ".png", ".webp", "image", "cdn")):
            continue
        if any(x in low for x in ("logo", "favicon", "icon", "sprite")):
            continue
        clean = m.split("?")[0].rstrip("\\")
        found.add(clean)
    # relative /_next/image
    for m in re.findall(r'/_next/image\?[^"\']+', html):
        found.add("https://www.figure.ai" + m.split("&")[0].replace("&amp;", "&"))
    for u in sorted(found):
        if u in seen:
            continue
        seen.add(u)
        try:
            r = requests.get(u, headers=UA, timeout=60)
        except requests.RequestException as e:
            print("  fail", e, u[:90])
            continue
        if r.status_code != 200 or len(r.content) < 12000:
            print("  skip", r.status_code, len(r.content), u[:100])
            continue
        h = hashlib.md5(r.content).hexdigest()[:12]
        if r.content[:4] == b"RIFF":
            ext = ".webp"
        elif r.content[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif r.content[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        else:
            ext = ".bin"
        p = OUT / f"{h}{ext}"
        p.write_bytes(r.content)
        try:
            im = Image.open(p).convert("RGB")
            t = im.copy()
            t.thumbnail((700, 700))
            t.save(OUT / f"{h}.qa.jpg", quality=85)
            print("  OK", h, im.size, len(r.content), u[:110])
        except Exception as e:
            print("  OK-noqa", h, len(r.content), e, u[:90])
