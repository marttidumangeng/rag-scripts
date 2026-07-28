"""Gap-fill the 9 remaining Jaten (company 1461) pending_review AGVs.

These 9 SDM-*/MN-* records already have image + features + OEM url; the only gaps
are `no_tags` and `no_videos`. They are payload/variant siblings of the 5 already-
enriched Jaten AGVs (2911/2916/5185/5190/5191), which all carry the same vetted
TagCatalog AGV tag-set and the same 3 official Jaten AGV demo videos. This inherits
those onto the siblings — no invented specs/heroes.

Tags/videos only, gap-fill via bulk-import patch_existing (adds tags+videos on
records that have none; never overwrites, never creates). No media copy.

Usage:
  python fix_jaten_ghosts.py            # dry-run
  python fix_jaten_ghosts.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
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
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from youtube_metadata import enrich_video_list

COMPANY_ID = 1461
COMPANY_SLUG = "jaten-robot"
COMPANY_NAME = "Jaten Robot Co., Ltd."

# TagCatalog-exact set, verified live on the enriched Jaten AGV siblings.
AGV_TAGS = ("AGV|AMR|Autonomous|Autonomous Mobile Robot|Industrial|Intralogistics|"
            "Logistics|Material Handling|Warehouse Automation|Wheeled")

# Official Jaten AGV demo videos (same series demos used on the enriched siblings).
AGV_VIDEO_IDS = ["ZUCj8KkxOkU", "xL6YiRfujbA", "uIgpMO-F6CM"]

# The 9 ghost records (all wheeled lifting/piggyback AGVs).
TARGET_IDS = [2912, 2914, 2918, 5186, 5187, 5188, 5189, 5192, 5193]


def main() -> int:
    parser = argparse.ArgumentParser(description="Gap-fill Jaten AGV tags+videos (company 1461)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = None
    for attempt in range(15):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as exc:
            print(f"list retry {attempt}: {str(exc)[:70]}", file=sys.stderr)
            time.sleep(6)
    if robots is None:
        print("ERROR: could not fetch Jaten robot list", file=sys.stderr)
        return 1
    by_id = {int(r["id"]): r for r in robots}

    videos = enrich_video_list([f"https://www.youtube.com/watch?v={v}" for v in AGV_VIDEO_IDS])
    print("videos:")
    for v in videos:
        print("   ", v["url"], "|", v.get("title", "")[:60])
    if len(videos) < len(AGV_VIDEO_IDS):
        print(f"WARNING: only {len(videos)}/{len(AGV_VIDEO_IDS)} videos resolved", file=sys.stderr)

    plan, staging = [], {}
    for rid in TARGET_IDS:
        r = by_id.get(rid)
        if not r:
            print(f"SKIP missing id={rid}", file=sys.stderr)
            continue
        if str(r.get("status") or "").lower() != "pending_review":
            print(f"SKIP not pending_review id={rid} status={r.get('status')}", file=sys.stderr)
            continue
        has_tags = bool(r.get("tags"))
        has_vids = bool(r.get("videos"))
        row = {
            "id": rid, "name": r["name"],
            "company_slug": COMPANY_SLUG, "company_name": COMPANY_NAME,
            "tags": AGV_TAGS,
            "video_urls": videos,
            "source_locale": "en",
        }
        staging[rid] = row
        plan.append({"id": rid, "name": r["name"], "had_tags": has_tags, "had_videos": has_vids})
        print(f"  {rid} {r['name']}: +tags({'skip-has' if has_tags else 'add'}) "
              f"+videos({'skip-has' if has_vids else 'add'})")

    if not plan:
        print("ERROR: nothing to do", file=sys.stderr)
        return 1
    print(f"\nTargets: {len(plan)}")
    if not args.apply:
        print("Dry-run. Re-run with --apply")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="jaten-ghosts-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    all_ok = True
    for item in plan:
        rid = item["id"]
        bulk_row = staging_dict_to_bulk_import_row(staging[rid])
        bulk_row["id"] = rid
        (tmp / f"jaten-{rid}.json").write_text(json.dumps([bulk_row], indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            res = client.bulk_import_robots(
                [bulk_row], update_existing=True, patch_existing=True,
                replace_media=False, status="pending_review", skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            continue
        if int(res.get("created_count") or 0):
            all_ok = False
            print(f"WARNING {rid}: created a NEW robot -> {res}", file=sys.stderr)
        if int(res.get("error_count") or 0):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {res}", file=sys.stderr)
        for k in totals:
            totals[k] += int(res.get(k) or 0)
        print(f"  patched {rid}: {res.get('results')}")

    out = {"ok": all_ok, "company_id": COMPANY_ID, "targets": len(plan), **totals}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    (_RESEARCH_DIR / "staging" / "reports" / "jaten-ghosts-result.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
