"""Trim the Thor robots' videos to only the relevant clip (company 1381).

All 8 Agile Robots records carry the same 3 generic Hannover-Messe clips. On the
5 Thor arms, only "The Thor series at Hannover Messe" is relevant; drop the 2
generic company highlights. Uses replace_videos with a NON-EMPTY list (delete +
recreate) — the empty-list clear no-ops, but a one-item list replaces cleanly.
patch_existing=True is required with replace_videos (else the row overwrite can
blank scalar/media enrichment). Media and all other fields are untouched.

    cd scripts/research && export PYTHONIOENCODING=utf-8
    python fix_thor_videos_1381.py            # dry-run
    python fix_thor_videos_1381.py --apply
"""

from __future__ import annotations

import argparse
import time

from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402

THOR_IDS = [1552, 1553, 1554, 1555, 1556]
KEEP_TITLE_TOKEN = "thor series"  # the clip to keep (case-insensitive title match)


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
    client = ResearchApiClient()

    for rid in THOR_IDS:
        r = _bo(lambda: client._get(f"robots/robots/{rid}/"))
        vids = r.get("videos") or []
        keep = [v for v in vids if KEEP_TITLE_TOKEN in (v.get("title") or "").lower()]
        drop = [v for v in vids if v not in keep]
        keep_urls = [v.get("url") or v.get("youtube_url") for v in keep if (v.get("url") or v.get("youtube_url"))]
        print(f"{rid} {r.get('name')}: {len(vids)} videos -> keep {len(keep_urls)}, drop {len(drop)}")
        for v in drop:
            print(f"     drop: {(v.get('title') or '')[:55]}")
        if not keep_urls:
            print("     !! no 'Thor series' clip found — skipping (won't blank to nothing)")
            continue
        if not args.apply:
            continue
        row = {
            "id": rid, "name": r.get("name"),
            "company_slug": "agile-robots", "company_name": "Agile Robots AG",
            "video_urls": keep_urls,
        }
        _bo(lambda: client.bulk_import_robots(
            [row], update_existing=True, patch_existing=True, skip_company_update=True,
            replace_videos=True, status="pending_review"))
        after = _bo(lambda: client._get(f"robots/robots/{rid}/")).get("videos") or []
        print(f"     -> now {len(after)} video(s): " + "; ".join((v.get('title') or '')[:40] for v in after))


if __name__ == "__main__":
    main()
