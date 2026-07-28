"""Scrape KUKA family pages -> per-variant OEM spec table.

KUKA product family pages (kuka.com/.../industrial-robots/<family>) render a
products table SERVER-SIDE in plain HTML — no JS/stealth needed. Each variant is a
`js-item list__item` block carrying:

  data-name           e.g. "KR 120 R2700-2"
  data-load-capacity  e.g. "120 kg"      (KUKA labels it "Total load" — NOT "Payload",
                                          which is why naive keyword scrapes found nothing
                                          and left 73/103 robots with <40-char features)
  data-reach          e.g. "2701 mm"
  data-application    e.g. "Standard"    ("Version environment")
plus a detail list: Construction type / Mounting positions / Protection class / Controller.

Writes staging/reports/kuka-recon.json  { "<variant name>": {...specs..., family, url} }

Usage:
  python kuka_recon.py                 # scrape all families found in the DB
  python kuka_recon.py --only kr-quantec kr-agilus
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from web_extract import WebFetcher

COMPANY_ID = 1396
OUT = _RESEARCH_DIR / "staging" / "reports" / "kuka-recon.json"

_ITEM_RE = re.compile(r'<div class="js-item list__item"[^>]*>(.*?)(?=<div class="js-item list__item"|</div>\s*</div>\s*</div>\s*$)', re.S)


def _clean(s: str) -> str:
    s = htmllib.unescape(htmllib.unescape(s or ""))
    s = s.replace("\xa0", " ")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_family(html: str, family: str, url: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    # Split on each variant block by its data-name anchor, then take a window.
    anchors = [m.start() for m in re.finditer(r'<div class="js-item list__item"', html)]
    anchors.append(len(html))
    for i in range(len(anchors) - 1):
        block = html[anchors[i]: anchors[i + 1]]
        m = re.search(r'data-name="([^"]+)"', block)
        if not m:
            continue
        name = _clean(m.group(1))
        rec: dict[str, Any] = {"family": family, "url": url}
        for attr, key in (("data-load-capacity", "total_load"),
                          ("data-reach", "max_reach"),
                          ("data-application", "version_environment")):
            a = re.search(attr + r'="([^"]*)"', block)
            if a:
                v = _clean(a.group(1))
                if v:
                    rec[key] = v
        # detail list: <strong>Label</strong><span>Value</span>
        for lm in re.finditer(r"<strong>([^<]{2,40})</strong>\s*<span>(.*?)</span>", block, re.S):
            label = _clean(lm.group(1))
            val = _clean(lm.group(2))
            if not val or "Download" in label:
                continue
            key = label.lower().replace(" ", "_")
            rec.setdefault(key, val[:120])
        # controller links
        ctrl = re.findall(r'robot-controllers/[^"]*"[^>]*>\s*<span[^>]*></span>\s*<span>([^<]+)</span>', block)
        if ctrl:
            rec["controller"] = ", ".join(dict.fromkeys(_clean(c) for c in ctrl))[:80]
        if name:
            out[name] = rec
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape KUKA family spec tables")
    ap.add_argument("--only", nargs="*", help="family slugs to limit to")
    args = ap.parse_args()

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
    if args.only:
        urls = [u for u in urls if any(o in u for o in args.only)]
    print(f"family pages to scrape: {len(urls)}")

    f = WebFetcher(stealth=False)
    catalog: dict[str, dict[str, Any]] = {}
    for u in urls:
        family = u.rstrip("/").split("/")[-1]
        html = f.get(u)
        if not html:
            print(f"  FAIL {family}", file=sys.stderr); continue
        got = parse_family(html, family, u)
        for k, v in got.items():
            catalog.setdefault(k, v)
        print(f"  {family:<38} variants={len(got)}")
        time.sleep(0.3)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\ntotal variants: {len(catalog)} -> {OUT}")

    # coverage vs DB names
    names = [r["name"] for r in robots if str(r.get("status") or "").lower() == "pending_review"]
    hit = [n for n in names if n in catalog]
    print(f"DB pending: {len(names)} | exact-name matches in catalog: {len(hit)}")
    miss = [n for n in names if n not in catalog]
    print(f"unmatched ({len(miss)}):")
    for n in miss[:30]:
        print("   ", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
