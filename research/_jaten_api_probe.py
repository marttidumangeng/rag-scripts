"""Probe Jaten getList AJAX endpoints; write raw responses."""
from __future__ import annotations

import json
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://jaten-robotics.com/index/Agv/index.html",
}
BASE = "https://jaten-robotics.com"
OUT = Path("staging/reports/jaten-api-probe.json")

candidates = [
    ("/index/Agv/getList.html", {"type": 1}),
    ("/index/Agv/getList.html", {"type": 2}),
    ("/index/Agv/getList.html", {}),
    ("/index/Agv/getList", {"type": 1}),
    ("/index/Agv/lists", {"type": 1}),
    ("/index/Product/getList.html", {"type": 1}),
    ("/agv/getList", {"type": 1}),
]

results = []
for path, params in candidates:
    url = BASE + path
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
        entry = {
            "url": r.url,
            "status": r.status_code,
            "ctype": r.headers.get("content-type"),
            "len": len(r.content),
            "body_head": r.text[:1500],
        }
        # try json
        try:
            entry["json_keys"] = list(r.json().keys()) if isinstance(r.json(), dict) else type(r.json()).__name__
        except Exception:
            entry["json_keys"] = None
        results.append(entry)
        print(f"{r.status_code} {r.url} len={len(r.content)}", flush=True)
    except Exception as e:
        results.append({"url": url, "error": repr(e)})
        print(f"ERR {url} {e!r}", flush=True)

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {OUT}", flush=True)
