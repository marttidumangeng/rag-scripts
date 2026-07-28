#!/usr/bin/env python3
"""Find Go2-W specific OEM assets (og:image + tire keywords)."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0"}
QA = Path("staging/unitree_fleet_qa")
QA.mkdir(parents=True, exist_ok=True)

BAD = {
    "e0b39e851afc",  # A2 footed
    "32a8193feb1a",  # A2-W industrial
    "23573d14770a",  # A2-W canyon
}


def main() -> int:
    for page in (
        "https://www.unitree.com/go2-w/",
        "https://www.unitree.com/mobile/go2-w/",
    ):
        html = requests.get(page, headers=UA, timeout=60).text
        print("PAGE", page, "len", len(html))
        for pat in (
            r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)',
            r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image',
            r'"og:image"\s*:\s*"([^"]+)"',
            r'ogImage["\']?\s*[:=]\s*["\']([^"\']+)',
        ):
            for m in re.findall(pat, html, re.I):
                print("  og-ish", m[:120])

        urls = re.findall(r"https://[^\"'\s>]+\.(?:png|jpg|jpeg|webp)", html, re.I)
        # also relative /images/
        rel = re.findall(r'["\'](/images/[^"\']+\.(?:png|jpg|jpeg|webp))["\']', html, re.I)
        for r in rel:
            urls.append("https://www.unitree.com" + r)

        # prefer names mentioning wheel/tire/go2
        scored = []
        for u in dict.fromkeys(urls):
            score = 0
            lu = u.lower()
            if "go2" in lu:
                score += 5
            if any(k in lu for k in ("wheel", "tire", "tyre", "wheeled")):
                score += 3
            if "800x800" in lu or "1200" in lu or "1600" in lu:
                score += 1
            if score:
                scored.append((score, u))
        scored.sort(reverse=True)
        print("scored", len(scored))
        for score, u in scored[:25]:
            print(f"  s={score}", u[:110])

    # Download remaining unscanned cands from go2-w page (all unique large)
    html = requests.get("https://www.unitree.com/go2-w/", headers=UA, timeout=60).text
    urls = list(dict.fromkeys(re.findall(r"https://[^\"'\s>]+\.(?:png|jpg|jpeg|webp)", html, re.I)))
    print("downloading all page imgs", len(urls))
    kept = []
    for u in urls:
        if "unitree.com" not in u:
            continue
        try:
            b = requests.get(u, headers=UA, timeout=45).content
        except Exception:
            continue
        if len(b) < 40000:
            continue
        if not (b.startswith((b"\x89PNG", b"\xff\xd8")) or (b[:4] == b"RIFF" and b[8:12] == b"WEBP")):
            continue
        md5 = hashlib.md5(b).hexdigest()
        if any(md5.startswith(x) for x in BAD):
            continue
        ext = "png" if b.startswith(b"\x89PNG") else ("jpg" if b.startswith(b"\xff\xd8") else "webp")
        path = QA / f"go2w_all_{md5[:12]}.{ext}"
        if not path.exists():
            path.write_bytes(b)
        kept.append((len(b), md5, u, path.name))
        print(f"kept {md5[:12]} {len(b)} {path.name}")
    kept.sort(reverse=True)
    print("top", [(k[1][:12], k[0], k[3]) for k in kept[:12]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
