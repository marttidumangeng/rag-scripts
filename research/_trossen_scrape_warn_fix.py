"""Scrape Trossen PDP prices + gallery candidates + discontinued banners."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
OUT = Path("staging/tmp/trossen-gallery")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = {
    5266: "https://www.trossenrobotics.com/aloha-solo",
    5267: "https://www.trossenrobotics.com/aloha-stationary",
    5268: "https://www.trossenrobotics.com/mobile-ai",
    5269: "https://www.trossenrobotics.com/pincherx100",
    5270: "https://www.trossenrobotics.com/viperx-300",
    5271: "https://www.trossenrobotics.com/viperx-aloha",
    5272: "https://www.trossenrobotics.com/widowx-250",
    5273: "https://www.trossenrobotics.com/widowx-ai",
    5274: "https://www.trossenrobotics.com/widowx-aloha-set",
}

DOCS_EXTRA = [
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/_images/px100.png",
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/_images/vx300s.png",
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/_images/vx300.png",
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/_images/wx250s.png",
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/_images/wx250.png",
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/_images/xsarms_family.png",
]


def main() -> int:
    for rid, url in PAGES.items():
        print("===", rid, url)
        r = requests.get(url, headers=UA, timeout=60)
        html = r.text
        low = html.lower()
        disc = "discontinued" in low or "this product has been discontinued" in low
        prices = re.findall(r"\$[\d,]+(?:\.\d{2})?", html)
        print("  discontinued?", disc, "prices sample", prices[:8])
        # wix media
        found = set(re.findall(r"https://static\.wixstatic\.com/media/[^\s\"'<>]+", html))
        kept = []
        seen_h: set[str] = set()
        for u in sorted(found):
            if "fill" not in u and "~mv2" not in u:
                continue
            try:
                ir = requests.get(u, headers=UA, timeout=45)
            except requests.RequestException:
                continue
            if ir.status_code != 200 or len(ir.content) < 40000:
                continue
            h = hashlib.md5(ir.content).hexdigest()[:12]
            if h in seen_h:
                continue
            seen_h.add(h)
            ext = (
                ".png"
                if ir.content[:8] == b"\x89PNG\r\n\x1a\n"
                else ".jpg"
                if ir.content[:3] == b"\xff\xd8\xff"
                else ".bin"
            )
            p = OUT / f"{rid}_{h}{ext}"
            p.write_bytes(ir.content)
            kept.append((h, len(ir.content), str(p.name), u[:90]))
            if len(kept) >= 8:
                break
        for row in kept:
            print("  img", row[0], row[1], row[2])

    print("=== docs extras")
    for u in DOCS_EXTRA:
        try:
            ir = requests.get(u, headers=UA, timeout=45)
        except requests.RequestException as e:
            print(" ERR", u, e)
            continue
        print(" ", ir.status_code, len(ir.content), u.split("/")[-1])
        if ir.status_code == 200 and len(ir.content) > 10000:
            h = hashlib.md5(ir.content).hexdigest()[:12]
            ext = ".png" if ir.content[:8] == b"\x89PNG\r\n\x1a\n" else ".bin"
            (OUT / f"docs_{h}{ext}").write_bytes(ir.content)
            print("   saved", h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
