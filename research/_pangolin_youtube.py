"""YouTube search for Pangolin models — model-token title gate."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fix_pangolin_robots import HERO
from youtube_metadata import fetch_youtube_metadata

OUT = _RESEARCH_DIR / "staging" / "reports" / "pangolin-youtube.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeek-ResearchAgent/1.0)"}

# Chinese + English search tokens per robot
SEARCH: dict[int, list[str]] = {
    2172: ["穿山甲 小鱼 机器人", "CSJBOT Xiaoyu robot", "Alpha 小鱼 迎宾"],
    2176: ["穿山甲 艾米 机器人", "CSJBOT 艾米", "Alpha Aimi robot"],
    2515: ["穿山甲 爱丽丝 机器人", "CSJBOT Alice robot", "Alpha 爱丽丝"],
    3497: ["穿山甲 小雪 机器人", "CSJBOT 小雪"],
    3197: ["穿山甲 精灵 机器人", "CSJBOT 精灵 迎宾"],
    2179: ["穿山甲 飞毛腿 Pro", "CSJBOT Speedybot Pro", "飞毛腿Pro 配送"],
    2185: ["穿山甲 飞毛腿Max", "CSJBOT Speedybot Max"],
    3499: ["穿山甲 飞毛腿Max 快递", "Speedybot Max"],
    3502: ["穿山甲 飞毛腿 送餐", "CSJBOT 飞毛腿 配送"],
    2189: ["穿山甲 熊猫 送餐机器人", "CSJBOT Panda robot 送餐"],
    3201: ["穿山甲 熊猫 酒店配送", "CSJBOT Panda hotel"],
    3503: ["穿山甲 熊猫医疗", "CSJBOT Panda medical"],
    2208: ["穿山甲 熊猫消杀", "CSJBOT disinfection robot"],
    2193: ["穿山甲 艾米送餐", "CSJBOT 艾米 送餐"],
    2195: ["穿山甲 牛魔王 F300", "CSJBOT 牛魔王", "Niumowang F300"],
    2203: ["穿山甲 任我行 无人零售", "CSJBOT Renwoxing"],
    3505: ["穿山甲 黑猫警长", "CSJBOT 黑猫警长"],
    3506: ["穿山甲 特种兵T1", "CSJBOT 特种兵"],
}

# Title must contain at least one of these (model-specific)
TITLE_NEED: dict[int, list[str]] = {
    2172: ["小鱼", "xiaoyu"],
    2176: ["艾米", "aimi", "amy"],
    2515: ["爱丽丝", "alice"],
    3497: ["小雪", "xiaoxue"],
    3197: ["精灵"],
    2179: ["飞毛腿", "speedybot", "feimaotui"],
    2185: ["飞毛腿", "speedybot", "max"],
    3499: ["飞毛腿", "speedybot", "max"],
    3502: ["飞毛腿", "speedybot"],
    2189: ["熊猫", "panda"],
    3201: ["熊猫", "panda", "酒店"],
    3503: ["熊猫", "panda", "医疗"],
    2208: ["消杀", "消毒", "disinfect"],
    2193: ["艾米", "送餐"],
    2195: ["牛魔王", "niumowang", "f300"],
    2203: ["任我行", "renwoxing", "无人零售"],
    3505: ["黑猫警长", "黑猫"],
    3506: ["特种兵", "t1"],
}


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
    ids = re.findall(r"\"videoId\":\"([a-zA-Z0-9_-]{11})\"", resp.text)
    out: list[str] = []
    for vid in ids:
        if vid not in out:
            out.append(vid)
        if len(out) >= limit:
            break
    return out


def title_ok(rid: int, title: str) -> bool:
    t = (title or "").lower()
    needs = TITLE_NEED.get(rid) or []
    if not needs:
        return False
    # brand context helps
    brand = any(x in t for x in ("穿山甲", "csjbot", "alpha", "pangolin", "飞毛腿", "熊猫"))
    hit = any(n.lower() in t for n in needs)
    # require model token; brand optional but preferred
    return hit


def main() -> None:
    results = {}
    for rid, queries in SEARCH.items():
        found = []
        seen = set()
        for q in queries:
            for vid in youtube_search_ids(q, limit=6):
                if vid in seen:
                    continue
                seen.add(vid)
                url = f"https://www.youtube.com/watch?v={vid}"
                meta = fetch_youtube_metadata(url) or {}
                title = meta.get("title") or ""
                ok = title_ok(rid, title)
                entry = {
                    "url": url,
                    "title": title,
                    "ok": ok,
                    "channel": meta.get("channel") or meta.get("author_name"),
                }
                found.append(entry)
                print(
                    f"{'OK' if ok else '..'} {rid} {(title or '?')[:55]} | {q[:30]}"
                )
            time.sleep(0.4)
        picks = [f for f in found if f["ok"]][:3]
        results[str(rid)] = {
            "model": HERO[rid]["model"],
            "picks": picks,
            "candidates": found[:12],
        }
        print(f"== {rid} picks={len(picks)}")

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
