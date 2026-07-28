"""Purge FANUC (189) shared junk images and re-source real photos from the series pages.

THE DEFECT (2026-07-16 audit): 111 robots carried only 83 DISTINCT images, and the most
reused were corporate marketing art, not robots — one capability infographic on **75**
robots, a "Reliability/Efficiency/Flexibility" triangle on 42, FIELD architecture
schematics on 42+33, a Japanese CSR materiality matrix on 8, a "BOT CON" banner on 5.
299 junk attachments over 67+ robots. URL-based dedupe cannot see it: each junk image was
copied to its own per-robot CDN key, so only the CONTENT HASH exposes the reuse.

THE FIX: per robot, rebuild the gallery as [genuine existing photos] + [real FANUC series
photos] and PATCH `images` — the DRF serializer does `instance.photos.all().delete()` then
recreates, so the junk is purged in the same call. Series photos come from
`fanuc_recon.py` (fanucamerica.com series pages, cdn.craft.cloud), each visually verified
as a real FANUC robot of that series.

SAFETY:
  - Only the 8 audited junk hashes are dropped; anything else on the robot is KEPT.
  - The serializer ignores an EMPTY images list, so a robot cannot be purged to zero —
    if we cannot offer a replacement it is skipped and reported, never left blank.
  - Series photos are family-level (same trade accepted for KUKA): shared across a
    series, but a real robot beats a marketing triangle.

Usage:
  python fix_fanuc_photos.py             # dry-run
  python fix_fanuc_photos.py --ids 1739  # single test
  python fix_fanuc_photos.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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

import requests

from api_client import ResearchApiClient

COMPANY_ID = 189
RECON = _RESEARCH_DIR / "staging" / "reports" / "fanuc-recon.json"
MAX_IMAGES = 6

# Content hashes (sha256[:12]) of the shared junk — each visually identified.
JUNK = {
    "873e38012bda": "capability infographic (x75)",
    "dd32c042ffb9": "generic machine-tending cell (x59)",
    "6ef0cfb335cd": "Reliability/Efficiency/Flexibility marketing triangle (x42)",
    "ac4ecec4fc5c": "FIELD system architecture schematic (x42)",
    "2f3b5a434a0b": "FANUC Robot marketing triangle (x35)",
    "d0e6528d5401": "FIELD system architecture schematic (x33)",
    "e75c5706db6c": "CSR materiality matrix chart (x8)",
    "cc858fcdfb67": "BOT CON conference banner (x5)",
}


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")


def _secret() -> str:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if s:
        return s
    env = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def _copy_media(rid: int, secret: str, *, force: bool = False) -> str:
    # `force=1` re-copies an external hero even when s3_image is already set — the only
    # way to overwrite a stale junk hero. Requires the 2026-07-16 server fix to
    # copy_media (robots/background.py + api_copy_media) to be DEPLOYED; against older
    # prod the param is ignored and the owned-CDN hero still can't be refreshed.
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    if force:
        url += "?force=1"
    try:
        r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
        return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return f"ERR {str(e)[:40]}"


def series_for(slug: str, recon: dict[str, Any]) -> str | None:
    """Map a robot's URL slug to the series key that owns its photos.

    FANUC robot URLs are PER-MODEL (`m-710ic-20m`, `m-900ib-280`, `lr-mate-200id7h`)
    while the photos are keyed by SERIES (`m-710`, `m-900`, `lr-mate`). Longest-prefix
    match, so `m-2000ia1200` picks `m-2000` and never `m-20` / `m-2`.
    """
    slug = (slug or "").lower()
    if slug in recon and recon.get(slug):
        return slug
    best = None
    for key in sorted((k for k in recon if recon.get(k)), key=len, reverse=True):
        if slug.startswith(key):
            best = key
            break
    return best


def photo_urls(r: dict[str, Any]) -> list[str]:
    urls = []
    p = r.get("s3_image") or r.get("image")
    if p:
        urls.append(p)
    for x in (r.get("photos") or r.get("images") or []):
        u = (x.get("s3_image") or x.get("url")) if isinstance(x, dict) else x
        if u and u not in urls:
            urls.append(u)
    return urls


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge FANUC junk images + re-source series photos")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    if not RECON.is_file():
        print(f"ERROR: {RECON} missing — run fanuc_recon.py first", file=sys.stderr); return 1
    recon = json.loads(RECON.read_text(encoding="utf-8"))

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID); break
        except Exception as e:
            print(f"list retry {a}: {str(e)[:60]}", file=sys.stderr); time.sleep(5)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr); return 1

    S = requests.Session()
    S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    cache: dict[str, str | None] = {}

    def sha(u: str) -> str | None:
        if u in cache:
            return cache[u]
        try:
            r = S.get(u, timeout=20)
            h = (hashlib.sha256(r.content).hexdigest()[:12]
                 if r.ok and r.headers.get("Content-Type", "").startswith("image") else None)
        except Exception:
            h = None
        cache[u] = h
        return h

    pend = [r for r in robots if str(r.get("status") or "").lower() == "pending_review"]
    if args.ids:
        pend = [r for r in pend if int(r["id"]) in set(args.ids)]

    plan, skipped = [], []
    for r in sorted(pend, key=lambda x: x["id"]):
        rid = int(r["id"])
        slug = (r.get("url") or "").rstrip("/").split("/")[-1]
        skey = series_for(slug, recon)
        series_imgs = [c["url"] for c in (recon.get(skey) or []) if c.get("url")] if skey else []
        cur = photo_urls(r)
        good, junk_n = [], 0
        for u in cur:
            h = sha(u)
            if h in JUNK:
                junk_n += 1
            elif h:
                good.append(u)
        if junk_n == 0:
            continue  # nothing to purge
        # EXTERNAL SERIES PHOTO MUST COME FIRST. The serializer sets
        # `instance.image = images[0]`, and copy-media FAIL-CLOSES (HTTP 500) when the
        # hero is an already-owned cdn.robotaigeek.com URL — so an owned-first order
        # leaves the junk hero in place with a stale s3_image (observed on 63 robots).
        # An external craft.cloud hero is downloadable, so copy-media refreshes s3_image.
        new = list(dict.fromkeys(series_imgs + good))[:MAX_IMAGES]
        if not new:
            skipped.append({"id": rid, "name": r["name"], "why": f"all {junk_n} photos junk, no series render ({slug})"})
            continue
        plan.append({"id": rid, "name": r["name"], "slug": slug, "series": skey, "junk": junk_n,
                     "kept": len(good), "added": len([x for x in new if x not in good]), "images": new})
        print(f"  {rid:<6}{r['name'][:26]:<27} junk-{junk_n} keep-{len(good)} "
              f"+series-{len(new)-len(good)} [{slug} -> {skey or 'NO SERIES'}]")

    print(f"\nto fix: {len(plan)} | cannot fix (would purge to zero): {len(skipped)}")
    for s in skipped[:12]:
        print(f"   SKIP {s['id']} {s['name'][:28]}: {s['why']}")
    preview = _RESEARCH_DIR / "staging" / "reports" / "fanuc-photos-preview.json"
    preview.write_text(json.dumps({"plan": plan, "skipped": skipped}, indent=2, ensure_ascii=False), encoding="utf-8")
    if not plan:
        print("Nothing to do."); return 0
    if not args.apply:
        print(f"\nPreview: {preview}. Re-run with --apply (or --ids N to test one)."); return 0

    secret = _secret()
    if not secret:
        print("ERROR: INTERNAL_API_SECRET missing", file=sys.stderr); return 1

    ok = fail = cm_warn = 0
    for p in plan:
        rid = p["id"]
        try:
            client._patch(f"robots/robots/{rid}/", {"images": p["images"]})
        except Exception as e:
            fail += 1
            print(f"  FAIL {rid}: {str(e)[:70]}", file=sys.stderr)
            continue
        # force=1: the gallery is rebuilt external-photo-first, so images[0] (and thus
        # Robot.image) is an EXTERNAL craft.cloud url. Without force, copy-media skips the
        # hero whenever s3_image is already set — which is exactly the stale-junk-hero case
        # we are repairing. With the deployed copy-media fix, force refreshes s3_image from
        # the external hero. (Still counts owned-CDN gallery keeps as skipped, not failed.)
        cm = _copy_media(rid, secret, force=True)
        if cm != "ok":
            cm_warn += 1
        ok += 1
        print(f"  ok {rid} {p['name']}: purged {p['junk']}, now {len(p['images'])} imgs"
              f"{'' if cm == 'ok' else f' (copy_media={cm} — expected for owned-CDN keeps)'}")
        time.sleep(0.2)

    out = {"ok": fail == 0, "fixed": ok, "failed": fail,
           "copy_media_warnings": cm_warn, "skipped": len(skipped)}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "fanuc-photos-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
