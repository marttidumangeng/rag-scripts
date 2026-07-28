"""Scrape WidowX AI PDP for product heroes; fix 5273 primary 403."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
OUT = Path("staging/tmp/trossen-wxai")
OUT.mkdir(parents=True, exist_ok=True)
URL = "https://www.trossenrobotics.com/widowx-ai"


def main() -> int:
    html = requests.get(URL, headers=UA, timeout=60).text
    found = set(re.findall(r"https://static\.wixstatic\.com/media/[^\s\"'<>]+", html))
    print("wix urls", len(found))
    kept = []
    seen: set[str] = set()
    for u in sorted(found):
        if "fill" not in u and "~mv2" not in u:
            continue
        try:
            r = requests.get(u, headers=UA, timeout=60)
        except requests.RequestException:
            continue
        if r.status_code != 200 or len(r.content) < 40000:
            continue
        h = hashlib.md5(r.content).hexdigest()[:12]
        if h in seen:
            continue
        seen.add(h)
        ext = (
            ".png"
            if r.content[:8] == b"\x89PNG\r\n\x1a\n"
            else ".jpg"
            if r.content[:3] == b"\xff\xd8\xff"
            else ".bin"
        )
        p = OUT / f"{h}{ext}"
        p.write_bytes(r.content)
        try:
            im = Image.open(p).convert("RGB")
            qa = OUT / f"{h}.qa.jpg"
            im.resize((min(800, im.size[0]), min(600, im.size[1]))).save(qa, quality=80)
        except Exception as e:  # noqa: BLE001
            print("  qa fail", h, e)
            continue
        kept.append((h, len(r.content), p.name, u[:100]))
        print("NEW", h, len(r.content), u[:100])
        if len(kept) >= 12:
            break
    print("kept", len(kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
