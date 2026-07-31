"""Search for missing EP product pages via Serper + site scrape."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

MISSING = [
    "QDD30T", "QDD30TS", "EPT20-30TW", "JXO", "ES12-25WA", "ES20-WA",
    "ES12-12ES", "ES12-25MM", "ES10-10ES", "ES10-22MM", "ES18-40WA",
    "ES14-30WA", "RPL251", "RPL301", "WPL201", "HPL152",
]


def serper(query: str) -> list[dict]:
    key = os.environ.get("SERPER_API_KEY") or os.environ.get("SERPER_KEY")
    if not key:
        print("NO SERPER KEY")
        return []
    r = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": query, "num": 10},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("organic") or []


def main() -> None:
    results = {}
    for model in MISSING:
        q = f'site:ep-equipment.com {model}'
        hits = serper(q)
        urls = [h.get("link") for h in hits if h.get("link")]
        titles = [(h.get("title"), h.get("link")) for h in hits]
        results[model] = titles
        print(f"\n=== {model} ===")
        for t, u in titles[:5]:
            print(f"  {t}")
            print(f"    {u}")

    # Also try alternate slug patterns for a few
    alts = [
        "https://ep-equipment.com/product/qdd30t/",
        "https://ep-equipment.com/product/qdd30ts/",
        "https://ep-equipment.com/product/qdd30t-30ts",
        "https://ep-equipment.com/product/ept20-30tw",
        "https://ep-equipment.com/product/wpl201",
        "https://ep-equipment.com/product/hpl152",
        "https://ep-equipment.com/product/rpl251/",
        "https://ep-equipment.com/product/rpl301/",
        "https://ep-equipment.com/product/es12-25wa",
        "https://ep-equipment.com/product/es20wa/",
        "https://ep-equipment.com/product/es20-wa",
        "https://ep-equipment.com/product/jxo",
        "https://ep-equipment.com/products/qdd30t-30ts/",
        "https://ep-equipment.com/products/wpl201/",
    ]
    print("\n=== ALT SLUG CHECK ===")
    for u in alts:
        try:
            r = requests.get(u, timeout=20, headers=HEADERS, allow_redirects=True)
            print(f"{r.status_code} {r.url}")
        except Exception as e:
            print(f"ERR {u}: {e}")

    Path("staging/reports/_ep1274_serper.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
