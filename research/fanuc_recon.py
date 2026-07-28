"""Scrape FANUC America series pages -> per-series product photo candidates.

fanucamerica.com/products/robots/series/<series> renders over plain HTTP (Craft CMS).
Media lives on cdn.craft.cloud. The pages carry NO per-variant spec table and no studio
renders — what they do carry is real application photography of that series
(`m-710ic-palletizing.jpg`, `m-410ic-gripper-with-boxes.jpg`, ...).

We keep only assets under /assets/images/ whose filename carries the series token, and
drop navigation chrome + case-study art. Everything is downloaded for visual QA before use.

Writes staging/reports/fanuc-recon.json  { series: [ {url, file}, ... ] }

Usage:
  python fanuc_recon.py
"""

from __future__ import annotations

import html as htmllib
import json
import os
import re
import sys
import time
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

import requests

from api_client import ResearchApiClient
from web_extract import WebFetcher

COMPANY_ID = 189
BASE = "https://www.fanucamerica.com"
OUT = _RESEARCH_DIR / "staging" / "reports" / "fanuc-recon.json"
IMGDIR = _RESEARCH_DIR / "staging" / "_fanuc_r"

# Chrome / non-product art seen on these pages.
REJECT = ("navigation/", "/case-studies/", "logo", "icon", "sprite", "favicon",
          "cnc-controls", "robodrill", "roboshot", "robocut", "placeholder")


def series_token(slug: str) -> str:
    """'m-710' -> 'm-710', 'lr-mate' -> 'lr-mate' (used to match the filename)."""
    return slug.lower()


def main() -> int:
    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID); break
        except Exception as e:
            print(f"list retry {a}: {str(e)[:60]}", file=sys.stderr); time.sleep(5)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr); return 1

    urls = sorted({(r.get("url") or "").strip() for r in robots if (r.get("url") or "").strip()})
    print(f"series pages: {len(urls)}")

    f = WebFetcher(stealth=False)
    S = requests.Session()
    S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    IMGDIR.mkdir(parents=True, exist_ok=True)

    out: dict[str, list[dict[str, str]]] = {}
    for u in urls:
        slug = u.rstrip("/").split("/")[-1]
        html = f.get(u)
        if not html:
            print(f"  FAIL {slug}", file=sys.stderr); continue
        tok = series_token(slug)
        cands = []
        for m in re.finditer(r'(?:src|data-src)="(https://cdn\.craft\.cloud/[^"]+\.(?:png|jpg|jpeg|webp)[^"]*)"', html, re.I):
            img = htmllib.unescape(m.group(1))
            low = img.lower()
            if any(k in low for k in REJECT):
                continue
            if "/assets/images/" not in low:
                continue
            # keep only assets whose filename mentions this series
            fname = low.split("/")[-1].split("?")[0]
            if tok.replace("-", "") not in fname.replace("-", "").replace("_", ""):
                continue
            base = img.split("?")[0]
            if any(c["url"].split("?")[0] == base for c in cands):
                continue
            cands.append({"url": img})
        out[slug] = cands
        print(f"  {slug:<16} candidates={len(cands)}")
        for i, c in enumerate(cands[:8]):
            try:
                r = S.get(c["url"], timeout=40)
                if r.ok and r.headers.get("Content-Type", "").startswith("image") and len(r.content) > 8000:
                    p = IMGDIR / f"{slug}_{i}.png"
                    p.write_bytes(r.content)
                    c["file"] = str(p)
                    print(f"      OK {len(r.content):>7}B {c['url'].split('/')[-1][:60]}")
            except Exception as e:
                print("      ERR", str(e)[:40])
        time.sleep(0.3)

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tot = sum(len(v) for v in out.values())
    print(f"\nseries with candidates: {sum(1 for v in out.values() if v)} / {len(out)}; total imgs {tot}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
