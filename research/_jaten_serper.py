"""Serper search for each Jaten model; write JSON (no console Unicode)."""
from __future__ import annotations

import json
from pathlib import Path

from load_env import load_research_env

load_research_env()
from product_url_search import _serper_google_search

MODELS = [
    "R2SDM1500-335-MG0",
    "SDM300-335-MG0",
    "SDM100-335-MG0",
    "MN100-164",
    "MN30-164",
    "AGV-31-MC500",
    "SDM2000-D228",
    "SDM300-339-MGD",
    "SDM1000-335-MG0",
    "SDM500-335-MG0",
    "SDM200-335-MG0",
    "SDM500-D228",
    "SDM1000-D228",
    "SDM3000-D228",
]

out: dict = {}
for m in MODELS:
    results = _serper_google_search(f"site:jaten-robotics.com {m}", max_results=8)
    # also try without site restrict
    results2 = _serper_google_search(f'Jaten "{m}" AGV', max_results=5)
    items = []
    for r in results + results2:
        link = r.get("link") or ""
        title = r.get("title") or ""
        snippet = r.get("snippet") or ""
        items.append({"link": link, "title": title, "snippet": snippet})
    # dedupe by link
    seen = set()
    deduped = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        deduped.append(it)
    out[m] = deduped
    print(f"{m}: {len(deduped)} results", flush=True)
    for it in deduped[:4]:
        print(f"  {it['link']}", flush=True)

path = Path("staging/reports/jaten-serper.json")
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {path}", flush=True)
