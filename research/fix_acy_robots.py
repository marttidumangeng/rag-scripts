"""Gap-only video backfill for ACY Automation Inc. (company 1369).

The ACY content queue is otherwise complete (image + features + specs + tags +
OEM url on all 90 pending_review robots). The only remaining gap on 24 robots is
`no_videos`. This script patches ONLY `video_urls` on those 24, using the
official ACY Automation YouTube channel (UCQmdLbGsptezOi5s9Q8NOOQ), matched to
each SKU's product family. No competitor clips; every id oEmbed-verified.

Nothing else is touched: patch_existing=True + minimal row (identity + videos),
status stays pending_review, skip_company_update=True, no media copy (videos are
plain URLs, not CDN objects).

Usage:
  python fix_acy_robots.py            # dry-run (writes preview JSON)
  python fix_acy_robots.py --apply
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

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

COMPANY_ID = 1369
COMPANY_SLUG = "acy-automation-inc"
COMPANY_NAME = "ACY Automation Inc."


def _yt(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


# Official ACY Automation channel demo shorts, mapped by SKU family.
# id -> list of ACY YouTube video ids (primary first). All titles oEmbed-verified.
VIDEOS_BY_ID: dict[int, list[str]] = {
    # --- Quick changers (square / round, incl. F variants) ---
    1101: ["Zz6EpguvXkk"],  # Square Quick Changer #60 RS
    1102: ["Zz6EpguvXkk"],  # Round Quick Changer AQ90 RS
    1377: ["Zz6EpguvXkk"],  # Square Quick Changer #60F
    1378: ["Zz6EpguvXkk"],  # Square Quick Changer #100
    1379: ["Zz6EpguvXkk"],  # Square Quick Changer #100F
    1380: ["Zz6EpguvXkk"],  # Square Quick Changer #160
    1381: ["Zz6EpguvXkk"],  # Square Quick Changer #160F
    1108: ["tRaaPcaefCg"],  # Star/Yushin Type Quick Changer -> Star EOAT Quick Changer
    1113: ["cvHT-nDckJ8"],  # Quick Changer Hanger -> EOAT storage bracket
    # --- Vacuum / suction cups ---
    1191: ["sreFgl-ivxY", "qUdiRy5LUwQ"],  # Flat Star Vacuum Cup 15mm Silicone
    1392: ["sreFgl-ivxY", "qUdiRy5LUwQ"],  # Flat Star Vacuum Cup 15mm Nitrile
    1393: ["sreFgl-ivxY"],  # Vacuum Cup Fitting 11mm M5 -> Suction cup cross connectors
    1402: ["qUdiRy5LUwQ"],  # Non-Rotating Suction Cup Suspension -> Suction cup holders
    # --- Mounting clamps ---
    1199: ["TfZM18GsrDE", "c2RRS1T66X4"],  # Cross Clamp 10x30 -> HD Cross Clamps
    1201: ["c2RRS1T66X4"],  # Long Angle Clamp w/ Ball-Joint -> EOAT mounting clamps
    1203: ["TfZM18GsrDE", "c2RRS1T66X4"],  # Swivel Cross Clamp -> HD Cross Clamps
    1205: ["c2RRS1T66X4"],  # Angle Plate 25mm -> EOAT mounting clamps
    1394: ["TfZM18GsrDE", "c2RRS1T66X4"],  # Heavy-Duty Angle Clamp HDAC-14
    # --- Profile / frame connectors (structural EOAT, shown in assembly) ---
    1209: ["GmYipWnn220", "tU23roIcZ50"],  # L-Type Frame Connector 25mm
    1400: ["GmYipWnn220", "tU23roIcZ50"],  # T-Type Frame Connector 25mm
    # --- Pneumatic cylinders ---
    1219: ["6LUWtDI7eP8"],  # Mini Cylinder 10mm/20mm -> Guided Cylinders / precise slide
    1401: ["6LUWtDI7eP8"],  # Mini Cylinder 10mm/50mm
    1221: ["6LUWtDI7eP8"],  # Twin Rod Cylinder 10mm/20mm
    1225: ["lyW27cEoDb0"],  # Rotary Cylinder 10mm 90deg -> RC series Rotary Table Cylinder
}

SOURCE_NOTE = "Videos: official ACY Automation YouTube channel (product-family demos), matched to SKU family."


def build_video_row(robot: dict[str, Any], vids: list[str]) -> dict[str, Any]:
    """Minimal patch row: identity + videos only. Everything else preserved."""
    videos = enrich_video_list([_yt(v) for v in vids])
    return {
        "name": robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "url": robot.get("url") or "",
        "video_urls": videos,
        "research_notes": SOURCE_NOTE,
        "source_locale": "en",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gap-only video fix for ACY company 1369")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    # Prod intermittently 502s on this list endpoint; client retries only 4x.
    robots = None
    for attempt in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as exc:
            print(f"list retry {attempt}: {str(exc)[:80]}", file=sys.stderr)
            time.sleep(6)
    if robots is None:
        print("ERROR: could not fetch ACY robot list (prod 502)", file=sys.stderr)
        return 1
    by_id = {int(r["id"]): r for r in robots}

    plan: list[dict[str, Any]] = []
    staging: dict[int, dict[str, Any]] = {}
    for rid, vids in VIDEOS_BY_ID.items():
        robot = by_id.get(rid)
        if not robot:
            print(f"SKIP missing robot id={rid}", file=sys.stderr)
            continue
        if str(robot.get("status") or "").lower() != "pending_review":
            print(f"SKIP not pending_review id={rid} status={robot.get('status')}", file=sys.stderr)
            continue
        if robot.get("videos"):
            print(f"SKIP already has videos id={rid} name={robot.get('name')!r}")
            continue
        row = build_video_row(robot, vids)
        n = len(row.get("video_urls") or [])
        staging[rid] = row
        plan.append({"id": rid, "name": robot["name"], "videos": n,
                     "urls": [v["url"] for v in row["video_urls"]]})
        print(f"  {rid} {robot['name']}: {n} video(s) -> {[v['url'] for v in row['video_urls']]}")

    preview = _RESEARCH_DIR / "staging" / "reports" / "acy-video-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    bad = [p for p in plan if p["videos"] < 1]
    if bad:
        print(f"ERROR: {len(bad)} target(s) resolved 0 videos (oEmbed reject?): "
              f"{[p['id'] for p in bad]}", file=sys.stderr)
        return 1
    print(f"\nTargets: {len(plan)}; total videos: {sum(p['videos'] for p in plan)}")
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="acy-video-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    all_ok = True
    for item in plan:
        rid = item["id"]
        row = staging[rid]
        bulk_row = staging_dict_to_bulk_import_row(row)
        bulk_row["id"] = rid  # company-scoped PK match -> patch, never create
        (tmp / f"{slugify_robot_name(row['name'])}-{rid}.json").write_text(
            json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            result = client.bulk_import_robots(
                [bulk_row],
                update_existing=True,
                patch_existing=True,
                replace_media=False,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            continue
        if int(result.get("created_count") or 0) > 0:
            all_ok = False
            print(f"WARNING {rid}: created a NEW robot (expected patch) -> {result}", file=sys.stderr)
        if int(result.get("error_count") or 0):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result}", file=sys.stderr)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  imported {rid}: {result.get('results')}")

    out = {"ok": all_ok, **totals, "preview": str(preview)}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "acy-video-fix-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
