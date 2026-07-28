"""Fetch Jaten AGV list pages by type and extract product cards."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://jaten-robotics.com"
OUT = Path("staging/reports/jaten-list-by-type.json")

# Try both HTML paths and pretty URLs
urls = []
for t in [None, 1, 2, 3, 5, 10, 12]:
    if t is None:
        urls.append(f"{BASE}/index/Agv/index.html")
        urls.append(f"{BASE}/agv/index")
    else:
        urls.append(f"{BASE}/index/Agv/index.html?type={t}")
        urls.append(f"{BASE}/agv/index/?type={t}")

all_products = {}
page_meta = []

for url in urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        html = r.text
    except Exception as e:
        page_meta.append({"url": url, "error": str(e)})
        continue
    # Extract detail ids and nearby model-like tokens
    # Look for patterns like data attributes or JSON in script
    detail_ids = sorted(set(re.findall(r"(?:Agv/detail\.html\?id=|/agv/detail/\?id=)(\d+)", html, re.I)))
    # Model-ish tokens near upload images
    products = []
    # Split by detail links
    for m in re.finditer(
        r'(?:href|data-url|data-href)=["\']([^"\']*(?:Agv/detail|/agv/detail)[^"\']*id=(\d+)[^"\']*)["\']',
        html,
        re.I,
    ):
        pid = m.group(2)
        href = urljoin(url, m.group(1))
        start = max(0, m.start() - 2000)
        end = min(len(html), m.end() + 2000)
        block = html[start:end]
        name_m = re.search(
            r"\b((?:R2)?SDM[\w\-]+|MN[\d\-]+|AGV[\w\-]+|LN[\w\-]+|IN[\w\-]+|MD[\w\-]+)\b",
            block,
            re.I,
        )
        imgs = [
            urljoin(url, u)
            for u in re.findall(r'(?:src|data-src)=["\']([^"\']*/upload/[^"\']+)["\']', block, re.I)
        ]
        # filter tiny UI
        imgs = [u for u in imgs if not any(x in u.lower() for x in ("logo", "icon", "pdf", "kf.", "wx"))]
        entry = {
            "id": pid,
            "url": href,
            "name": name_m.group(1) if name_m else "",
            "hero": imgs[0] if imgs else "",
            "images": imgs[:4],
        }
        products.append(entry)
        key = f"{pid}|{entry['name']}"
        if key not in all_products or (not all_products[key].get("hero") and entry["hero"]):
            all_products[key] = entry

    # Also scan for inline JSON arrays
    json_blobs = re.findall(r"(\{[^{}]{0,200}\"id\"\s*:\s*\d+[^{}]{0,400}\})", html)
    page_meta.append({
        "url": url,
        "status": r.status_code,
        "len": len(html),
        "detail_ids": detail_ids[:50],
        "detail_id_count": len(detail_ids),
        "products_found": len(products),
        "json_blob_sample": json_blobs[:3],
    })
    print(f"{url} ids={len(detail_ids)} products={len(products)}", flush=True)

# Try common API endpoints
api_candidates = [
    f"{BASE}/index/Agv/getList.html",
    f"{BASE}/index/Agv/lists.html",
    f"{BASE}/index/ajax/agv.html",
    f"{BASE}/index/Agv/ajaxList.html",
    f"{BASE}/api/agv/list",
]
for api in api_candidates:
    for params in [{}, {"type": 1}, {"page": 1}, {"cate": 1}]:
        try:
            r = requests.get(api, params=params, headers=HEADERS, timeout=20)
            ctype = r.headers.get("content-type", "")
            body = r.text[:200].replace("\n", " ")
            print(f"API {api} params={params} status={r.status_code} ctype={ctype} body={body[:120]}", flush=True)
            if r.status_code == 200 and ("json" in ctype or r.text.strip().startswith("{") or r.text.strip().startswith("[")):
                page_meta.append({"api": api, "params": params, "body": r.text[:5000]})
        except Exception as e:
            print(f"API {api} ERR {e}", flush=True)

OUT.write_text(
    json.dumps(
        {"pages": page_meta, "products": list(all_products.values())},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(f"unique products={len(all_products)} -> {OUT}", flush=True)
for p in list(all_products.values())[:30]:
    print(f"  id={p['id']} name={p['name']!r} hero={bool(p['hero'])}", flush=True)
