"""Find Storyblok UR product renders from listing + working PDPs."""

from __future__ import annotations

import re
import sys
import time
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

URLS = [
    "https://www.universal-robots.com/products/",
    "https://www.universal-robots.com/products/e-series/",
    "https://www.universal-robots.com/products/cobots/",
    "https://www.universal-robots.com/products/ur3e/",
    "https://www.universal-robots.com/products/ur16e/",
    "https://www.universal-robots.com/products/ur20/",
    "https://www.universal-robots.com/products/ur30/",
    "https://www.universal-robots.com/products/ur15/",
    "https://www.universal-robots.com/products/ur7e/",
]


def main() -> int:
    f = WebFetcher(stealth=False)
    found: dict[str, set[str]] = {}
    for u in URLS:
        html = f.get(u) or ""
        print(u, "len", len(html))
        for m in re.finditer(
            r"https://a\.storyblok\.com/[^\"'\s>]+/(ur[a-z0-9\-]+)\.(png|jpg|jpeg|webp)",
            html,
            re.I,
        ):
            full = m.group(0).split("?")[0]
            key = m.group(1).lower()
            found.setdefault(key, set()).add(full)
        time.sleep(0.25)
    for k in sorted(found):
        print(k, len(found[k]))
        for u in sorted(found[k])[:3]:
            print(" ", u)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
