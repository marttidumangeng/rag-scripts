"""Fill Universal Robots (192) videos with model-titled YouTube clips.

Prefer titles that name the exact model token. Skip software/academy tutorials
and sibling-model titles (UR10e clip must not land on UR10).

Usage:
  python fix_ur_videos.py            # dry-run
  python fix_ur_videos.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any

import requests

_RESEARCH_DIR = __import__("pathlib").Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from fix_universal_robots import normalize_model
from youtube_metadata import enrich_video_list, fetch_youtube_metadata

COMPANY_ID = 192
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RobotAIGeek-ResearchAgent/1.0)",
}

# Hand-picked official / clearly model-named seeds (verified titles).
SEED: dict[str, list[str]] = {
    "UR3": ["https://www.youtube.com/watch?v=NGlTRErHkPs"],
    "UR5": ["https://www.youtube.com/watch?v=AJ-Eq1uHz8s"],  # may fail title gate
    "UR10": ["https://www.youtube.com/watch?v=gkm_uMQ8NbM"],
    "UR3e": ["https://www.youtube.com/watch?v=y62T-Q57JbY"],  # e-Series family — gated
    "UR5e": ["https://www.youtube.com/watch?v=KdXA4pnfqT4"],
    "UR10e": ["https://www.youtube.com/watch?v=0kNF_l22-HM"],
    "UR16e": [],
    "UR20": ["https://www.youtube.com/watch?v=jdedvpNPg2g"],
    "UR30": [],
    "UR7e": [],
    "UR12e": [],
    "UR15": [],
    "UR18": [],
    "UR8": [],
    "UR8 Long": [],
}

_REJECT_TITLE = re.compile(
    r"(?i)\b("
    r"academy|online\s+training|tool\s+configuration|safety\s+plane|"
    r"tcp,?\s+orientation|quick\s+start|polyscope\s+tutorial|"
    r"how\s+to\s+program|core\s+track"
    r")\b"
)


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
    return [f"https://www.youtube.com/watch?v={v}" for v in out]


def model_tokens(model: str) -> list[str]:
    m = model.lower().replace(" ", "")
    toks = [m, model.lower()]
    if m.endswith("e") and len(m) > 2:
        toks.append(m[:-1])  # allow loose? NO — don't add bare ur5 for ur5e
    return [t for t in toks if t == m or t == model.lower()]


def title_ok(model: str, title: str) -> bool:
    t = (title or "").lower()
    if not t or _REJECT_TITLE.search(t):
        return False
    m = model.lower().replace(" ", "")
    # normalize spaces/hyphens in title: "ur 20" / "ur-20"
    compact = re.sub(r"[^a-z0-9]+", "", t)
    if m not in compact:
        return False
    # CB vs e: UR10 must not match UR10e title
    if not m.endswith("e"):
        if m + "e" in compact:
            return False
    else:
        # UR5e must not match only UR5 — already requires m in compact
        pass
    # UR8 Long: accept ur8 long / ur8long
    if model == "UR8 Long":
        return "ur8long" in compact or ("ur8" in compact and "long" in t)
    if model == "UR8":
        # allow ur8 long page as same product
        return "ur8" in compact
    return True


def pick_videos(model: str) -> list[dict[str, str]]:
    candidates: list[str] = []
    candidates.extend(SEED.get(model) or [])
    queries = [
        f"Universal Robots {model}",
        f"Universal Robots {model} cobot",
        f'"{model}" Universal Robots official',
    ]
    if model == "UR8 Long":
        queries.append("Universal Robots UR8 Long")
    for q in queries:
        candidates.extend(youtube_search_ids(q, limit=6))
    # dedupe preserve order
    seen = set()
    urls = []
    for u in candidates:
        if u not in seen:
            seen.add(u)
            urls.append(u)

    accepted: list[dict[str, str]] = []
    for u in urls:
        meta = fetch_youtube_metadata(u)
        title = meta.get("title") or ""
        if not title_ok(model, title):
            continue
        accepted.append({"url": u, "title": title, "description": meta.get("description") or ""})
        if len(accepted) >= 2:
            break
        time.sleep(0.2)
    return accepted


def existing_urls(full: dict[str, Any]) -> list[str]:
    vids = full.get("video_urls") or full.get("videos") or []
    out = []
    for v in vids:
        if isinstance(v, dict) and v.get("url"):
            out.append(v["url"])
        elif isinstance(v, str):
            out.append(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only-missing", action="store_true", default=True)
    ap.add_argument("--refresh-all", action="store_true", help="Also replace rows that already have videos")
    args = ap.parse_args()
    if args.refresh_all:
        args.only_missing = False

    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    ]

    cache: dict[str, list[dict[str, str]]] = {}
    plan = []
    for r in sorted(robots, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        model = normalize_model(full.get("name") or "")
        if not model:
            continue
        have = existing_urls(full)
        if args.only_missing and have:
            continue
        if model not in cache:
            print(f"search {model}…")
            cache[model] = pick_videos(model)
            print(f"  -> {len(cache[model])} accepted")
            for v in cache[model]:
                print(f"     {v['title'][:70]!r} {v['url']}")
        vids = cache[model]
        if not vids:
            print(f"SKIP {rid} {model}: no model-titled video")
            continue
        plan.append({"id": rid, "model": model, "name": full.get("name"), "videos": vids, "had": len(have)})

    print(f"\nplanned={len(plan)}")
    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    ok = fail = 0
    for p in plan:
        try:
            body = {"video_urls": enrich_video_list([v["url"] for v in p["videos"]])}
            client._patch(f"robots/robots/{p['id']}/", body)
            print(f"ok {p['id']} {p['model']} vids={len(p['videos'])}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {p['id']}: {exc}")
            fail += 1
        time.sleep(0.1)
    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
