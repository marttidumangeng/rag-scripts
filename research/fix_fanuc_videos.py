"""Strip FANUC CNC/software promo videos (and known wrong-model clips) from robots.

Audit (2026-07-16) found 59 FANUC robots carrying videos that are NOT robot demos —
FANUC CNC / simulation / software promos ("What you can do with the servo model",
"CNC GUIDE 2 Introduction Movie", "CNC Reflection Studio", "High-speed simulation
at 100x") — plus a handful with a clearly WRONG model's clip (DR-6iB carried M-6iB
deburring/casepacking videos).

Per stakeholder: strip the software videos, keep any genuine robot video (a robot may
end with fewer or zero — honest, better than wrong). Removal is by video-id, applied
via DRF PATCH `video_urls` (serializer hard-deletes then recreates the survivors with
their titles). If a robot would end with the SAME set it already has, it is skipped.

Usage:
  python fix_fanuc_videos.py            # dry-run
  python fix_fanuc_videos.py --ids 4124 # one robot
  python fix_fanuc_videos.py --apply
"""

from __future__ import annotations

import argparse
import json
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

# Software / CNC / simulation promos — verified NOT robot demos. Remove from every robot.
SOFTWARE_IDS = {
    "aKMGt6UZoSI",  # What you can do with the servo model
    "5aoZ8eD7w4I",  # High-speed simulation at up to 100x speed
    "ch6nOOiWoBs",  # CNC GUIDE 2 Introduction Movie
    "7Xl3WwoeYbk",  # CNC Reflection Studio Screen Demo
    "KliVOHmXSHM",  # Machine simulation with CNC Reflection Studio
}
# Wrong-model clips on specific robots (id -> set of video-ids to drop).
WRONGMODEL_BY_ID: dict[int, set[str]] = {
    # DR-6iB / DR-3iB delta robots carried M-6iB deburring/casepacking clips.
    # Filled from the audit below; extend as verified.
}


def vid_id(v: Any) -> str:
    u = v.get("url") if isinstance(v, dict) else v
    return extract_youtube_video_id(u or "") or ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Strip FANUC software/wrong-model videos")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
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
    if args.ids:
        pend = [r for r in pend if int(r["id"]) in set(args.ids)]

    plan = []
    for r in sorted(pend, key=lambda x: x["id"]):
        rid = int(r["id"])
        vids = r.get("videos") or []
        drop = SOFTWARE_IDS | WRONGMODEL_BY_ID.get(rid, set())
        kept, removed = [], []
        for v in vids:
            i = vid_id(v)
            if i and i in drop:
                removed.append((i, (v.get("title") if isinstance(v, dict) else "") or ""))
            else:
                u = v.get("url") if isinstance(v, dict) else v
                entry = {"url": u}
                if isinstance(v, dict) and v.get("title"):
                    entry["title"] = v["title"]
                if isinstance(v, dict) and v.get("description"):
                    entry["description"] = v["description"]
                kept.append(entry)
        if not removed:
            continue
        plan.append({"id": rid, "name": r["name"], "removed": removed, "kept": kept,
                     "before": len(vids), "after": len(kept)})
        print(f"  {rid:<6}{r['name'][:26]:<27} {len(vids)}->{len(kept)} vids "
              f"(drop {[t[:22] for _, t in removed][:2]})")

    # Robots that keep >=1 genuine video are cleaned via video_urls PATCH. Robots whose
    # videos are ALL junk would need clearing to empty, which the DRF serializer refuses
    # (empty video_urls is ignored) — separate them out rather than fail-loop.
    clean = [p for p in plan if p["after"] >= 1]
    needs_clear = [p for p in plan if p["after"] == 0]
    print(f"\nrobots with junk videos: {len(plan)} | software/wrong videos found: "
          f"{sum(len(p['removed']) for p in plan)}")
    print(f"  -> {len(clean)} cleanable (keep >=1 real video)")
    print(f"  -> {len(needs_clear)} all-junk (API can't clear to empty; needs manual/server clear): "
          f"{[p['id'] for p in needs_clear][:12]}")
    plan = clean
    (_RESEARCH_DIR / "staging" / "reports" / "fanuc-videos-preview.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    if not plan:
        print("Nothing to do."); return 0
    if not args.apply:
        print("Dry-run. Re-run with --apply"); return 0

    ok = fail = 0
    for p in plan:  # only the cleanable set
        rid = p["id"]
        try:
            client._patch(f"robots/robots/{rid}/", {"video_urls": p["kept"]})
            ok += 1
            print(f"  ok {rid} {p['name']}: {p['before']}->{p['after']}")
        except Exception as e:
            fail += 1
            print(f"  FAIL {rid}: {str(e)[:70]}", file=sys.stderr)
        time.sleep(0.15)

    out = {"ok": fail == 0, "cleaned": ok, "failed": fail, "needs_manual_clear": len(needs_clear),
           "needs_manual_clear_ids": [p["id"] for p in needs_clear]}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "fanuc-videos-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
