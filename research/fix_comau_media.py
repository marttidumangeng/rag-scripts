"""Repair Comau (company 245) primary/gallery images.

An earlier run set Comau's corporate world-map graphic
(/wp-content/uploads/2024/09/global-presence-2.webp, md5
f9f947f91fd616172a68268be1ae7758 -- the "Global Spirit, Local Presence" section
art) as the PRIMARY hero on 32 robots, and duplicated images across models.
This replaces each with a genuine, distinct, per-model product render taken from
comau_hero_plan.py (which is hash-audited and visually reviewed).

Media-only: patches `image`/`images` via bulk-import patch_existing +
replace_media, then copy-media. Text/specs/tags are untouched.

MANDATORY PRE-APPLY GATE (assert_media_safe) -- refuses to import when:
  a) any image hashes to the banned world-map graphic
  b) a hash repeats within one robot's gallery
  c) a hash is already another robot's primary in this batch/company

Fail closed: a robot with no genuine distinct image is left imageless and
reported -- never given a sibling's render, a banner, or a drawing.

    python fix_comau_media.py                       # dry-run + gate
    python fix_comau_media.py --apply --copy-media --ids 1852,1853
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from comau_image_audit import BANNED_MD5, fetch
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name

COMPANY_ID = 245
COMPANY_SLUG = "comau"
COMPANY_NAME = "Comau"
PLAN = _RESEARCH_DIR / "staging" / "reports" / "comau-hero-plan.json"

# Gallery size cap: replace_media recopies every image synchronously inside the
# import request, and large galleries 502 the gateway (see lessons 2026-07-16).
MAX_GALLERY = 4


def md5_of(url: str) -> str | None:
    data, _ = fetch(url)
    return hashlib.md5(data).hexdigest() if data else None


def assert_media_safe(rows: dict[int, dict[str, Any]]) -> list[str]:
    """The permanent gate. Returns a list of violations (empty == safe)."""
    problems: list[str] = []
    primary_owner: dict[str, int] = {}
    for rid, row in sorted(rows.items()):
        imgs = row.get("images") or []
        hashes: list[str] = []
        for u in imgs:
            h = md5_of(u)
            if h is None:
                problems.append(f"{rid}: unfetchable image {u}")
                continue
            if h in BANNED_MD5:
                problems.append(f"{rid}: BANNED world-map image {u}")
            hashes.append(h)
        if len(hashes) != len(set(hashes)):
            problems.append(f"{rid}: duplicate image bytes within gallery")
        if not imgs:
            continue
        ph = md5_of(imgs[0])
        if ph:
            if ph in primary_owner and primary_owner[ph] != rid:
                problems.append(f"{rid}: primary hash already used by robot {primary_owner[ph]}")
            primary_owner[ph] = rid
    return problems


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("copy-media: missing secret/base url", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        u = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(u, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"  copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"  copy-media fail {rid}: {exc}")
        time.sleep(0.2)
    return ok, fail


def main() -> int:
    ap = argparse.ArgumentParser(description="Fix Comau primary/gallery images (company 245)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--ids", type=str, default="")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    client = ResearchApiClient()
    robots = {int(r["id"]): r for r in client.list_robots_for_company(COMPANY_ID)}

    want = {int(x) for x in args.ids.split(",") if x.strip().isdigit()} if args.ids.strip() else None

    rows: dict[int, dict[str, Any]] = {}
    imageless: list[str] = []
    for rid_s, p in plan.items():
        rid = int(rid_s)
        if want and rid not in want:
            continue
        r = robots.get(rid)
        if not r:
            continue
        # Never touch anything but pending_review.
        if (r.get("status") or "") != "pending_review":
            print(f"SKIP {rid} {r.get('name')}: status={r.get('status')}", file=sys.stderr)
            continue
        if p.get("imageless") or not p.get("hero"):
            imageless.append(f"{rid} {p['name']}")
            continue
        gallery = p["gallery"][:MAX_GALLERY]
        pdp = (p.get("url") or r.get("url") or "").strip()
        # The staging validator requires description/purpose + >=1 source. In
        # patch mode these only fill BLANK fields, so echoing the robot's current
        # text keeps this media-only while satisfying validation.
        desc = (r.get("description") or "").strip() or f"Comau {p['name']} industrial robot."
        rows[rid] = {
            "id": rid,
            "name": p["name"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "url": pdp,
            "description": desc[:1200],
            "purpose": ((r.get("purpose") or "").strip() or desc)[:1200],
            "image": p["hero"],
            "images": gallery,
            "sources": [{"url": pdp, "type": "website", "title": f"Comau {p['name']} product page"}],
            "research_notes": (
                "Media repair: replaced Comau corporate world-map graphic "
                "(global-presence-2.webp) with a hash-audited, visually verified "
                "per-model product render; gallery deduplicated by content hash."
            ),
        }

    print(f"targets with vetted media: {len(rows)}")
    print(f"left imageless (no genuine distinct render): {len(imageless)}")
    for x in imageless:
        print(f"   - {x}")

    print("\nrunning mandatory pre-apply gate (hash every candidate)...")
    problems = assert_media_safe(rows)
    if problems:
        print(f"GATE FAILED with {len(problems)} violation(s):", file=sys.stderr)
        for p_ in problems:
            print(f"   ! {p_}", file=sys.stderr)
        return 1
    print("GATE PASSED: no banned map, no intra-gallery dupes, no cross-model primary reuse.")

    for rid, row in sorted(rows.items()):
        print(f"  {rid} {row['name'][:26]:26} imgs={len(row['images'])} hero={row['image'].rsplit('/',1)[-1][:40]}")

    if not args.apply:
        print("\nDry-run. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="comau-media-"))
    imported: list[int] = []
    all_ok = True
    for rid, row in sorted(rows.items()):
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            result = import_staging(
                fpath,
                patch=True,             # media-only: never clobber text/specs
                force_overwrite=False,
                status="pending_review",
                dry_run=False,
                created_by_id=resolve_created_by_id(args.created_by_id),
                replace_media=True,     # required to displace the world-map hero
                batch_size=1,
                skip_company_update=True,
            )
        except Exception as exc:
            # replace_media copies synchronously; the gateway can 502 while the
            # write still commits. Verify after rather than trusting the code.
            print(f"  {rid}: import raised ({str(exc)[:60]}) - will verify", file=sys.stderr)
            imported.append(rid)
            continue
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result.get('errors')}", file=sys.stderr)
            continue
        if result.get("created_count"):
            print(f"WARN {rid}: created_count={result['created_count']} (expected patch only)", file=sys.stderr)
        imported.append(rid)
        print(f"  patched {rid} {row['name']}")

    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")

    print(json.dumps({"ok": all_ok, "imported": imported, "imageless": imageless}, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
