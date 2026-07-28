"""Fix ConTrax Module One (robot 1560, Agile Robots) — AI-verify flags.

The original pass mis-attributed the media: the hero + gallery were Agile Robots'
*Agile ONE humanoid* renders (name collision inside the same company), and the
videos were generic Hannover-Messe highlights + a Thor-series clip — none depict
ConTrax. Specs were empty.

This fixer:
  - replace_media with the correct OEM image (BÄR ConTrax platform carrying a Yu 5
    arm, from the Agile Robots AMR/AGV page — visually verified robot-dominant)
  - replace_videos with none (fail closed; no ConTrax-specific clip found)
  - typed specs from the authoritative BÄR Automation ConTrax Module One page:
    payload 500 kg, travel 1.2 m/s (-> 4.32 km/h), 48 V x 42 Ah = 2016 Wh
  - features rewritten with the cited platform facts
  - release_year + price left blank on purpose (no grounded citation / no public
    price for a custom industrial AGV) — rationale recorded in notes

Sources: agile-robots.com/en/solutions/amr/agv (image + config),
baer-automation.com ConTrax Module One page (specs).

    cd scripts/research && export PYTHONIOENCODING=utf-8
    python fix_contrax_1560.py            # dry-run
    python fix_contrax_1560.py --apply
"""

from __future__ import annotations

import argparse
import os
import time

import requests

from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402

RID = 1560
OEM_IMG = ("https://www.agile-robots.com/media/_processed_/7/2/"
           "csm_AgileRobots-MobileRobotics-Content-Image-003_79a090863d.jpg")
URL = "https://www.agile-robots.com/en/solutions/amr/agv/#contrax-module-one"

SOURCES = [
    URL,
    "https://www.agile-robots.com/en/solutions/amr/agv/",
    "https://baer-automation.com/en/products/automated-guided-vehicle-solutions/contrax/contrax-module-one",
    "https://www.agile-robots.com/en/news/detail/mobile-manipulators-dynamic-flexibility-in-action/",
]

FEATURES = (
    "Mobile manipulator: a BAR Automation ConTrax mobile platform carrying an Agile Robots Yu 5 Industrial cobot\n"
    "500 kg transport payload (the Yu 5 arm handles up to 5 kg)\n"
    "Up to 1.2 m/s travel speed; SLAM free navigation with optional optical fine positioning\n"
    "48 V 42 Ah LiFePO battery with inductive charging for cycle-time-parallel, 24/7 operation\n"
    "Decoupled design: the AGV sets the arm on a supply station and returns to transport tasks\n"
    "Co-developed with BAR Automation and Idealworks for intralogistics"
)

NOTE_MARKER = "[HERO+DATA FIX 2026-07-25]"
NOTE = (
    f"{NOTE_MARKER} Replaced mis-attributed humanoid gallery (Agile ONE renders) with the correct "
    "ConTrax Module One image (BAR platform + Yu 5). Cleared mis-attributed videos "
    "(Hannover Messe highlights + a Thor-series clip). Specs from the BAR Automation ConTrax "
    "Module One page (payload 500 kg, 1.2 m/s, 48V/42Ah). No public price (custom industrial AGV "
    "system). No grounded launch-year citation (shown at LogiMAT 2025, but an exhibition is not a "
    "launch) -> release_year left blank."
)

TYPED = {
    "payload_kg": 500,
    "speed": 4.32,        # 1.2 m/s locomotion -> km/h
    "battery_wh": 2016,   # 48 V x 42 Ah
}


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
        headers=_internal_headers(), timeout=240,
    )
    r.raise_for_status()
    return r.json()


def verify_cdn(client: ResearchApiClient) -> None:
    robot = client._get(f"robots/robots/{RID}/")
    url = str(robot.get("s3_image") or robot.get("image") or "")
    if "cdn.robotaigeek.com" not in url:
        raise RuntimeError(f"no owned CDN hero: {url}")
    resp = requests.get(url, timeout=90)
    magic = resp.content[:4]
    ok = resp.status_code == 200 and len(resp.content) > 8000 and (
        resp.content[:3] == b"\xff\xd8\xff" or magic == b"\x89PNG" or magic == b"RIFF")
    if not ok:
        raise RuntimeError(f"CDN hero bad: {resp.status_code} {len(resp.content)}b magic={magic.hex()}")
    print(f"  CDN hero OK: {url} ({len(resp.content)}b)")
    print(f"  payload={robot.get('payload_kg')} speed={robot.get('speed')} battery_wh={robot.get('battery_wh')} "
          f"photos={len(robot.get('photos') or [])} videos={len(robot.get('videos') or [])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    client = ResearchApiClient()

    detail = client._get(f"robots/robots/{RID}/")
    notes = str(detail.get("notes") or "")
    if NOTE_MARKER not in notes:
        notes = f"{NOTE}\n{notes}".strip()

    row = {
        "id": RID,
        "name": "ConTrax Module One",
        "company_slug": "agile-robots",
        "company_name": "Agile Robots AG",
        "url": URL,
        "image": OEM_IMG,
        "images": [OEM_IMG],
        "s3_image": None,
        "video_urls": [],
    }
    patch_body = {
        "image": OEM_IMG,
        "s3_image": None,
        "features": FEATURES,
        "notes": notes,
        "information_source_urls": SOURCES,
        "status": "pending_review",
        **TYPED,
    }

    print("ConTrax Module One (1560)", "APPLY" if args.apply else "dry-run")
    print("  hero  ->", OEM_IMG)
    print("  typed ->", TYPED)
    print("  clears: 8 humanoid photos + 3 mis-attributed videos")
    if not args.apply:
        print("  (dry-run; re-run with --apply)")
        return

    def _bo(fn):
        for a in range(7):
            try:
                return fn()
            except Exception as e:
                if any(c in str(e) for c in ("429", "502", "503")):
                    time.sleep(4 * (a + 1)); continue
                raise
        raise SystemExit("gave up")

    _bo(lambda: client.bulk_import_robots(
        [row], update_existing=True, patch_existing=True, skip_company_update=True,
        replace_media=True, replace_videos=True, status="pending_review"))
    print("  bulk-import replace_media+replace_videos done")
    _bo(lambda: client._patch(f"robots/robots/{RID}/", patch_body))
    print("  patched specs+features+notes")
    print("  copy-media:", copy_media(RID).get("status") or "ok")
    time.sleep(2)
    verify_cdn(client)


if __name__ == "__main__":
    main()
