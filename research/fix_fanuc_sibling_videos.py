"""Give the 21 all-software-video FANUC robots a correct video from a same-series sibling.

Those 21 had ONLY CNC/software promos; stripping to empty is impossible via the API
(DRF ignores an empty video_urls). Instead, per stakeholder, inherit the genuine
robot video that already exists on a same-series sibling (e.g. every M-410 robot gets
the real M-410 palletizing clip). PATCHing a NON-empty list replaces the junk cleanly.

A robot only gets touched if (a) it currently carries a known software/junk video and
(b) a sibling in its series has a genuine (non-software) video. Robots whose whole
series has no real video anywhere (e.g. SR SCARA) are left + reported.

Usage:
  python fix_fanuc_sibling_videos.py            # dry-run
  python fix_fanuc_sibling_videos.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from youtube_metadata import extract_youtube_video_id

COMPANY_ID = 189

# Software/CNC promos + the DR wrong-model set — anything here is NOT a robot demo.
JUNK_IDS = {
    "aKMGt6UZoSI", "5aoZ8eD7w4I", "ch6nOOiWoBs", "7Xl3WwoeYbk", "KliVOHmXSHM",
    "3opjWDd0Y9I", "Mbj43fQvQfI", "PfrKCN9x0KI",  # M-6iB clips (were on DR-6iB)
}
_SW = re.compile(r"(?i)(CNC GUIDE|servo model|FANUC Smart|ROBOGUIDE|Reflection Studio|"
                 r"Introduction Movie|What you can do with|simulation at up to|Digital Twin)")


def series_key(name: str) -> str:
    n = name.replace("FANUC", "").strip().lower()
    if n.startswith("lr mate"):
        return "lr-mate"
    if n.startswith("arc mate"):
        return "arc-mate"
    if n.startswith("crx"):
        return "crx"
    if n.startswith("sr-"):
        return "sr"
    m = re.match(r"([a-z]+-?\d+)i", n)
    return m.group(1) if m else n[:6]


def vid_id(v: Any) -> str:
    u = v.get("url") if isinstance(v, dict) else v
    return extract_youtube_video_id(u or "") or ""


def is_junk(v: Any) -> bool:
    if vid_id(v) in JUNK_IDS:
        return True
    t = (v.get("title") if isinstance(v, dict) else "") or ""
    return bool(_SW.search(t))


def main() -> int:
    ap = argparse.ArgumentParser(description="Inherit sibling videos for all-junk FANUC robots")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID); break
        except Exception as e:
            print(f"list retry {a}: {str(e)[:60]}", file=sys.stderr); time.sleep(5)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr); return 1

    pend = [r for r in robots if str(r.get("status") or "").lower() == "pending_review"]

    # 1) collect the genuine (non-junk) videos available per series.
    good_by_series: dict[str, list[dict[str, str]]] = {}
    for r in pend:
        sk = series_key(r["name"])
        for v in (r.get("videos") or []):
            if is_junk(v):
                continue
            u = v.get("url") if isinstance(v, dict) else v
            if not u:
                continue
            entry = {"url": u}
            if isinstance(v, dict) and v.get("title"):
                entry["title"] = v["title"]
            lst = good_by_series.setdefault(sk, [])
            if all(e["url"] != u for e in lst):
                lst.append(entry)

    # 2) robots whose videos are ALL junk -> inherit series' good videos.
    plan, nofix = [], []
    for r in sorted(pend, key=lambda x: x["id"]):
        vids = r.get("videos") or []
        if not vids or any(not is_junk(v) for v in vids):
            continue  # nothing wrong / already has a good one
        sk = series_key(r["name"])
        good = good_by_series.get(sk, [])[:3]
        if not good:
            nofix.append((r["id"], r["name"], sk))
            continue
        plan.append({"id": int(r["id"]), "name": r["name"], "series": sk, "videos": good})
        print(f"  {r['id']:<6}{r['name'][:24]:<25} [{sk}] <- {[g.get('title','')[:30] for g in good]}")

    print(f"\ninherit: {len(plan)} | no sibling video in series: {len(nofix)}")
    for i, n, sk in nofix:
        print(f"   NOFIX {i} {n[:24]} (series {sk} has no real video)")
    (_RESEARCH_DIR / "staging" / "reports" / "fanuc-sibling-videos-preview.json").write_text(
        json.dumps({"plan": plan, "nofix": nofix}, indent=2, ensure_ascii=False), encoding="utf-8")
    if not plan:
        print("Nothing to inherit."); return 0
    if not args.apply:
        print("Dry-run. Re-run with --apply"); return 0

    ok = fail = 0
    for p in plan:
        try:
            client._patch(f"robots/robots/{p['id']}/", {"video_urls": p["videos"]})
            ok += 1
            print(f"  ok {p['id']} {p['name']}: <- {len(p['videos'])} {p['series']} video(s)")
        except Exception as e:
            fail += 1
            print(f"  FAIL {p['id']}: {str(e)[:60]}", file=sys.stderr)
        time.sleep(0.15)
    out = {"ok": fail == 0, "inherited": ok, "failed": fail, "nofix": len(nofix)}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "fanuc-sibling-videos-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
