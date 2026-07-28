#!/usr/bin/env python3
"""Fix Pangolin 1413 display names + drop garbage video titles; search Xiaoyu replacement."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from youtube_metadata import (
    enrich_video_list,
    fetch_youtube_metadata,
    is_reject_robot_video_title,
)

COMPANY_ID = 1413
PREFIX = "Pangolin Robotics "
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeek-ResearchAgent/1.0)"}


def youtube_search_ids(query: str, limit: int = 8) -> list[str]:
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


def find_xiaoyu_videos() -> list[dict]:
    queries = [
        "CSJBOT Xiaoyu",
        "穿山甲 小鱼 机器人",
        "Alpha Robotics 小鱼",
        "CSJBOT 小鱼 迎宾",
        "小鱼 迎宾机器人 CSJBOT",
    ]
    hits: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        for vid in youtube_search_ids(q, limit=8):
            if vid in seen:
                continue
            seen.add(vid)
            url = f"https://www.youtube.com/watch?v={vid}"
            meta = fetch_youtube_metadata(url)
            title = meta.get("title") or ""
            low = title.casefold()
            ok_token = any(t in low or t in title for t in ("小鱼", "xiaoyu", "timo"))
            brand = any(
                b in low or b in title
                for b in ("csjbot", "alpha", "pangolin", "穿山甲", "alpharobotics")
            )
            rejected = is_reject_robot_video_title(title)
            # Prefer human-readable product titles over hashtag dumps
            readable = len(re.sub(r"[#@].*", "", title).strip()) >= 12
            hits.append(
                {
                    "url": url,
                    "title": title,
                    "ok_token": ok_token,
                    "brand": brand,
                    "rejected": rejected,
                    "readable": readable,
                }
            )
        time.sleep(0.4)
    return hits


def main() -> int:
    apply = "--apply" in sys.argv
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)

    xiaoyu_hits = find_xiaoyu_videos()
    Path("staging/reports/_xiaoyu_yt.json").write_text(
        json.dumps(xiaoyu_hits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    replacements = [
        h
        for h in xiaoyu_hits
        if h["ok_token"] and h["brand"] and not h["rejected"] and h.get("readable", True)
    ]
    # Prefer titles that name Timo/Xiaoyu without WeChat/hash junk (already filtered)
    replacements.sort(
        key=lambda h: (
            0 if "timo" in (h["title"] or "").casefold() or "小鱼" in (h["title"] or "") else 1,
            len(h["title"] or ""),
        )
    )
    print(f"Xiaoyu candidates: {len(replacements)} usable / {len(xiaoyu_hits)} scanned")
    for h in replacements[:5]:
        print(f"  KEEP {h['title'][:80]} | {h['url']}")

    plan = []
    for r in robots:
        if str(r.get("status") or "").lower() == "rejected":
            continue
        rid = int(r["id"])
        name = (r.get("name") or "").strip()
        new_name = name
        if name.startswith(PREFIX):
            new_name = name[len(PREFIX) :].strip()

        vids = r.get("videos") or r.get("video_urls") or []
        cleaned = enrich_video_list(vids if isinstance(vids, list) else [])
        # Xiaoyu: if empty after reject, attach preferred readable Timo clip
        if rid == 2172 and not cleaned:
            preferred = "https://www.youtube.com/watch?v=NL4xgiJmYdE"
            if replacements:
                cleaned = enrich_video_list([replacements[0]["url"]])
            if not cleaned:
                cleaned = enrich_video_list([preferred])

        name_changed = new_name != name
        # Compare video URLs/titles
        old_urls = []
        for v in vids if isinstance(vids, list) else []:
            if isinstance(v, dict):
                old_urls.append((v.get("url"), v.get("title")))
            else:
                old_urls.append((v, None))
        new_urls = [(v.get("url"), v.get("title")) for v in cleaned]
        vids_changed = old_urls != new_urls

        if not name_changed and not vids_changed:
            continue

        body = {}
        if name_changed:
            body["name"] = new_name
        if vids_changed:
            body["video_urls"] = cleaned
        plan.append(
            {
                "id": rid,
                "status": r.get("status"),
                "old_name": name,
                "new_name": new_name,
                "old_video_titles": [t for _, t in old_urls],
                "new_video_titles": [t for _, t in new_urls],
                "body": body,
            }
        )

    Path("staging/reports/_pangolin_name_video_fix.json").write_text(
        json.dumps(
            [{k: v for k, v in p.items() if k != "body"} for p in plan],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nplan {len(plan)} robots")
    for p in plan:
        print(f"  {p['id']} {p['status']}")
        if p["old_name"] != p["new_name"]:
            print(f"    name: {p['old_name']!r} -> {p['new_name']!r}")
        if p["old_video_titles"] != p["new_video_titles"]:
            print(f"    vids: {p['old_video_titles']} -> {p['new_video_titles']}")

    if not apply:
        print("dry-run only; pass --apply to patch")
        return 0

    ok = fail = 0
    for p in plan:
        try:
            client._patch(f"robots/robots/{p['id']}/", p["body"])
            print(f"ok {p['id']}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {p['id']}: {e}")
            fail += 1
        time.sleep(0.1)
    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
