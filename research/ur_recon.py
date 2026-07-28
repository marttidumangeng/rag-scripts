"""Scrape Universal Robots product pages → heroes + payload/reach.

Writes staging/reports/ur-recon.json keyed by normalized model (UR3e, UR20, …).

Usage:
  python ur_recon.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from web_extract import WebFetcher

OUT = _RESEARCH_DIR / "staging" / "reports" / "ur-recon.json"

# Canonical product URLs (current UR catalog).
PRODUCTS: dict[str, str] = {
    "UR3e": "https://www.universal-robots.com/products/ur3e/",
    "UR5e": "https://www.universal-robots.com/products/ur5e/",
    "UR7e": "https://www.universal-robots.com/products/ur7e/",
    "UR10e": "https://www.universal-robots.com/products/ur10e/",
    "UR12e": "https://www.universal-robots.com/products/ur12e/",
    "UR16e": "https://www.universal-robots.com/products/ur16e/",
    "UR8": "https://www.universal-robots.com/products/ur8-long/",  # closest public page; refine if /ur8/ exists
    "UR8 Long": "https://www.universal-robots.com/products/ur8-long/",
    "UR15": "https://www.universal-robots.com/products/ur15/",
    "UR18": "https://www.universal-robots.com/products/ur18/",
    "UR20": "https://www.universal-robots.com/products/ur20/",
    "UR30": "https://www.universal-robots.com/products/ur30/",
    "UR3": "https://www.universal-robots.com/products/ur3-robot/",
    "UR5": "https://www.universal-robots.com/products/ur5-robot/",
    "UR10": "https://www.universal-robots.com/products/ur10-robot/",
}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def parse_product(html: str, model: str, url: str) -> dict[str, Any]:
    rec: dict[str, Any] = {"model": model, "url": url}
    title_m = re.search(r"<title>([^<]+)", html, re.I)
    if title_m:
        rec["title"] = _clean(title_m.group(1))

    # Storyblok product renders prefer filename containing model token
    token = re.sub(r"[^a-z0-9]", "", model.lower())
    imgs = re.findall(
        r"https?://a\.storyblok\.com/[^\"'\s>]+\.(?:png|jpg|jpeg|webp)(?:\?[^\"'\s>]*)?",
        html,
        re.I,
    )
    product_imgs: list[str] = []
    other_imgs: list[str] = []
    seen: set[str] = set()
    for u in imgs:
        base = u.split("?", 1)[0]
        if base in seen:
            continue
        seen.add(base)
        low = base.lower()
        if any(x in low for x in ("case", "thumbnail", "deburring", "loreal", "beruf")):
            continue
        if token and token in re.sub(r"[^a-z0-9]", "", low):
            product_imgs.append(base)
        else:
            other_imgs.append(base)
    rec["heroes"] = (product_imgs or other_imgs)[:4]

    # Payload / reach from marketing copy near model
    # Prefer title patterns: "3 kg Payload", "25 kg Payload"
    payload = None
    reach = None
    m = re.search(r"([\d.]+)\s*kg\s+Payload", html, re.I)
    if m:
        payload = float(m.group(1))
    m = re.search(r"Payload[^.]{0,40}?([\d.]+)\s*kg", html, re.I)
    if m and payload is None:
        payload = float(m.group(1))
    m = re.search(r"([\d.]+)\s*mm\s+reach", html, re.I)
    if m:
        reach = float(m.group(1))
    m = re.search(r"reach[^.]{0,40}?([\d.]+)\s*mm", html, re.I)
    if m and reach is None:
        reach = float(m.group(1))
    # compact copy: "3 kg payload and 500 mm reach"
    m = re.search(
        r"([\d.]+)\s*kg\s+payload\s+and\s+([\d.]+)\s*mm\s+reach",
        html,
        re.I,
    )
    if m:
        payload = float(m.group(1))
        reach = float(m.group(2))

    if payload is not None:
        rec["payload_kg"] = payload
    if reach is not None:
        rec["reach_mm"] = reach

    # short description from meta
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        html,
        re.I,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
            html,
            re.I,
        )
    if m:
        rec["meta_description"] = _clean(m.group(1))[:400]

    return rec


def main() -> int:
    f = WebFetcher(stealth=False)
    # probe /ur8/ as well
    for slug in ("ur8",):
        u = f"https://www.universal-robots.com/products/{slug}/"
        html = f.get(u) or ""
        print(f"probe {u} len={len(html)}")
        if html and "ur8" in html.lower() and "not found" not in html.lower()[:500]:
            PRODUCTS["UR8"] = u
        time.sleep(0.2)

    catalog: dict[str, Any] = {}
    for model, url in PRODUCTS.items():
        html = f.get(url) or ""
        if not html:
            print(f"FAIL {model} {url}")
            continue
        rec = parse_product(html, model, url)
        catalog[model] = rec
        print(
            f"  {model:<10} heroes={len(rec.get('heroes') or [])} "
            f"p={rec.get('payload_kg')} r={rec.get('reach_mm')} "
            f"title={(rec.get('title') or '')[:55]}"
        )
        time.sleep(0.35)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} models={len(catalog)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
