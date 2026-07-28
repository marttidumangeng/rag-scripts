"""YouTube + tags check for DINGS Gripper."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from load_env import load_research_env

load_research_env()
from tag_suggest import TagCatalog
from youtube_metadata import enrich_video_list

HEADERS = {"User-Agent": "Mozilla/5.0"}
session = requests.Session()
session.headers.update(HEADERS)

def yt_ids(query: str, limit: int = 6) -> list[str]:
    resp = session.get("https://www.youtube.com/results", params={"search_query": query}, timeout=30)
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
    out = []
    for v in ids:
        if v not in out:
            out.append(v)
        if len(out) >= limit:
            break
    return out

urls = []
for q in [
    "DINGS gripper electric",
    "dingsmotion gripper",
    "DINGS Motion robotic gripper",
    "Jiangsu DINGS gripper",
]:
    for v in yt_ids(q):
        u = f"https://www.youtube.com/watch?v={v}"
        if u not in urls:
            urls.append(u)

# include known serper hit
if "https://www.youtube.com/watch?v=g90zDBm1s-M" not in urls:
    urls.insert(0, "https://www.youtube.com/watch?v=g90zDBm1s-M")

enriched = enrich_video_list(urls[:15])
yt = [{"url": e.get("url"), "title": e.get("title")} for e in enriched]
Path("staging/reports/dings-youtube.json").write_text(json.dumps(yt, indent=2, ensure_ascii=False), encoding="utf-8")
for e in yt:
    title = (e.get("title") or "").encode("ascii", "replace").decode()
    print(f"{title} | {e.get('url')}", flush=True)

cat = TagCatalog.load()
have = {t.get("name") for t in cat.tags}
for w in [
    "Industrial", "Manufacturing", "Pick-and-Place", "Compact", "Modular",
    "Precision", "Electric", "Actuator", "End Effector", "Manipulation",
    "Assembly", "Stationary", "Lightweight",
]:
    print(f"TAG {w}: {'OK' if w in have else 'MISSING'}", flush=True)
