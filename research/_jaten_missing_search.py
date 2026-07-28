"""Search jtrobots.com and Wayback for missing Jaten models."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from load_env import load_research_env

load_research_env()
from product_url_search import _serper_google_search

HEADERS = {"User-Agent": "Mozilla/5.0"}
MISSING = [
    "SDM300-335-MG0",
    "SDM100-335-MG0",
    "SDM1000-335-MG0",
    "SDM500-335-MG0",
    "SDM200-335-MG0",
    "MN100-164",
    "SDM2000-D228",
    "SDM1000-D228",
    "SDM3000-D228",
]

out = {}
for m in MISSING:
    queries = [
        f'site:jaten-robotics.com "{m}"',
        f'site:jtrobots.com "{m}"',
        f'"{m}" Jaten AGV',
        f'site:web.archive.org jaten "{m}"',
    ]
    items = []
    for q in queries:
        for r in _serper_google_search(q, max_results=5):
            items.append({"q": q, "link": r.get("link"), "title": r.get("title"), "snippet": r.get("snippet")})
    # dedupe
    seen = set()
    ded = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        ded.append(it)
    out[m] = ded
    print(f"{m}: {len(ded)}", flush=True)
    for it in ded[:3]:
        print(f"  {it['link']}", flush=True)

Path("staging/reports/jaten-missing-serper.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)

# Try Chinese detail with same IDs - Accept-Language zh
print("--- zh fetch sample ---", flush=True)
for pid, expect in [("1001022", "SDM300"), ("1001020", "SDM100"), ("1000004", "MN100"), ("1000000", "SDM1000"), ("1000005", "SDM2000"), ("1000006", "SDM3000")]:
    url = f"https://jaten-robotics.com/index/Agv/detail.html?id={pid}"
    r = requests.get(url, headers={**HEADERS, "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=30)
    # find first model-like
    text = re.sub(r"<script[\s\S]*?</script>", " ", r.text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    m = re.search(r"\b((?:R2)?SDM[\w\-]+|MN[\d\-]+|AGV[\w\-]+|LN[\w\-]+|IN[\w\-]+|MD[\w\-]+)\b", text)
    print(f"id={pid} expect~{expect} title={m.group(1) if m else None} has={expect in text}", flush=True)
