"""Download candidate Stryker Mako heroes; inspect HTML for DAM URLs."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from web_extract import WebFetcher, parse_page

OUT = Path("staging/tmp/stryker-heroes")
OUT.mkdir(parents=True, exist_ok=True)

pages = [
    "https://www.stryker.com/us/en/joint-replacement/systems/Mako_SmartRobotics_Overview.html",
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-total-knee.html",
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-total-hip.html",
    "https://www.stryker.com/us/en/joint-replacement/systems/mako-partial-knee.html",
]

f = WebFetcher()
pat = re.compile(
    r"(?:https://www\.stryker\.com)?(/content/dam/stryker/[^\"'\s>]+\.(?:jpg|jpeg|png|webp))",
    re.I,
)

all_urls: set[str] = set()
for url in pages:
    p = parse_page(f, url, rendered=False)
    html = getattr(p, "html", None) or getattr(p, "raw_html", None) or ""
    if not html:
        # fallback requests
        try:
            html = requests.get(url, timeout=60).text
        except Exception as e:
            print("page fail", url, e)
            continue
    print("===", url, "html", len(html))
    for m in pat.findall(html):
        full = m if m.startswith("http") else "https://www.stryker.com" + m
        if "globe_icon" in full or "flag" in full.lower():
            continue
        all_urls.add(full.split("?")[0])

# Known from prior parse
extra = [
    "https://www.stryker.com/content/dam/stryker/joint-replacement/systems/mako-system-overview/images/Mako%204%20Family%205_1920x1080.jpg",
    "https://www.stryker.com/content/dam/stryker/australia-new-zealand/jr/images/Mako%204%20THA%202K.jpg",
    "https://www.stryker.com/content/dam/stryker/joint-replacement/systems/mako-system-overview/images/Mako%204%20Family%205_.jpg",
]
# try common variants
for base in [
    "https://www.stryker.com/content/dam/stryker/joint-replacement/systems/mako-system-overview/images/",
]:
    for name in [
        "Mako%204%20Family%205_1920x1080.jpg",
        "Mako%204%20Family%205_.jpg",
        "Mako%204%20Family%205.png",
        "Mako4Family.jpg",
    ]:
        extra.append(base + name)

all_urls.update(extra)
print("candidates", len(all_urls))
for u in sorted(all_urls):
    try:
        r = requests.get(u, timeout=60)
        ok = r.status_code == 200 and len(r.content) > 5000
        h = hashlib.md5(r.content).hexdigest()[:12] if ok else "-"
        print(r.status_code, len(r.content), h, u[:140])
        if ok:
            name = hashlib.md5(u.encode()).hexdigest()[:10] + Path(u.split("?")[0]).suffix.lower()
            (OUT / name).write_bytes(r.content)
    except Exception as e:
        print("ERR", u[:80], e)

print("saved", list(OUT.glob("*")))
