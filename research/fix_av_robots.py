"""AeroVironment (283) To Review enrichment — the 3 unambiguous robots.

Fixes only what the deterministic quality flags (robots/quality.py) actually raise,
per-robot, sourced from the live avinc.com product pages (browser-verified):

  Pro 5 (1509)    missing_video + wrong hero (its s3_image is byte-identical to a
                  VigilantHalo shelter photo) → rebuild gallery external-Pro5-render-first
                  + force copy-media; add the genuine VideoRay Pro 5 demo video; typed dims+weight.
  Defender (1510) missing_specs → typed dims from the OEM page (28.0x15.5x9.5 in).
  VigilantHalo    missing_specs → it is a software C2 platform (no physical specs); set the
      (1506)      one factual "spec" the page states — deployment connectivity.

Wasp (519) and release_year are handled separately (open decisions), not here.

Usage:
  python fix_av_robots.py            # dry-run
  python fix_av_robots.py --ids 1509 # one robot
  python fix_av_robots.py --apply
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

# genuine Pro 5 gallery: external OEM render FIRST (so Robot.image is a downloadable
# hero copy-media can refresh), then the existing verified yellow-ROV shots. The dropped
# ids are cross-contaminated: 5600 green-screen, 5602 soldier w/ UAV, 5603 fixed-wing.
PRO5_IMAGES = [
    "https://www.avinc.com/wp-content/uploads/2026/03/Product-Page_UMV_Pro-5_Hero.jpg",
    "https://cdn.robotaigeek.com/robots/photos/photo-1509-5597.jpg",
    "https://cdn.robotaigeek.com/robots/photos/photo-1509-5598.jpg",
    "https://cdn.robotaigeek.com/robots/photos/photo-1509-5599.webp",
    "https://cdn.robotaigeek.com/robots/photos/photo-1509-5601.webp",
]
PRO5_VIDEO = {"url": "https://www.youtube.com/watch?v=UypS8GORaPg",
              "title": "VideoRay Pro 5 & MSS Defender | ROV"}

PATCHES = {
    1509: {  # Pro 5 — 51.5 x 33.0 x 25.7 cm, 10 kg (OEM page)
        "images": PRO5_IMAGES,
        "video_urls": [PRO5_VIDEO],
        "length_mm": 515, "width_mm": 330, "height_mm": 257, "weight_kg": 10.0,
        "_copy_media": True,
    },
    1510: {  # Defender — 28.0 x 15.5 x 9.5 in = 71.1 x 39.4 x 24.1 cm (OEM page)
        "length_mm": 711, "width_mm": 394, "height_mm": 241,
    },
    1506: {  # VigilantHalo — software C2 platform; only factual "spec" is deployment
        "connectivity": "Cloud, mobile, and fixed-site deployment; secure micro-service architecture",
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

    # health-check any external image before staging it
    S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0"
    def healthy(u: str) -> bool:
        if u.startswith("https://cdn.robotaigeek.com"):
            return True  # owned, already served
        try:
            r = S.get(u, timeout=25)
            return bool(r.ok and r.headers.get("Content-Type", "").startswith("image") and len(r.content) > 6000)
        except Exception:
            return False

    ids = set(args.ids) if args.ids else set(PATCHES)
    plan = []
    for rid in sorted(ids):
        r = by.get(rid)
        if not r:
            print(f"  {rid}: not in company {COMPANY_ID} — skip", file=sys.stderr); continue
        if str(r.get("status") or "").lower() != "pending_review":
            print(f"  {rid} {r.get('name')}: status {r.get('status')} — SKIP (only To Review)", file=sys.stderr); continue
        p = dict(PATCHES[rid])
        if "images" in p:
            bad = [u for u in p["images"] if not healthy(u)]
            if bad:
                print(f"  {rid}: dead image url(s) {bad}", file=sys.stderr); return 1
        plan.append((rid, r.get("name"), p))
        keys = [k for k in p if not k.startswith("_")]
        print(f"  {rid:<6}{str(r.get('name'))[:16]:<17} -> {keys}")

    if not args.apply:
        print("\nDry-run. Re-run with --apply."); return 0

    secret = _secret()
    ok = fail = 0
    for rid, name, p in plan:
        body = {k: v for k, v in p.items() if not k.startswith("_")}
        try:
            client._patch(f"robots/robots/{rid}/", body)
        except Exception as e:
            fail += 1; print(f"  FAIL {rid}: {str(e)[:80]}", file=sys.stderr); continue
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
