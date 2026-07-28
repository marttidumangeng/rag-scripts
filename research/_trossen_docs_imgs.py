"""Download Interbotix docs images (product + drawings) for galleries."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path("staging/tmp/trossen-gallery")
OUT.mkdir(parents=True, exist_ok=True)
BASE = "https://docs.trossenrobotics.com/interbotix_xsarms_docs/"
PAGES = [
    "specifications/px100.html",
    "specifications/vx300.html",
    "specifications/vx300s.html",
    "specifications/wx250.html",
    "specifications/wx250s.html",
]

# Known asset names often used in docs
GUESSES = [
    "_images/px100.png",
    "_images/vx300.png",
    "_images/vx300s.png",
    "_images/wx250.png",
    "_images/wx250s.png",
    "_images/px100_drawing.png",
    "_images/vx300s_drawing.png",
    "_images/wx250s_drawing.png",
    "_images/px100_dim.png",
    "_images/vx300s_dim.png",
    "_images/wx250s_dim.png",
    "_images/px100.jpg",
    "_images/frame_xsarms.png",
]

for page in PAGES:
    url = BASE + page
    html = requests.get(url, headers=UA, timeout=60).text
    found = set(re.findall(r"(_images/[A-Za-z0-9_./-]+\.(?:png|jpg|jpeg))", html))
    print("===", page, "found", len(found))
    for rel in sorted(found):
        print(" ", rel)

for rel in GUESSES:
    full = BASE + rel.lstrip("/")
    r = requests.get(full, headers=UA, timeout=45)
    print("guess", r.status_code, len(r.content), rel)
    if r.status_code == 200 and len(r.content) > 8000:
        h = hashlib.md5(r.content).hexdigest()[:12]
        ext = Path(rel).suffix or ".bin"
        (OUT / f"docs_{h}{ext}").write_bytes(r.content)
        print("  saved", h)
