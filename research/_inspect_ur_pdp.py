"""Inspect Universal Robots PDP HTML for hero/spec patterns."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from web_extract import WebFetcher

URL = "https://www.universal-robots.com/products/ur3e/"


def main() -> int:
    html = WebFetcher(stealth=False).get(URL) or ""
    (_RESEARCH_DIR / "staging/reports/ur3e_sample.html").write_text(html[:250000], encoding="utf-8")
    print("html_len", len(html))

    imgs = re.findall(r"https?://[^\"'\s>]+\.(?:jpg|jpeg|png|webp)(?:\?[^\"'\s>]*)?", html, re.I)
    seen: set[str] = set()
    uniq: list[str] = []
    for u in imgs:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    print("img_urls", len(uniq))
    for u in uniq[:25]:
        low = u.lower()
        mark = ""
        if any(x in low for x in ("ur3", "product", "cobot", "robot")):
            mark = " *"
        print(f"  {u[:140]}{mark}")

    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.S | re.I,
    ):
        print("ld+json", re.sub(r"\s+", " ", m.group(1))[:240])

    # payload/reach near text
    for pat in (
        r"Payload[^<]{0,80}",
        r"Reach[^<]{0,80}",
        r"3\s*kg",
        r"500\s*mm",
        r"data-payload",
        r"spec-table",
    ):
        ms = re.findall(pat, html, re.I)
        if ms:
            print(pat, "->", [re.sub(r"\s+", " ", x)[:100] for x in ms[:3]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
