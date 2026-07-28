"""Scrape GDMS Bluefin product pages for hero image URLs (browser UA)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URLS = {
    "bf9": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-9-autonomous-underwater-vehicle",
    "bf12": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-12-unmanned-underwater-vehicle",
    "bf21": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-21-autonomous-underwater-vehicle",
    "hauv": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-hauv",
}

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def abs_url(i: str) -> str:
    if i.startswith("//"):
        return "https:" + i
    if i.startswith("/"):
        return "https://gdmissionsystems.com" + i
    return i


def main() -> int:
    out: dict = {}
    for key, url in URLS.items():
        r = requests.get(url, timeout=60, headers=UA)
        print(key, r.status_code, len(r.text))
        og = re.search(
            r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)',
            r.text,
        )
        if not og:
            og = re.search(
                r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
                r.text,
            )
        imgs = re.findall(
            r'(?:src|data-src|content)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)',
            r.text,
            re.I,
        )
        ashx = re.findall(r'(https?://[^"\']+/-/media/[^"\']+)', r.text)
        ranked: list[tuple[int, str]] = []
        for i in imgs + ashx:
            i = abs_url(i)
            low = i.lower()
            score = 0
            if any(x in low for x in ("bluefin", "hauv", "uuv", "underwater")):
                score += 5
            if "/media/" in low:
                score += 2
            if any(x in low for x in ("logo", "icon", "favicon", "sprite", "nav")):
                score -= 10
            ranked.append((score, i))
        ranked.sort(reverse=True)
        uniq: list[tuple[int, str]] = []
        seen: set[str] = set()
        for score, i in ranked:
            if i in seen:
                continue
            seen.add(i)
            uniq.append((score, i))
        out[key] = {
            "url": url,
            "og": abs_url(og.group(1)) if og else None,
            "cands": [i for s, i in uniq[:15] if s > 0],
        }
        print("  og", out[key]["og"])
        for score, i in uniq[:8]:
            print(f"  [{score}]", i[:130])
    path = _RESEARCH / "staging" / "reports" / "bluefin-images.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
