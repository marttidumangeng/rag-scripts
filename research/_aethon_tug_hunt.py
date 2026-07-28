"""Hunt a real classic Aethon TUG photo (robot 86 has a Locus Vector!)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path("staging/tmp/aethon-qa")
OUT.mkdir(parents=True, exist_ok=True)

pages = [
    "https://aethon.com/aethon-tug-autonomous-mobile-robot-discussed-ria-magazine/",
    "https://aethon.com/tug-autonomous-robot-highlighted-beckers-hospital-review/",
    "https://aethon.com/resources/",
    "https://www.therobotreport.com/aethon-tug/",
]
yt_ids = [
    # from resources page titles / known promos — fill after scrape
]

for url in pages:
    r = requests.get(url, headers=UA, timeout=45)
    print("PAGE", r.status_code, len(r.content), url)
    if r.status_code != 200:
        continue
    for m in re.finditer(
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r.text,
    ):
        print(" yt", m.group(1))
        yt_ids.append(m.group(1))
    imgs = re.findall(
        r"https://cdn\.aethon\.com/[^\"'\s>]+\.(?:jpg|jpeg|png|webp)",
        r.text,
        re.I,
    )
    imgs += re.findall(
        r"https://[^\"'\s>]+\.(?:jpg|jpeg|png|webp)",
        r.text,
        re.I,
    )
    for u in sorted(set(imgs)):
        low = u.lower()
        if any(x in low for x in ("logo", "icon", "favicon", "emoji", "avatar")):
            continue
        if "tug" in low or "aethon" in low or "wp-content" in low:
            print(" ", u[:140])

for vid in sorted(set(yt_ids))[:12]:
    for q in ("maxresdefault", "hqdefault"):
        thumb = f"https://i.ytimg.com/vi/{vid}/{q}.jpg"
        r = requests.get(thumb, headers=UA, timeout=30)
        print("YT", vid, q, r.status_code, len(r.content))
        if r.ok and len(r.content) > 8000:
            (OUT / f"yt-tug-{vid}-{q}.jpg").write_bytes(r.content)
            break
