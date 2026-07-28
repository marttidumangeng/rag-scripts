"""Inspect Jaten AGV list HTML structure and search for model names."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
LIST = "https://jaten-robotics.com/index/Agv/index.html"
html = requests.get(LIST, headers=HEADERS, timeout=60).text

# Save sample snippet containing known model
models = [
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

out = []
for name in models:
    idxs = [m.start() for m in re.finditer(re.escape(name), html)]
    print(f"{name}: {len(idxs)} hits")
    if not idxs:
        # try partial
        parts = name.split("-")[0]
        idxs2 = [m.start() for m in re.finditer(re.escape(parts), html)]
        print(f"  partial {parts}: {len(idxs2)} hits")
        continue
    i = idxs[0]
    block = html[max(0, i - 800) : i + 800]
    # find any id= nearby
    ids = re.findall(r"id[=:]?\s*['\"]?(\d{5,})", block)
    imgs = re.findall(r'(?:src|url|background)[=:(]?[\"\']?([^\"\'\s>]*/upload/[^\"\'\s>]+)', block, re.I)
    out.append({"name": name, "ids": ids[:10], "imgs": imgs[:5], "block": block})

Path("staging/reports/jaten-list-blocks.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("wrote blocks", len(out))

# Also look for JSON API endpoints embedded
apis = set(re.findall(r'["\'](/[^"\']*(?:agv|product|list|api)[^"\']*)["\']', html, re.I))
print("possible api paths sample:")
for a in sorted(apis)[:40]:
    print(" ", a)

# Look for ajax urls
ajax = set(re.findall(r'url\s*:\s*[\'\"]([^\'\"]+)[\'\"]', html))
print("ajax urls:")
for a in sorted(ajax)[:40]:
    print(" ", a)
