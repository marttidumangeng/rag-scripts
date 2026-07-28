"""Download + preview Piaggio heroes vs OEM social stills."""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0"}
OUT = _RESEARCH / "staging" / "tmp" / "piaggio"
OUT.mkdir(parents=True, exist_ok=True)

URLS = {
    "cdn-3767": "https://cdn.robotaigeek.com/robots/original/robot-3767-gitamini-v1783776510.webp",
    "cdn-3765": "https://cdn.robotaigeek.com/robots/original/robot-3765-gita-plus-v1783776510.webp",
    "oem-mini": "https://a.storyblok.com/f/255103/1200x627/58e82e90d4/b2c-shop-gitamini-social-sharing.jpg",
    "oem-plus": "https://a.storyblok.com/f/255103/1200x627/a2f2fd984d/b2c-shop-gitaplus-social-sharing.jpg",
}


def main() -> int:
    for name, url in URLS.items():
        raw = requests.get(url, headers=UA, timeout=60).content
        im = Image.open(BytesIO(raw)).convert("RGB")
        path = OUT / f"{name}.jpg"
        im.save(path, quality=90)
        print(name, im.size, len(raw), path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
