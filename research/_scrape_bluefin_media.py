"""Find all /-/media/ URLs on Bluefin pages."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
URLS = {
    "bf9": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-9-autonomous-underwater-vehicle",
    "bf12": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-12-unmanned-underwater-vehicle",
    "bf21": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-21-autonomous-underwater-vehicle",
    "hauv": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-hauv",
}


def main() -> int:
    for key, url in URLS.items():
        r = requests.get(url, timeout=60, headers=UA)
        media = sorted(set(re.findall(r'/-/media/[^"\'?\s>]+', r.text)))
        print(f"\n=== {key} media={len(media)}")
        for m in media:
            if any(x in m.lower() for x in ("bluefin", "hauv", "uuv", "image", "jpg", "png", "ashx")):
                print(" ", m[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
