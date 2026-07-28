"""Map alpha-robot product list pages → model name + thumbnail."""
from __future__ import annotations

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
OUT = _RESEARCH_DIR / "staging" / "reports" / "pangolin-catalog.json"

# Common category / product-index URLs observed in robot records
SEED = [
    f"{BASE}/",
    f"{BASE}/product.html",
    f"{BASE}/product/",
    f"{BASE}/productxy/",
    f"{BASE}/productamjj/",
    f"{BASE}/productspeedybot/",
    f"{BASE}/productxm/",
    f"{BASE}/productrwx/",
    f"{BASE}/productalsjj/",
    f"{BASE}/producthmjz/",
    f"{BASE}/productjl/",
    f"{BASE}/product/138.html",
]


def fetch(url: str) -> str:
    r = SESS.get(url, timeout=45)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def main() -> None:
    found_links: dict[str, dict] = {}
    visited = set()
    queue = list(SEED)

    # also seed from recon URLs' parent paths
    recon = json.loads(
        (_RESEARCH_DIR / "staging" / "reports" / "pangolin-recon.json").read_text(
            encoding="utf-8"
        )
    )
    for row in recon.values():
        u = (row.get("url") or "").strip()
        if not u:
            continue
        # parent category
        m = re.match(r"(https://www\.alpha-robot\.com\.cn/[^/]+/)", u)
        if m:
            queue.append(m.group(1))
        m2 = re.match(r"(https://www\.alpha-robot\.com\.cn/[^/]+/\d+/)", u)
        if m2:
            queue.append(m2.group(1))

    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            html = fetch(url)
        except Exception as e:
            print(f"FAIL {url}: {e}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.get_text(strip=True) if soup.title else "")[:60]
        print(f"OK {url} title={title!r}")

        # product cards: links containing /detail/
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"]).split("?")[0]
            if "alpha-robot.com.cn" not in href:
                continue
            if "/detail/" in href or re.search(r"/product[^/]*/\d+/detail/\d+", href):
                text = a.get_text(" ", strip=True)
                img = a.find("img")
                src = ""
                if img:
                    src = img.get("src") or img.get("data-src") or ""
                    if src:
                        src = urljoin(url, src).split("?")[0]
                # nearby img sibling
                if not src:
                    prev = a.find_previous("img")
                    if prev:
                        src = prev.get("src") or prev.get("data-src") or ""
                        if src:
                            src = urljoin(url, src).split("?")[0]
                entry = found_links.setdefault(
                    href,
                    {"url": href, "texts": [], "thumbs": [], "seen_on": []},
                )
                if text and text not in entry["texts"] and len(text) < 80:
                    entry["texts"].append(text)
                if src and src not in entry["thumbs"] and "eee172ad" not in src:
                    entry["thumbs"].append(src)
                if url not in entry["seen_on"]:
                    entry["seen_on"].append(url)

            # enqueue more category pages
            if href.endswith(".html") and "/detail/" not in href:
                if any(x in href for x in ("/product", "chanpin", "robot")):
                    if href not in visited and len(visited) < 80:
                        queue.append(href)

    OUT.write_text(
        json.dumps(
            {"visited": sorted(visited), "products": list(found_links.values())},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUT} products={len(found_links)} pages={len(visited)}")
    for p in sorted(found_links.values(), key=lambda x: x["url"])[:30]:
        print(
            f"  {p['url'][-50:]:50s} texts={p['texts'][:2]!r} thumbs={len(p['thumbs'])}"
        )


if __name__ == "__main__":
    main()
