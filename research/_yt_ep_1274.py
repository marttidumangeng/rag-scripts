"""YouTube title-filter for EP Equipment models."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_env import load_research_env

load_research_env()
from youtube_metadata import enrich_video_list

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}

MODELS = {
    "JX0": ["JX0", "EP"],
    "ES15-15ES": ["ES15", "EP"],
    "ESL122": ["ESL122", "EP"],
    "EPT25-WA": ["EPT25", "EP"],
    "EPT20-20WA": ["EPT20-20WA", "EPT20"],
    "KPL201": ["KPL201", "EP"],
    "EPL185": ["EPL185", "EP"],
    "EPL154": ["EPL154", "EP"],
    "EPT20-RAP": ["EPT20-RAP", "RAP"],
    "RPL251": ["RPL251", "EP"],
    "RPL301": ["RPL301", "EP"],
    "ES20-WA": ["ES20-WA", "EP"],
    "WPL201": ["WPL201", "EP"],
}


def yt_ids(query: str) -> list[str]:
    r = requests.get(
        "https://www.youtube.com/results",
        params={"search_query": query},
        headers=H,
        timeout=40,
    )
    ids = re.findall(r"watch\?v=([\w-]{11})", r.text)
    seen = set()
    out = []
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
    return out


def main() -> None:
    result = {}
    for model, tokens in MODELS.items():
        q = f"{model} EP Equipment"
        ids = yt_ids(q)
        urls = [f"https://www.youtube.com/watch?v={i}" for i in ids[:12]]
        enriched = enrich_video_list(urls)
        # enrich_video_list returns list of dicts or urls with titles
        kept = []
        print(f"\n=== {model} q={q} ===")
        for item in enriched:
            if isinstance(item, dict):
                url = item.get("url") or item.get("video_url") or ""
                title = item.get("title") or ""
            else:
                url = str(item)
                title = ""
            title_l = title.lower()
            token_ok = any(t.lower() in title_l.replace(" ", "") for t in tokens[:1]) or (
                tokens[0].lower() in title_l
            )
            # require model token in title
            model_tok = model.lower().replace("-", "")
            compact = title_l.replace("-", "").replace(" ", "")
            ok = model.lower() in title_l or model_tok in compact or tokens[0].lower() in title_l
            print(f"  {'OK' if ok else 'no'} | {title[:90]}")
            print(f"     {url}")
            if ok and url:
                kept.append(url)
        result[model] = kept[:3]
    Path("staging/reports/_ep1274_youtube.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print("\nRESULT", json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
