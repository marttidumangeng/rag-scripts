"""Fix Wellwit (1423) video mis-attribution — model-specific clips were scattered
across the wrong models (AI-verify 'video doesn't match robot').

Per robot, keep: ONE company overview + any model/series-specific clip whose title
actually names this robot's model/series. Drop mismatched-model clips and the
redundant generic company videos. replace_videos with the kept (non-empty) list.

Title→scope map (from the fleet's actual YouTube titles):
  xYY0sQSkj6U  "Leading the Future in Autonomous Mobility"   -> company overview (all)
  Hq0g35Ab1VM  "Under Drive Lifting AMR: W6&W8 Series"        -> W6-* / W8-*
  fSdqNkIgAyY  "Mobile Chassis W6-600MB/W6-600DS"            -> W6-600MB / W6-600DS
  3tgmRkpCs0s  "WMF-CPD15/CPD20"                              -> models containing CPD
  wwLBXCnnh70  "W1000SL - Lidar SLAM"                         -> W3-1000SL
  h17_AWnUH8s  "Under Drive Lifting AMR W3-600B Series"       -> W3-600B
  z5Gy3BuB7Tc  "W500DL SLAM"  (no model in our catalog)       -> DROP everywhere
  IAnRxnrCi4k / hrVFXHMMy6k  generic company clips            -> DROP (padding)

    cd scripts/research && export PYTHONIOENCODING=utf-8
    python fix_wellwit_videos.py            # dry-run
    python fix_wellwit_videos.py --apply
"""
from __future__ import annotations
import argparse, time
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402

Y = "https://www.youtube.com/watch?v="
COMPANY = Y + "xYY0sQSkj6U"
W6W8 = Y + "Hq0g35Ab1VM"
W6_600 = Y + "fSdqNkIgAyY"
CPD = Y + "3tgmRkpCs0s"
W1000SL = Y + "wwLBXCnnh70"
W3_600B = Y + "h17_AWnUH8s"


def keep_for(model: str) -> list[str]:
    m = model.upper()
    keep = [COMPANY]  # every robot keeps one company overview
    if m.startswith("W6-") or m.startswith("W8-"):
        keep.append(W6W8)
    if m in ("W6-600MB", "W6-600DS"):
        keep.append(W6_600)
    if "CPD" in m:
        keep.append(CPD)
    if "1000SL" in m:
        keep.append(W1000SL)
    if m == "W3-600B":
        keep.append(W3_600B)
    # de-dupe, preserve order
    seen, out = set(), []
    for u in keep:
        if u not in seen:
            seen.add(u); out.append(u)
    return out


def _bo(fn):
    for a in range(7):
        try:
            return fn()
        except Exception as e:
            if any(c in str(e) for c in ("429", "502", "503")):
                time.sleep(4 * (a + 1)); continue
            raise
    raise SystemExit("gave up")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    c = ResearchApiClient()
    robots = _bo(lambda: c.list_robots_for_company(1423))

    changed = 0
    for r in robots:
        rid = r["id"]; model = r["name"].strip()
        cur = [(v.get("url") or v.get("youtube_url") or "") for v in (r.get("videos") or [])]
        keep = keep_for(model)
        drop = [u for u in cur if u not in keep]
        if not drop and set(cur) == set(keep):
            continue
        changed += 1
        extra = "+matched" if len(keep) > 1 else "company-only"
        print(f"{rid} {model:15} {len(cur)}->{len(keep)} ({extra}); dropping {len(drop)}")
        if args.apply:
            row = {"id": rid, "name": model, "company_slug": "shenzhen-wellwit-robotics-co-ltd",
                   "company_name": "Shenzhen Wellwit Robotics Co., Ltd.", "video_urls": keep}
            _bo(lambda: c.bulk_import_robots([row], update_existing=True, patch_existing=True,
                                             skip_company_update=True, replace_videos=True, status="pending_review"))
    print(f"\n{'applied' if args.apply else 'dry-run'}: {changed} robots re-curated")


if __name__ == "__main__":
    main()
