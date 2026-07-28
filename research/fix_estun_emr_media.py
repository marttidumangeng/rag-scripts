"""Replace WRONG media on the 15 Estun EMR-* cobot records (company 220).

Decision (Martti, 2026-07-16): "replace media only" — swap the wrong EMR heroes
(yellow industrial arm / CO-ARC welding cart / CN "5-Pro" infographic / blank) for
the correct official ESTUN CoDroid cobot arm render matched by payload class, and
replace the irrelevant generic clips (arc welding / digital-twin) with real ESTUN
cobot demos. Leaves the EMR-vs-S-series naming question alone.

Mechanisms (each the right tool):
  - Videos: DRF PATCH robots/robots/{id}/ with video_urls -> clean delete+recreate
    (serializer hard-deletes then recreates; carries titles). Auth: X-API-Key.
  - Image: bulk-import patch_existing=True + replace_media=True (force-overwrites
    `image` only, preserves description/features/specs, recopies to S3 synchronously),
    then copy-media + CDN verify.

Usage:
  python fix_estun_emr_media.py                 # dry-run (plan only)
  python fix_estun_emr_media.py --ids 3635      # apply to one robot (test)
  python fix_estun_emr_media.py --apply          # apply to all 15
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

import requests

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from youtube_metadata import enrich_video_list

COMPANY_ID = 220
COMPANY_SLUG = "estun"
_IMG = "https://en.estun.com/static/upload/image/20240524/"

# Official ESTUN CoDroid cobot arm renders (verified from en.estun.com/?list_191/,
# each paired to its model on that page). Payload kg -> canonical hero render.
RENDER_BY_PAYLOAD = {
    5:  _IMG + "1716543371655538.png",   # S5-90  (5 kg)
    10: _IMG + "1716543432450195.png",   # S10-140 (10 kg)
    15: _IMG + "1716543473227966.png",   # S20-180 (nearest >= 15 kg; no S15)
    20: _IMG + "1716543473227966.png",   # S20-180 (20 kg)
    25: _IMG + "1716543473227966.png",   # S20-180 (largest ESTUN cobot; no S25)
}

# Real ESTUN cobot demos (replace the irrelevant welding/digital-twin clips).
COBOT_VIDEO_IDS = [
    "rsxDqqyvdKI",  # ESTUN CoDroid collaborative robot in metal processing
    "Jy0i8DLl6Cw",  # ESTUN cobots in Automotive industry
]

SOURCE_NOTE = ("Media re-sourced 2026-07-16: official ESTUN CoDroid cobot render "
               "(payload-matched) + ESTUN cobot demo videos.")


def _payload_from_name(name: str) -> int | None:
    m = re.search(r"EMR-(\d+)", name)
    return int(m.group(1)) if m else None


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")


def _internal_secret() -> str:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if s:
        return s
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def _copy_media(rid: int, secret: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    try:
        resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
        return "ok" if resp.ok else f"HTTP {resp.status_code}"
    except requests.RequestException as exc:
        return f"ERR {str(exc)[:50]}"


def _fetch(client: ResearchApiClient) -> list[dict[str, Any]]:
    for attempt in range(15):
        try:
            return client.list_robots_for_company(COMPANY_ID)
        except Exception as exc:
            print(f"list retry {attempt}: {str(exc)[:60]}", file=sys.stderr)
            time.sleep(6)
    raise SystemExit("ERROR: could not fetch robot list")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace media on Estun EMR cobots (company 220)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ids", type=int, nargs="*", help="only these robot ids")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = _fetch(client)
    emr = [r for r in robots if "EMR-" in (r.get("name") or "")]
    if args.ids:
        emr = [r for r in emr if int(r["id"]) in set(args.ids)]
    emr.sort(key=lambda r: r["id"])

    cobot_videos = enrich_video_list([f"https://www.youtube.com/watch?v={v}" for v in COBOT_VIDEO_IDS])
    if len(cobot_videos) < len(COBOT_VIDEO_IDS):
        print(f"WARNING: only {len(cobot_videos)} cobot videos resolved (oEmbed reject?)", file=sys.stderr)
    print("cobot videos:")
    for v in cobot_videos:
        print("   ", v["url"], "|", v.get("title", "")[:70])

    plan = []
    for r in emr:
        p = _payload_from_name(r["name"])
        render = RENDER_BY_PAYLOAD.get(p)
        plan.append({"id": int(r["id"]), "name": r["name"], "payload": p, "render": render,
                     "cur_image": (r.get("s3_image") or r.get("image") or "")[:60]})
        print(f"  {r['id']} {r['name']}: payload={p} -> {render.split('/')[-1] if render else 'NO RENDER'}")

    missing = [x for x in plan if not x["render"]]
    if missing:
        print(f"ERROR: no render for {[x['id'] for x in missing]}", file=sys.stderr)
        return 1
    if not cobot_videos:
        print("ERROR: no cobot videos resolved", file=sys.stderr)
        return 1

    if not args.apply and not args.ids:
        print(f"\nDry-run: {len(plan)} EMR cobots. Re-run with --apply (or --ids N to test one).")
        return 0

    secret = _internal_secret()
    if not secret:
        print("ERROR: INTERNAL_API_SECRET not configured (needed for copy-media)", file=sys.stderr)
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="estun-emr-media-"))
    results = []
    all_ok = True
    for x in plan:
        rid, render = x["id"], x["render"]
        # 1) Videos: DRF PATCH -> clean replace (delete old + recreate with titles).
        try:
            client._patch(f"robots/robots/{rid}/", {"video_urls": cobot_videos})
            vid_status = "replaced"
        except Exception as exc:
            all_ok = False
            vid_status = f"FAIL {str(exc)[:60]}"

        # 2) Image: bulk-import force-overwrite `image` + synchronous S3 recopy.
        bulk_row = staging_dict_to_bulk_import_row({
            "id": rid, "name": x["name"], "company_slug": COMPANY_SLUG,
            "image": render, "images": [{"url": render}],
            "research_notes": SOURCE_NOTE, "source_locale": "en",
        })
        bulk_row["id"] = rid
        (tmp / f"emr-{rid}.json").write_text(json.dumps([bulk_row], indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            res = client.bulk_import_robots(
                [bulk_row], update_existing=True, patch_existing=True,
                replace_media=True, status="pending_review", skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
            img_status = "updated" if int(res.get("updated_count") or 0) else str(res)
            if int(res.get("created_count") or 0):
                all_ok = False
                img_status = f"CREATED?! {res}"
        except Exception as exc:
            all_ok = False
            img_status = f"FAIL {str(exc)[:60]}"

        # 3) copy-media so CDN/s3_image refreshes from the new external render.
        cm = _copy_media(rid, secret)
        if cm != "ok":
            all_ok = False
        results.append({"id": rid, "name": x["name"], "video": vid_status, "image": img_status, "copy_media": cm})
        print(f"  {rid} {x['name']}: video={vid_status} image={img_status} copy_media={cm}")
        time.sleep(0.2)

    out = {"ok": all_ok, "count": len(results), "results": results}
    (_RESEARCH_DIR / "staging" / "reports" / "estun-emr-media-result.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": all_ok, "count": len(results)}, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
