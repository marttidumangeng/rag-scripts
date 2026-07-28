#!/usr/bin/env python3
"""Inspect Niumowang / factory list cards vs robot 2195 hero."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SESS = requests.Session()
SESS.verify = False
SESS.headers["User-Agent"] = "Mozilla/5.0"
BASE = "https://www.alpha-robot.com.cn"
OUT = Path("staging/pangolin_pdp_extra/_visual")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    # factory handling list + niumowang PDP
    pages = [
        f"{BASE}/product/141.html",
        f"{BASE}/productnmw/141/detail/15.html",
    ]
    report = []
    for page in pages:
        html = SESS.get(page, timeout=45).text
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        print("===", title, page)
        cards = []
        for a in soup.find_all("a", href=True):
            href = urljoin(page, a["href"]).split("?")[0]
            if "/detail/" not in href:
                continue
            text = " ".join(a.get_text(" ", strip=True).split())[:80]
            img = a.find("img")
            parent = a
            for _ in range(4):
                if img:
                    break
                parent = parent.parent if parent else None
                if parent is None:
                    break
                img = parent.find("img")
            src = ""
            if img:
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    src = urljoin(page, src).split("?")[0]
            if not src or "eee172ad" in src:
                continue
            try:
                data = SESS.get(src, timeout=30).content
            except Exception:
                continue
            md5 = hashlib.md5(data).hexdigest()
            fname = OUT / f"nmw_{md5[:12]}.png"
            if not fname.exists():
                fname.write_bytes(data)
            entry = {
                "text": text,
                "href": href,
                "src": src,
                "md5": md5,
                "bytes": len(data),
                "file": str(fname.name),
            }
            cards.append(entry)
            print(f"  {md5[:12]} {len(data):6d} {text[:40]!r} {src.rsplit('/',1)[-1]}")
        report.append({"page": page, "title": title, "cards": cards})

    Path("staging/reports/_pangolin_nmw_cards.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
