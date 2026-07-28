"""Replace the Thor-series heroes with per-model OEM renders (company 1381).

Thor 3/7/12/20 shared ONE byte-identical welding photo and Thor 7 Pro used a
low-res 7.6 KB render. The OEM Thor-series page has a clean, model-specific product
render per model. This swaps each hero to its own render (media only — videos and
all other fields untouched), then copy-media + verify + cross-hash dedupe.

Source: agile-robots.com/en/solutions/thor-series (per-model product renders,
each visually verified robot-dominant before apply).

    cd scripts/research && export PYTHONIOENCODING=utf-8
    python fix_thor_heroes_1381.py            # dry-run
    python fix_thor_heroes_1381.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import os
import time

import requests

from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402

BASE = "https://www.agile-robots.com/media/files/New_website/Solutions/Thor_series"
HEROES = {
    1552: {"name": "Thor 3", "img": f"{BASE}/AgileRobots-ThorSeries-Thor3.jpg"},
    1553: {"name": "Thor 7", "img": f"{BASE}/AgileRobots-ThorSeries-Thor7.jpg"},
    1554: {"name": "Thor 7 Pro", "img": f"{BASE}/AgileRobots-ThorSeries-Thor7Pro.jpg"},
    1555: {"name": "Thor 12", "img": f"{BASE}/AgileRobots-ThorSeries-Thor12-2.jpg"},
    1556: {"name": "Thor 20", "img": f"{BASE}/AgileRobots-ThorSeries-Thor20.jpg"},
}
NOTE_MARKER = "[HERO FIX 2026-07-25 per-model]"
NOTE = (f"{NOTE_MARKER} Replaced the shared welding photo (Thor 3/7/12/20) / low-res render "
        "(Thor 7 Pro) with this model's own OEM Thor-series render.")


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")


def _internal_headers() -> dict[str, str]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        raise RuntimeError("INTERNAL_API_SECRET missing")
    return {"X-Internal-Secret": secret}


def copy_media(rid: int) -> dict:
    r = requests.post(
        f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1",
        headers=_internal_headers(), timeout=240)
    r.raise_for_status()
    return r.json()


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

    for rid, h in HEROES.items():
        print(f"{rid} {h['name']} -> {h['img']}  ({'APPLY' if args.apply else 'dry-run'})")
        if not args.apply:
            continue
        detail = _bo(lambda: client._get(f"robots/robots/{rid}/"))
        notes = str(detail.get("notes") or "")
        if NOTE_MARKER not in notes:
            notes = f"{NOTE}\n{notes}".strip()
        row = {
            "id": rid, "name": h["name"],
            "company_slug": "agile-robots", "company_name": "Agile Robots AG",
            "image": h["img"], "images": [h["img"]], "s3_image": None,
        }
        _bo(lambda: client.bulk_import_robots(
            [row], update_existing=True, patch_existing=True, skip_company_update=True,
            replace_media=True, status="pending_review"))
        _bo(lambda: client._patch(f"robots/robots/{rid}/",
                                  {"image": h["img"], "s3_image": None, "notes": notes}))
        print("  copy-media:", copy_media(rid).get("status") or "ok")

    if not args.apply:
        return

    print("--- verify + cross-hash dedupe ---")
    time.sleep(2)
    hashes: dict[str, int] = {}
    for rid, h in HEROES.items():
        robot = _bo(lambda: client._get(f"robots/robots/{rid}/"))
        url = str(robot.get("s3_image") or robot.get("image") or "")
        if "cdn.robotaigeek.com" not in url:
            print(f"  {rid} {h['name']}: NO owned CDN ({url})"); continue
        resp = requests.get(url, timeout=90)
        magic = resp.content[:4]
        ok = resp.status_code == 200 and len(resp.content) > 8000 and (
            resp.content[:3] == b"\xff\xd8\xff" or magic == b"\x89PNG" or magic == b"RIFF")
        digest = hashlib.sha256(resp.content).hexdigest()[:12]
        dup = f" DUP of {hashes[digest]}" if digest in hashes else ""
        hashes.setdefault(digest, rid)
        print(f"  {rid} {h['name']}: {'OK' if ok else 'BAD'} {len(resp.content)}b {digest}{dup}")
    print(f"  unique hashes: {len(hashes)}/{len(HEROES)}")


if __name__ == "__main__":
    main()
