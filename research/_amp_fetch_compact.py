"""Fetch AMP Compact product-page images into staging/tmp/amp-heroes."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
OUT = Path("staging/tmp/amp-heroes")
OUT.mkdir(parents=True, exist_ok=True)

URLS = [
    "https://www.amprobotics.com/compact-robotic-sorting",
    "https://ampsortation.com/technologies/delta-compact",
    "https://ampsortation.com/technologies/delta",
]


def main() -> int:
    for url in URLS:
        print("===", url)
        try:
            r = requests.get(url, headers=UA, timeout=60)
            print(" status", r.status_code, "len", len(r.text))
        except requests.RequestException as e:
            print(" ERR", e)
            continue
        html = r.text
        found = set(re.findall(r"https?://images\.prismic\.io/[^\s\"'<>]+", html))
        found |= set(
            re.findall(r"https?://[^\s\"'<>]+\.(?:png|jpe?g|webp|avif)", html, re.I)
        )
        for u in sorted(found):
            u2 = u.split("?")[0]
            low = u2.lower()
            if any(x in low for x in ("logo", "favicon", "icon", "sprite")):
                continue
            try:
                ir = requests.get(u, headers=UA, timeout=60)
            except requests.RequestException:
                continue
            if ir.status_code != 200 or len(ir.content) < 20000:
                print("  skip", ir.status_code, len(ir.content), u2[-70:])
                continue
            h = hashlib.md5(ir.content).hexdigest()[:12]
            if ir.content[:3] == b"\xff\xd8\xff":
                ext = ".jpg"
            elif ir.content[:8] == b"\x89PNG\r\n\x1a\n":
                ext = ".png"
            elif ir.content[:4] == b"RIFF":
                ext = ".webp"
            else:
                ext = ".bin"
            p = OUT / f"{h}{ext}"
            if not p.exists():
                p.write_bytes(ir.content)
                print("  NEW", h, len(ir.content), u2[-90:])
            else:
                print("  have", h, u2[-90:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
