"""Map live EP Equipment product catalog URLs."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

MODELS = [
    "QDD30T", "QDD30TS", "EPT20-30TW", "JXO", "ES12-25WA", "ES20-WA",
    "ES12-12ES", "ES12-25MM", "ES10-10ES", "ES10-22MM", "ES18-40WA",
    "ES14-30WA", "RPL251", "RPL301", "WPL201", "HPL152", "EPT20-RAP",
    "ES15-15ES", "ESL122", "EPT25-WA", "EPT20-20WA", "KPL201", "EPL185",
    "EPL154",
]


def fetch(url: str) -> str:
    r = requests.get(url, timeout=60, headers=HEADERS, allow_redirects=True)
    print(f"{r.status_code} {len(r.text)} {r.url}")
    r.raise_for_status()
    return r.text


def extract_product_links(html: str, base: str) -> list[dict]:
    links = []
    seen = set()
    # href="/product/.../" or full URL
    for m in re.finditer(r'href=["\']([^"\']*(?:/product/|/products/)[^"\']+)["\']', html, re.I):
        href = m.group(1)
        full = urljoin(base, href.split("#")[0])
        if full in seen:
            continue
        seen.add(full)
        # grab nearby text for title
        start = max(0, m.start() - 200)
        end = min(len(html), m.end() + 300)
        ctx = re.sub(r"<[^>]+>", " ", html[start:end])
        ctx = re.sub(r"\s+", " ", ctx).strip()[:200]
        links.append({"url": full, "ctx": ctx})
    return links


def main() -> None:
    pages = [
        "https://ep-equipment.com/products/",
        "https://ep-equipment.com/product/",
    ]
    all_links = []
    seen = set()
    for page in pages:
        html = fetch(page)
        for item in extract_product_links(html, page):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            all_links.append(item)

    # Also try category pages from homepage nav
    home = fetch("https://ep-equipment.com/")
    cat_urls = set()
    for m in re.finditer(r'href=["\'](https?://ep-equipment\.com/[^"\']+)["\']', home, re.I):
        u = m.group(1).rstrip("/") + "/"
        low = u.lower()
        if any(x in low for x in ("pallet", "stacker", "forklift", "reach", "order", "tow", "agv", "amr", "lithium", "warehouse", "truck")):
            cat_urls.add(u)
    # Also relative
    for m in re.finditer(r'href=["\'](/[^"\']+)["\']', home, re.I):
        u = urljoin("https://ep-equipment.com/", m.group(1))
        low = u.lower()
        if any(x in low for x in ("pallet", "stacker", "forklift", "reach", "order", "tow", "agv", "amr", "lithium")):
            cat_urls.add(u.rstrip("/") + "/")

    print(f"\nCategory candidates: {len(cat_urls)}")
    for u in sorted(cat_urls)[:40]:
        print(" ", u)

    for u in sorted(cat_urls):
        try:
            html = fetch(u)
            for item in extract_product_links(html, u):
                if item["url"] in seen:
                    continue
                seen.add(item["url"])
                all_links.append(item)
        except Exception as e:
            print("skip", u, e)

    # Match models
    print("\n=== MODEL MATCH ===")
    matches = {}
    for model in MODELS:
        token = model.lower().replace("/", "-")
        hits = []
        for item in all_links:
            low = (item["url"] + " " + item["ctx"]).lower()
            if token in low or model.lower() in low:
                hits.append(item["url"])
        # also try without dashes
        compact = re.sub(r"[^a-z0-9]", "", model.lower())
        for item in all_links:
            path = item["url"].lower()
            path_compact = re.sub(r"[^a-z0-9]", "", path)
            if compact in path_compact and item["url"] not in hits:
                hits.append(item["url"])
        matches[model] = hits
        print(f"{model}: {hits[:3] if hits else 'NONE'}")

    out = {
        "all_product_urls": [x["url"] for x in all_links],
        "all_with_ctx": all_links,
        "matches": matches,
        "categories": sorted(cat_urls),
    }
    Path("staging/reports/_ep1274_url_map.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    print(f"\nTotal unique product-ish URLs: {len(all_links)}")
    print("Wrote staging/reports/_ep1274_url_map.json")


if __name__ == "__main__":
    main()
