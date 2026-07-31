"""Deep resolve EP Equipment missing models + scrape live PDPs."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

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
# Force UTF-8 stdout on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MISSING = [
    "QDD30T", "QDD30TS", "QDD30S", "EPT20-30TW", "JXO", "JX0",
    "ES12-25WA", "ES20-WA", "ES12-12ES", "ES12-25MM", "ES10-10ES",
    "ES10-22MM", "ES18-40WA", "ES14-30WA", "RPL251", "RPL301",
    "WPL201", "HPL152", "WPL", "HPL",
]


def serper(query: str) -> list[dict]:
    key = os.environ.get("SERPER_API_KEY") or os.environ.get("SERPER_KEY")
    if not key:
        return []
    r = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": query, "num": 8},
        timeout=30,
    )
    r.raise_for_status()
    return (r.json().get("organic") or [])


def check_url(url: str) -> dict:
    try:
        r = requests.get(url, timeout=30, headers=HEADERS, allow_redirects=True)
        title = ""
        if r.status_code == 200:
            m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.I | re.S)
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()[:140]
        return {"status": r.status_code, "url": r.url, "title": title, "chars": len(r.text)}
    except Exception as e:
        return {"error": str(e), "url": url}


def main() -> None:
    # Load all product URLs from prior map
    umap = json.loads(
        Path("staging/reports/_ep1274_url_map.json").read_text(encoding="utf-8")
    )
    all_urls = umap.get("all_product_urls") or []
    # Keep only /product/{slug}/ style
    pdp = sorted(
        {
            u
            for u in all_urls
            if re.search(r"/product/[a-z0-9][\w\-]*/?$", u, re.I)
            and "product-category" not in u
        }
    )
    print(f"PDP-like URLs: {len(pdp)}")
    for u in pdp:
        slug = u.rstrip("/").split("/")[-1]
        print(f"  {slug}")

    Path("staging/reports/_ep1274_all_slugs.txt").write_text(
        "\n".join(u.rstrip("/").split("/")[-1] for u in pdp), encoding="utf-8"
    )

    print("\n=== SERPER MISSING ===")
    serper_out = {}
    for model in MISSING:
        hits = serper(f'site:ep-equipment.com "{model}"')
        serper_out[model] = [
            {"title": h.get("title"), "link": h.get("link"), "snippet": h.get("snippet")}
            for h in hits
        ]
        print(f"\n{model}:")
        for h in hits[:4]:
            print(f"  {(h.get('title') or '')[:80]}")
            print(f"    {h.get('link')}")

    # Candidate URL checks
    candidates = [
        "https://ep-equipment.com/product/qdd30s/",
        "https://ep-equipment.com/product/qdd30t/",
        "https://ep-equipment.com/product/jx0/",
        "https://ep-equipment.com/product/jxo/",
        "https://ep-equipment.com/product/rpl251/",
        "https://ep-equipment.com/product/rpl301/",
        "https://ep-equipment.com/product/rpl301e/",
        "https://ep-equipment.com/product/wpl201/",
        "https://ep-equipment.com/product/hpl152/",
        "https://ep-equipment.com/product/es12-25wa/",
        "https://ep-equipment.com/product/es20-wa/",
        "https://ep-equipment.com/product/es18-40wa/",
        "https://ep-equipment.com/product/es14-30wa/",
        "https://ep-equipment.com/product/es12-12es/",
        "https://ep-equipment.com/product/es10-10es/",
        "https://ep-equipment.com/product/ept20-30tw/",
        "https://ep-equipment.com/product/ept20-rap/",
        "https://ep-equipment.com/product/esl122/",
        "https://ep-equipment.com/product/es15-15es/",
        "https://ep-equipment.com/product/kpl201/",
        "https://ep-equipment.com/product/epl185/",
        "https://ep-equipment.com/product/epl154/",
        "https://ep-equipment.com/product/ept25-wa/",
        "https://ep-equipment.com/product/ept20-20wa/",
        # possible renames from slug list
        "https://ep-equipment.com/product/wpl202/",
        "https://ep-equipment.com/product/hpl201/",
        "https://ep-equipment.com/product/hpl202/",
        "https://ep-equipment.com/product/es12-12emm/",
        "https://ep-equipment.com/product/es10-10emm/",
        "https://ep-equipment.com/product/es12wa/",
        "https://ep-equipment.com/product/es14wa/",
        "https://ep-equipment.com/product/es18wa/",
        "https://ep-equipment.com/product/es20wa/",
    ]
    # Also add any slug containing our tokens
    tokens = [
        "qdd", "ept20-30", "jxo", "jx0", "es12", "es20", "es10", "es18", "es14",
        "rpl", "wpl", "hpl", "tow", "tractor",
    ]
    for u in pdp:
        slug = u.rstrip("/").split("/")[-1].lower()
        if any(t in slug for t in tokens):
            if u not in candidates:
                candidates.append(u)

    print("\n=== URL CHECKS ===")
    checks = {}
    for u in candidates:
        info = check_url(u)
        checks[u] = info
        st = info.get("status")
        title = info.get("title") or info.get("error") or ""
        print(f"{st} {u}")
        if title:
            print(f"   {title}")

    Path("staging/reports/_ep1274_resolve.json").write_text(
        json.dumps({"serper": serper_out, "checks": checks, "slugs": [u.rstrip('/').split('/')[-1] for u in pdp]}, indent=2),
        encoding="utf-8",
    )
    print("\nWrote _ep1274_resolve.json")


if __name__ == "__main__":
    main()
