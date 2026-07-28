"""Scrape Lumos product pages for text + images."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path(__file__).resolve().parent / "staging" / "tmp" / "lumos-pages"
OUT.mkdir(parents=True, exist_ok=True)

URLS = {
    5290: "https://www.lumosbot.tech/products/lud",
    5291: "https://www.lumosbot.tech/products/lus2",
    5292: "https://www.lumosbot.tech/products/mos",
    5293: "https://www.lumosbot.tech/products/luxiaoming",
    5294: "https://www.lumosbot.tech/products/touch",
}


def strip_html(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    for rid, url in URLS.items():
        r = requests.get(url, timeout=45, headers=UA)
        path = OUT / f"{rid}.html"
        path.write_text(r.text, encoding="utf-8")
        text = strip_html(r.text)
        print(f"=== {rid} {r.status_code} {len(r.text)} ===")
        print(text[:3000])
        print()
        imgs = sorted(
            set(
                re.findall(
                    r"https?://[^\"'\s>]+\.(?:webp|png|jpg|jpeg)(?:\?[^\"'\s>]*)?",
                    r.text,
                    flags=re.I,
                )
            )
        )
        print(f"imgs {len(imgs)}")
        for u in imgs[:20]:
            print(" ", u[:140])
        print()


if __name__ == "__main__":
    main()
