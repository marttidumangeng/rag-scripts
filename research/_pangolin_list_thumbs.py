"""Extract product-card name+thumb from Pangolin category list pages."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SESS = requests.Session()
SESS.headers["User-Agent"] = "Mozilla/5.0"
SESS.verify = False
BASE = "https://www.alpha-robot.com.cn"
SHARED = "eee172ad753e9d623e64b52a8053981a"
OUT = _RESEARCH_DIR / "staging" / "reports" / "pangolin-list-thumbs.json"
IMG_DIR = _RESEARCH_DIR / "staging" / "pangolin_list_thumbs"
IMG_DIR.mkdir(parents=True, exist_ok=True)

# Category list pages (from catalog crawl)
LISTS = [
    f"{BASE}/product/138.html",  # indoor/outdoor delivery
    f"{BASE}/product/103.html",  # welcome/reception
    f"{BASE}/product/145.html",  # medical
    f"{BASE}/product/102.html",  # food delivery
    f"{BASE}/product/133.html",  # hotel delivery
    f"{BASE}/product/141.html",  # factory handling
    f"{BASE}/product/142.html",  # security patrol
    f"{BASE}/product/139.html",  # unmanned retail
    f"{BASE}/product/146.html",  # humanoid
    f"{BASE}/product/1.html",  # all products?
]


def fetch(url: str) -> str:
    r = SESS.get(url, timeout=45)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def main() -> None:
    products: dict[str, dict] = {}
    for list_url in LISTS:
        try:
            html = fetch(list_url)
        except Exception as e:
            print(f"FAIL {list_url}: {e}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        list_title = soup.title.get_text(strip=True) if soup.title else ""
        print(f"\n=== {list_title} | {list_url}")

        # Find all detail links
        for a in soup.find_all("a", href=True):
            href = urljoin(list_url, a["href"]).split("#")[0].split("?")[0]
            if "/detail/" not in href:
                continue
            if "alpha-robot.com.cn" not in href:
                continue
            # skip news/cases
            if any(x in href for x in ("/article/", "/cases/", "/about/", "/agent/")):
                continue

            text = a.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)[:100]

            # find best nearby image
            img = a.find("img")
            parent = a
            for _ in range(4):
                if img:
                    break
                parent = parent.parent
                if parent is None:
                    break
                img = parent.find("img")

            src = ""
            if img:
                src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
                if src:
                    src = urljoin(list_url, src).split("?")[0]

            entry = products.setdefault(
                href,
                {
                    "url": href,
                    "names": [],
                    "thumbs": [],
                    "lists": [],
                },
            )
            if text and text not in entry["names"] and len(text) >= 2:
                entry["names"].append(text)
            if src and SHARED not in src and src not in entry["thumbs"]:
                if any(src.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")):
                    entry["thumbs"].append(src)
            if list_url not in entry["lists"]:
                entry["lists"].append(list_url)

        # Also parse structured cards: look for product blocks with img+title
        # Dump first product-looking structure sample
        cards = soup.select(".product-item, .pro-item, .list-item, li, .swiper-slide")
        print(f"  detail_links_so_far={sum(1 for u in products if list_url in products[u]['lists'])} cards_sel={len(cards)}")

    # Download thumbs and hash
    hash_owners: dict[str, list] = {}
    for href, entry in products.items():
        entry["thumb_meta"] = []
        for src in entry["thumbs"][:3]:
            try:
                data = SESS.get(src, timeout=45).content
            except Exception as e:
                entry["thumb_meta"].append({"url": src, "error": str(e)})
                continue
            if len(data) < 5000:
                continue
            md5 = hashlib.md5(data).hexdigest()
            fname = f"{md5[:12]}_{Path(src).name}"
            (IMG_DIR / fname).write_bytes(data)
            meta = {"url": src, "md5": md5, "bytes": len(data), "file": fname}
            entry["thumb_meta"].append(meta)
            hash_owners.setdefault(md5, []).append(href)

    # Mark uniqueness
    for entry in products.values():
        for m in entry.get("thumb_meta") or []:
            if "md5" in m:
                m["n_products"] = len(set(hash_owners.get(m["md5"], [])))

    OUT.write_text(
        json.dumps(
            {
                "products": list(products.values()),
                "shared_thumb_hashes": {
                    h: urls for h, urls in hash_owners.items() if len(set(urls)) > 1
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nwrote {OUT} products={len(products)}")
    unique = 0
    for p in sorted(products.values(), key=lambda x: x["url"]):
        names = p["names"][:2]
        metas = p.get("thumb_meta") or []
        uniq = [m for m in metas if m.get("n_products") == 1]
        if uniq:
            unique += 1
        print(
            f"  {'U' if uniq else 'S' if metas else '-'} "
            f"{(names[0] if names else '?')[:28]:28s} "
            f"thumbs={len(metas)} uniq={len(uniq)} {p['url'][-55:]}"
        )
    print(f"products_with_unique_thumb={unique}")


if __name__ == "__main__":
    main()
