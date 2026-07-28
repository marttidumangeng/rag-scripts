"""YouTube HTML search for Jaten AGV models; write JSON."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from youtube_metadata import enrich_video_list, fetch_youtube_metadata

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
OUT = Path("staging/reports/jaten-youtube.json")

QUERIES = {
    "company": ["Jaten AGV", "Jaten Robot AGV", "嘉腾 AGV", "Jaten AMR"],
    "R2SDM1500-335-MG0": ["Jaten R2SDM1500", "R2SDM1500-335-MG0"],
    "SDM300-339-MGD": ["Jaten SDM300-339", "SDM300-339-MGD"],
    "MN30-164": ["Jaten MN30-164", "MN30-164 AGV"],
    "AGV-31-MC500": ["Jaten AGV-31-MC500", "AGV-31-MC500", "Jaten Red Dot AGV"],
    "SDM500-D228": ["Jaten SDM500-D228", "SDM500-D228", "Jaten D228 AGV"],
    "MN100-164": ["Jaten MN100-164", "MN100-164 AGV"],
    "SDM1000-D228": ["Jaten SDM1000-D228", "SDM1000 D228"],
    "SDM2000-D228": ["Jaten SDM2000-D228", "SDM2000 D228"],
    "SDM3000-D228": ["Jaten SDM3000-D228", "SDM3000 D228"],
}


def search_ids(query: str, limit: int = 5) -> list[str]:
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException:
        return []
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
    out: list[str] = []
    for vid in ids:
        if vid not in out:
            out.append(vid)
        if len(out) >= limit:
            break
    return out


results: dict = {}
for key, queries in QUERIES.items():
    urls: list[str] = []
    for q in queries:
        for vid in search_ids(q, limit=4):
            url = f"https://www.youtube.com/watch?v={vid}"
            if url not in urls:
                urls.append(url)
    enriched = enrich_video_list(urls)
    meta = []
    for item in enriched:
        u = item if isinstance(item, str) else (item.get("url") or "")
        if not u:
            continue
        m = fetch_youtube_metadata(u) or {}
        title = m.get("title") or (item.get("title") if isinstance(item, dict) else "") or ""
        meta.append({"url": u, "title": title})
        print(f"{key}: {title!r} | {u}", flush=True)
    results[key] = meta

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {OUT}", flush=True)
