"""Find image refs in Lumos HTML + download current CDN heroes for QA."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

PAGES = Path("staging/tmp/lumos-pages")
OUT = Path("staging/tmp/lumos-heroes")
OUT.mkdir(parents=True, exist_ok=True)

for p in sorted(PAGES.glob("*.html")):
    html = p.read_text(encoding="utf-8")
    urls = set()
    for m in re.finditer(r"(?:src|href)=[\"']([^\"']+)[\"']", html, re.I):
        u = m.group(1)
        if any(x in u.lower() for x in (".webp", ".png", ".jpg", ".jpeg", "image", "upload", "cdn")):
            urls.add(u)
    for m in re.finditer(r"/_ipx/[^\"'\s>]+", html):
        urls.add(m.group(0))
    print(p.name, len(urls))
    for u in sorted(urls)[:30]:
        print(" ", u[:140])

c = ResearchApiClient()
for r in c.list_robots_for_company(70) or []:
    d = c._get(f"robots/robots/{r['id']}/")
    img = d.get("s3_image") or d.get("image") or ""
    if not img:
        continue
    ext = ".webp" if ".webp" in img else ".png" if ".png" in img else ".jpg"
    path = OUT / f"{r['id']}{ext}"
    raw = requests.get(img, timeout=30).content
    path.write_bytes(raw)
    print("hero", r["id"], len(raw), path)
