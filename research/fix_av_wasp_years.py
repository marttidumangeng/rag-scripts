"""AeroVironment (283) — finish Wasp (519) + set the decided 2019 ROV release years.

Wasp 519 is the mini-UAV (photos/videos/2012/Aerial confirm it); its Chinese
description/purpose/features tripped `non_english_content`, and it had 3 photos.
Per operator decision the source URL is repointed to an authoritative Wasp AE reference
(the live avinc.com page now hosts an unrelated space antenna; the AV datasheets 404).

  519  Wasp     EN description/purpose/features; cited typed specs (1.3 kg, 760 mm,
                1020 mm span); real legacy weight/runtime/sensors; +1 verified Wikimedia
                Wasp III photo -> 4; url -> airforce-technology.com; sources added.
  1509 Pro 5    release_year 2019 (documented: VideoRay 2019 demo + product page).
  1510 Defender release_year 2019 (documented: VideoRay 2019 datasheet).

Usage: python fix_av_wasp_years.py [--ids N] [--apply]
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

_RD = Path(__file__).resolve().parent
if str(_RD) not in sys.path:
    sys.path.insert(0, str(_RD))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from load_env import load_research_env
load_research_env(local="--local" in sys.argv)
import requests
from api_client import ResearchApiClient

COMPANY_ID = 283

WASP_DESC = (
    "The Wasp AE is a nano/micro unmanned aircraft system developed by AeroVironment for "
    "close-range reconnaissance and surveillance. An all-environment evolution of the "
    "combat-proven Wasp III micro air vehicle, it is man-packable, hand-launched from a "
    "confined area, and recovers via a deep-stall landing. Its gimbaled payload carries a "
    "stabilized high-resolution electro-optical and infrared camera for day and night "
    "intelligence, surveillance, and reconnaissance. Built for portability and rapid "
    "deployment, it emphasizes a low acoustic and visual signature, ease of use, and "
    "short-range intelligence gathering for frontline forces."
)
WASP_PURPOSE = "Short-range reconnaissance and surveillance for frontline forces"
WASP_FEATURES = (
    "Man-packable and hand-launched from confined areas; all-environment (land and maritime) "
    "operation; low acoustic and visual signature; gimbaled stabilized EO/IR camera; "
    "Digital Data Link; ~50-minute endurance; deep-stall landing."
)
WASP_IMAGES = [
    "https://cdn.robotaigeek.com/robots/original/robot_519_74c241ade0f646549fdb0cc62795cce5.jpg",
    "https://cdn.robotaigeek.com/robots/photos/robot_519_1_df9861c455c24156896ef895297d017b.jpg",
    "https://cdn.robotaigeek.com/robots/photos/robot_519_2_e28c1bfda7de4fdd82390cf8f4e1dfcb.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/f/fa/Wasp_III_aircraft.jpg",
]
WASP_URL = "https://www.airforce-technology.com/projects/wasp-ae-small-unmanned-aircraft-system/"

PATCHES = {
    519: {
        "description": WASP_DESC,
        "purpose": WASP_PURPOSE,
        "features": WASP_FEATURES,
        "url": WASP_URL,
        "images": WASP_IMAGES,
        "weight_kg": 1.3, "length_mm": 760, "width_mm": 1020,
        "weight": "1.3 kg (2.85 lb)", "runtime": "50 minutes",
        "sensors": ["EO/IR gimbaled camera"], "connectivity": "Digital Data Link",
        "information_source_urls": [
            "https://www.airforce-technology.com/projects/wasp-ae-small-unmanned-aircraft-system/",
            "https://en.wikipedia.org/wiki/AeroVironment_Wasp_III",
        ],
        "_copy_media": True,
    },
    1509: {
        "release_year": 2019,
        "information_source_urls": ["https://videoray.com/products/mission-specialist-pro-5/"],
    },
    1510: {
        "release_year": 2019,
        "information_source_urls": [
            "https://www.videoray.com/images/DATASHEETS/2019_MSS_DEFENDER.pdf",
            "https://videoray.com/products/mission-specialist-defender/",
        ],
    },
}


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")


def _secret() -> str:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if s:
        return s
    env = _RD.parents[1] / "robotaigeek-server" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def _copy_media(rid: int, secret: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    try:
        r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
        return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return f"ERR {str(e)[:40]}"


def main() -> int:
    ap = argparse.ArgumentParser()
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
    by = {int(r["id"]): r for r in robots}

    S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
    def healthy(u: str) -> bool:
        if u.startswith("https://cdn.robotaigeek.com"):
            return True
        try:
            r = S.get(u, timeout=25)
            return bool(r.ok and r.headers.get("Content-Type", "").startswith("image") and len(r.content) > 6000)
        except Exception:
            return False

    ids = set(args.ids) if args.ids else set(PATCHES)
    plan = []
    for rid in sorted(ids):
        r = by.get(rid)
        if not r or str(r.get("status") or "").lower() != "pending_review":
            print(f"  {rid}: missing or not To Review — skip", file=sys.stderr); continue
        p = dict(PATCHES[rid])
        for u in p.get("images", []):
            if not healthy(u):
                print(f"  {rid}: dead image {u}", file=sys.stderr); return 1
        plan.append((rid, r.get("name"), p))
        print(f"  {rid:<6}{str(r.get('name'))[:16]:<17} -> {[k for k in p if not k.startswith('_')]}")

    if not args.apply:
        print("\nDry-run. Re-run with --apply."); return 0

    secret = _secret()
    ok = fail = 0
    for rid, name, p in plan:
        body = {k: v for k, v in p.items() if not k.startswith("_")}
        try:
            client._patch(f"robots/robots/{rid}/", body)
        except Exception as e:
            fail += 1; print(f"  FAIL {rid}: {str(e)[:90]}", file=sys.stderr); continue
        cm = ""
        if p.get("_copy_media"):
            cm = " copy_media=" + _copy_media(rid, secret)
        ok += 1
        print(f"  ok {rid} {name}{cm}")
        time.sleep(0.2)
    print(json.dumps({"ok": fail == 0, "patched": ok, "failed": fail}, indent=2))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
