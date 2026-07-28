"""Scrape Liquid Robotics + Asensus OEM pages with browser UA."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
URLS = [
    "https://www.liquid-robotics.com/",
    "https://www.liquid-robotics.com/wave-glider/overview/",
    "https://www.liquid-robotics.com/wave-glider/",
    "https://www.liquid-robotics.com/wave-glider/how-it-works/",
    "https://www.liquid-robotics.com/wave-glider/instrumentation/",
    "https://www.liquid-robotics.com/product/wave-glider/",
    "https://www.asensus.com/",
    "https://www.asensus.com/senhance",
    "https://www.asensus.com/isu",
    "https://www.asensus.com/senhance-surgical-system",
    "https://karlstorz.com/",
]


def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main() -> int:
    out = _RESEARCH / "staging" / "tmp" / "liquid-asensus-pages"
    out.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    for url in URLS:
        slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[:80]
        try:
            r = sess.get(url, timeout=40, allow_redirects=True)
            print(f"{r.status_code} final={r.url} chars={len(r.text)} <- {url}")
            (out / f"{slug}.html").write_text(r.text, encoding="utf-8", errors="replace")
            text = clean_text(r.text)
            (out / f"{slug}.txt").write_text(text, encoding="utf-8", errors="replace")
            print("  text_chars=", len(text), "title=", (BeautifulSoup(r.text, "html.parser").title or type("", (), {"string": ""})).string)
        except Exception as e:
            print(f"FAIL {url}: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
