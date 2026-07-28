"""Crop Flex marketing robot region; QA scrubber + DVIDS hull still."""
from __future__ import annotations

from pathlib import Path

import requests
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path("staging/tmp/gecko-qa2")
OUT.mkdir(parents=True, exist_ok=True)

# Crop text-heavy Flex graphic to robot-dominant region
flex_src = Path("staging/tmp/gecko-qa/flex.jpg")
if flex_src.is_file():
    flex = Image.open(flex_src).convert("RGB")
    w, h = flex.size
    print("flex size", w, h)
    # Avoid top title band; keep pipe + robot body (right/photo side)
    crop = flex.crop((int(w * 0.35), int(h * 0.28), int(w * 0.99), int(h * 0.98)))
    crop.save(OUT / "flex-crop.jpg", quality=92)
    print("flex-crop", crop.size)

# Robotic Gizmos page images
html = requests.get(
    "https://www.roboticgizmos.com/toka-flex-pipe-inspection-robot/",
    headers=UA,
    timeout=45,
).text
print("gizmos chars", len(html))
import re

for u in re.findall(r"(https://[^\"'\s>]+\.(?:jpg|jpeg|png|webp))", html, re.I):
    low = u.lower()
    if any(x in low for x in ("logo", "icon", "avatar", "emoji", "gravatar")):
        continue
    print(" ", u[:140])

# YouTube maxres for Gecko TOKA Flex official if known
# common: search via page scrape of gizmos for youtube embed
for m in re.finditer(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})", html):
    vid = m.group(1)
    print("yt", vid)
    for q in ("maxresdefault", "sddefault", "hqdefault"):
        thumb = f"https://i.ytimg.com/vi/{vid}/{q}.jpg"
        r = requests.get(thumb, headers=UA, timeout=30)
        print(" ", q, r.status_code, len(r.content))
        if r.ok and len(r.content) > 5000:
            (OUT / f"flex-yt-{vid}-{q}.jpg").write_bytes(r.content)
            break
