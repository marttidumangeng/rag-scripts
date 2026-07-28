"""Search saved/fetched UR HTML for ur5e/ur10e storyblok assets."""

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


def main() -> int:
    html = WebFetcher(stealth=False).get(
        "https://www.universal-robots.com/products/e-series/"
    ) or ""
    for token in ("ur5e", "ur10e", "ur12e", "ur16e", "ur18", "ur8"):
        hits = [m.group(0) for m in re.finditer(rf"https://a\.storyblok\.com/[^\"'\s>]*{token}[^\"'\s>]*", html, re.I)]
        print(token, "hits", len(hits))
        for h in hits[:5]:
            print(" ", h[:140])
    # also any /ur5e in page
    print("ur5e text mentions", len(re.findall(r"ur5e", html, re.I)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
