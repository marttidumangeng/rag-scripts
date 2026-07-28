"""Replace non-AMP YouTube hits on AMP Delta (1472)."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from youtube_metadata import enrich_video_list

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}


def yt_search(query: str, limit: int = 8) -> list[str]:
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    html = requests.get(url, headers=UA, timeout=30).text
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
    out: list[str] = []
    seen: set[str] = set()
    for vid in ids:
        if vid in seen:
            continue
        seen.add(vid)
        out.append(f"https://www.youtube.com/watch?v={vid}")
        if len(out) >= limit:
            break
    return out


def main() -> int:
    urls: list[str] = []
    for q in (
        "AMP Robotics Delta sorting",
        "AMP Robotics recycling robot",
        "AMP Robotics AI sorting MRF",
    ):
        urls.extend(yt_search(q))
    seen: set[str] = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    vids = enrich_video_list(uniq)
    kept = []
    for v in vids:
        title = (v.get("title") or "").lower()
        channel = (v.get("channel") or v.get("author_name") or "").lower()
        blob = f"{title} {channel}"
        if any(x in blob for x in ("omron", "abb ", "fanuc", "boston dynamics", "kuka")):
            continue
        if "amp" not in blob:
            continue
        kept.append(v)
        print("KEEP", (v.get("title") or "")[:90])
        if len(kept) >= 3:
            break
    if not kept:
        print("no AMP videos found")
        return 1
    client = ResearchApiClient()
    try:
        client._patch("robots/robots/1472/", {"video_urls": kept[:3]})
        print("patched video dicts", len(kept))
    except Exception as e:  # noqa: BLE001
        urls_only = [v.get("url") or v.get("video_url") for v in kept]
        urls_only = [u for u in urls_only if u]
        client._patch("robots/robots/1472/", {"video_urls": urls_only[:3]})
        print("patched urls", urls_only, "after", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
