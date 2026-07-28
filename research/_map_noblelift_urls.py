"""Build Noblelift model → ASPX URL map from list pages + sample heroes."""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
LISTS = [
    "https://www.noblelift.com/AGV/list.aspx?lcid=51",
    "https://www.noblelift.com/AGV/list.aspx?lcid=55",
    "https://www.noblelift.com/AGV/list.aspx?lcid=56",
    "https://www.noblelift.com/wlbysb/list.aspx?lcid=47",
    "https://www.noblelift.com/wlbysb/list.aspx?lcid=48",
    "https://www.noblelift.com/wlbysb/list.aspx?lcid=49",
    "https://www.noblelift.com/wlbysb/list.aspx?lcid=50",
    "https://www.noblelift.com/wlbysb/list.aspx?lcid=45",
    "https://www.noblelift.com/wlbysb/list.aspx?lcid=46",
    "https://www.noblelift.com/wlbysb/list.aspx?lcid=43",
    "https://www.noblelift.com/wlbysb/list.aspx?lcid=44",
    "https://www.noblelift.com/wlbysb/list.aspx?lcid=63",
]


def main() -> None:
    mapping = {}
    for list_url in LISTS:
        html = requests.get(list_url, headers=HEADERS, timeout=45).text
        # links to info.aspx
        for href, title in re.findall(r'href=["\']([^"\']*info\.aspx\?[^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            text = re.sub(r"<[^>]+>", " ", unescape(title)).strip()
            text = re.sub(r"\s+", " ", text)
            if not text or len(text) > 80:
                continue
            full = urljoin(list_url, href)
            mapping.setdefault(text, full)
        # also tit in cards
        for block in re.findall(r'href=["\']([^"\']*info\.aspx\?[^"\']+)["\'][\s\S]{0,400}?class="tit"[^>]*>(.*?)</', html, re.I):
            href, tit = block
            text = re.sub(r"<[^>]+>", " ", unescape(tit)).strip()
            mapping.setdefault(text, urljoin(list_url, href))
        print(list_url, "mapping size", len(mapping))

    path = Path("staging/reports/noblelift-url-map.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", path, "n=", len(mapping))
    for k, v in list(mapping.items())[:30]:
        print(f"  {k} -> {v}")


if __name__ == "__main__":
    main()
