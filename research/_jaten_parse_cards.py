"""Parse all AGV cards from Jaten list page SSR HTML."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
LIST = "https://jaten-robotics.com/index/Agv/index.html"
BASE = "https://jaten-robotics.com"
OUT = Path("staging/reports/jaten-url-map.json")

html = requests.get(LIST, headers=HEADERS, timeout=60).text
print("html len", len(html), flush=True)

# Each product card
card_re = re.compile(
    r"<div class=\"card\" onclick=\"onDetail\('(\d+)'\);\">(.*?)</div>\s*</div>\s*</div>\s*</div>",
    re.S,
)
# Simpler: find all onDetail + following cardTitle + cardImg
pairs = []
for m in re.finditer(r"onDetail\('(\d+)'\);", html):
    pid = m.group(1)
    block = html[m.start() : m.start() + 2500]
    title_m = re.search(r'<div class="cardTitle">([^<]+)</div>', block)
    img_m = re.search(r'<img class="cardImg" src="([^"]+)"', block)
    # also extract key-value specs from cardValueItem
    specs = {}
    for sm in re.finditer(
        r'<span class="itemTitle"\s*>([^<]+)</span>\s*<span>([^<]*)</span>',
        block,
    ):
        specs[sm.group(1).strip()] = re.sub(r"&amp;", "&", sm.group(2)).strip()
    # rated load sometimes differently
    load_m = re.search(r"(?:额定负载|Specific Load)\s*</span>\s*<span>([^<]+)</span>", block)
    if load_m:
        specs["Specific Load"] = load_m.group(1).strip()
    load_m2 = re.search(r"额定负载</[^>]+>\s*<[^>]+>([^<]+)", block)
    # Chinese load after authLine pattern
    rated = re.search(r"额定负载[^0-9A-Z]*([0-9]+\s*KG)", block, re.I)
    if rated:
        specs["Rated Load"] = rated.group(1)

    title = (title_m.group(1).strip() if title_m else "")
    img = urljoin(BASE, img_m.group(1)) if img_m else ""
    url = f"{BASE}/index/Agv/detail.html?id={pid}"
    entry = {
        "id": pid,
        "name": title,
        "url": url,
        "hero": img,
        "specs": specs,
    }
    pairs.append(entry)
    print(f"id={pid} name={title!r} hero={bool(img)}", flush=True)

# Deduplicate by id keeping first
by_id = {}
for e in pairs:
    by_id.setdefault(e["id"], e)

# Also index by normalized name
by_name = {}
for e in by_id.values():
    if e["name"]:
        by_name[e["name"].upper()] = e
        # also without ZER suffix variants kept as-is
        by_name[e["name"].split()[0].upper()] = e

OUT.write_text(
    json.dumps({"by_id": by_id, "cards": list(by_id.values())}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"unique={len(by_id)} -> {OUT}", flush=True)

# Check our CRM robots
targets = [
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
print("--- CRM match ---", flush=True)
for t in targets:
    hits = [e for e in by_id.values() if t.upper() in e["name"].upper() or e["name"].upper().startswith(t.upper())]
    # fuzzy: model stem
    if not hits:
        stem = t.split("-")[0]
        hits = [e for e in by_id.values() if stem.upper() in e["name"].upper()]
    print(f"{t}: {[ (h['id'], h['name']) for h in hits[:5] ]}", flush=True)
