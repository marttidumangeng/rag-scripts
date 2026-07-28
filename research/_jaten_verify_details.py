"""Exact-name search in Jaten list HTML + verify candidate detail IDs."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = "https://jaten-robotics.com"
LIST = f"{BASE}/index/Agv/index.html"

TARGETS = [
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

# Candidate detail IDs from CRM + nearby
CANDIDATE_IDS = {
    "R2SDM1500-335-MG0": ["1001025"],
    "SDM300-335-MG0": ["1001022", "1001026"],
    "SDM100-335-MG0": ["1001020"],
    "MN100-164": ["1000004"],
    "MN30-164": ["1000003"],
    "AGV-31-MC500": ["1000002"],
    "SDM2000-D228": ["1000005", "1000263"],
    "SDM300-339-MGD": ["1001026"],
    "SDM1000-335-MG0": ["1001024"],
    "SDM500-335-MG0": ["1001023"],
    "SDM200-335-MG0": ["1001021"],
    "SDM500-D228": ["1000001"],
    "SDM1000-D228": ["1000000", "1000019"],
    "SDM3000-D228": ["1000006"],
}

html = requests.get(LIST, headers=HEADERS, timeout=60).text
# Exact substring presence
print("=== exact in list HTML ===", flush=True)
for t in TARGETS:
    print(f"  {t}: {html.count(t)}", flush=True)

# Fetch detail pages and extract English product title from body
OUT = {}
session = requests.Session()
session.headers.update(HEADERS)

for name, ids in CANDIDATE_IDS.items():
    OUT[name] = []
    for pid in ids:
        url = f"{BASE}/index/Agv/detail.html?id={pid}"
        # try EN cookie / lang
        for lang_url in [url, url + "&lang=en", f"{BASE}/agv/detail/?id={pid}"]:
            try:
                r = session.get(lang_url, timeout=40)
            except Exception as e:
                OUT[name].append({"id": pid, "fetch": lang_url, "error": str(e)})
                continue
            text = r.text
            # Prefer cardTitle-like / h1 / first model token in body
            soup = BeautifulSoup(text, "html.parser")
            # remove scripts
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            body = soup.get_text(" ", strip=True)
            # model named in page?
            named = name in body or name.split("-")[0] in body[:500]
            # Find first AGV-like model token after EN marker
            m = re.search(
                r"\b((?:R2)?SDM[\w\-]+|MN[\d\-]+|AGV[\w\-]+|LN[\w\-]+|IN[\w\-]+|MD[\w\-]+|SLAM[\w\-]+|DM[\w\-]+)\b",
                body,
            )
            title = m.group(1) if m else ""
            # hero upload image
            imgs = [
                BASE + u if u.startswith("/") else u
                for u in re.findall(r'(?:src)=["\']([^"\']*/upload/[^"\']+\.(?:png|jpe?g|webp))["\']', text, re.I)
            ]
            imgs = [u for u in imgs if "1df52100" not in u]  # shared footer junk
            # Specs extraction
            specs = {}
            for label in [
                "Navigation", "Delivery Mode", "Speed", "Climbing Ability",
                "Dimension", "Turning Radius", "Battery", "Charging Mode",
                "Lifting Height", "Running Direction", "Specific Load", "行走方向", "额定负载",
            ]:
                mm = re.search(re.escape(label) + r"\s+([^\n]{0,80}?)(?=\s+(?:Navigation|Delivery|Speed|Climbing|Dimension|Turning|Battery|Charging|Lifting|Running|Specific|行走|额定|Consultation|Parameters|Product|$))", body)
                if mm:
                    specs[label] = mm.group(1).strip()[:80]
            entry = {
                "id": pid,
                "fetch": lang_url,
                "status": r.status_code,
                "title_guess": title,
                "name_in_page": name in body,
                "hero": imgs[0] if imgs else "",
                "images": imgs[:4],
                "specs": specs,
                "body_snip": body[body.find(title): body.find(title) + 400] if title else body[:300],
            }
            OUT[name].append(entry)
            print(f"{name} id={pid} title={title!r} match={name in body} hero={bool(imgs)}", flush=True)
            break  # one URL enough per id

path = Path("staging/reports/jaten-detail-verify.json")
path.write_text(json.dumps(OUT, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {path}", flush=True)
