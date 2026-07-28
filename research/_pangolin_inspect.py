"""Inspect Pangolin PDP HTML + existing CDN hero uniqueness."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

SESS = requests.Session()
SESS.headers["User-Agent"] = "Mozilla/5.0"
SESS.verify = False

OUT = _RESEARCH_DIR / "staging" / "pangolin_heroes"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    recon = json.loads(
        (_RESEARCH_DIR / "staging" / "reports" / "pangolin-recon.json").read_text(encoding="utf-8")
    )
    # unique URLs
    urls = Counter()
    titles = Counter()
    hero0 = Counter()
    for v in recon.values():
        urls[(v.get("url") or "")[:90]] += 1
        pdp = v.get("pdp") or {}
        titles[(pdp.get("title") or "")[:50]] += 1
        hs = pdp.get("heroes") or []
        if hs:
            hero0[hs[0]] += 1
    print("top URLs:")
    for u, n in urls.most_common(15):
        print(f"  {n}x {u}")
    print("top titles:")
    for t, n in titles.most_common(15):
        print(f"  {n}x {t}")
    print("top hero0:")
    for h, n in hero0.most_common(5):
        print(f"  {n}x {h}")

    # fetch one "good" detail page and dump img candidates
    sample_url = "https://www.alpha-robot.com.cn/productalsjj/3/detail/6.html"
    r = SESS.get(sample_url, timeout=45)
    r.encoding = r.apparent_encoding or "utf-8"
    html = r.text
    print(f"\nSAMPLE {sample_url} status={r.status_code} len={len(html)}")
    imgs = re.findall(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', html, re.I)
    for u in list(dict.fromkeys(imgs))[:40]:
        print(" IMG", u[:120])

    # hash existing CDN heroes for robots with images
    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(1413)
        if str(r.get("status") or "").lower() == "pending_review"
    ]
    hashes: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in robots:
        full = client._get(f"robots/robots/{int(r['id'])}/")
        img = (full.get("image") or full.get("s3_image") or "").strip()
        if not img:
            continue
        data = requests.get(img, timeout=60).content
        h = hashlib.md5(data).hexdigest()
        hashes[h].append((int(full["id"]), (full.get("name") or "")[:40]))
        path = OUT / f"keep_{full['id']}.bin"
        path.write_bytes(data)
        print(f"KEEP {full['id']} bytes={len(data)} md5={h} {(full.get('name') or '')[:40]!r}")
    print("\nshared keep hashes:")
    for h, owners in hashes.items():
        if len(owners) > 1:
            print(f"  {h[:12]} -> {owners}")


if __name__ == "__main__":
    main()
