"""Attach official KUKA family product renders to the 15 robots that have NO image at all.

Decision (Martti, 2026-07-16): "attach family renders to the 15". KUKA publishes
renders per FAMILY, not per variant, so same-family variants share one render — an
accepted trade for going from *no photo* to a correct-family OEM render.

Every render below was downloaded and VISUALLY verified. Rejected during QA:
  - kr-quantec `-10 %` marketing graphic (text overlay)
  - kr-quantec 3-arm family lineup / a steel-truss photo (not a robot)
  - kr-scara page's sibling cross-nav images (an orange 6-axis arm, a delta, an
    AGILUS — the family page embeds neighbouring families' art; the Comau trap)
  - lbr-med Sunrise.OS laptop screenshot and a people-at-a-desk shot

Mechanism: bulk-import patch_existing + replace_media (force_patch_keys={url,image}
→ overwrites `image` only, preserves description/features/specs) then copy-media +
CDN verify. These 15 have image="" so nothing is destroyed.

Usage:
  python fix_kuka_photos.py             # dry-run
  python fix_kuka_photos.py --ids 4091  # single test
  python fix_kuka_photos.py --apply
"""

from __future__ import annotations

import argparse
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
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

COMPANY_ID = 1396
COMPANY_SLUG = "kuka"
K = "https://www.kuka.com/-/media/kuka-corporate/images"

# Visually verified official KUKA family renders.
SCARA = (f"{K}/products/robots/kr-scara/kuka-kr-scara-industrial-robot-with-4-axes.jpg"
         "?rev=b240d1b685f440148cce418e2ef12e7a&hash=8F372E68B0D61F74544842451D2801C4")
NANO = f"{K}/products/robots/cta-images/kr-cybertech-nano.png?rev=-1"
QUANTEC = f"{K}/products/robots/cta-images/kr-quantec.png?rev=-1"
DELTA = (f"{K}/products/robots/kr-delta/delta-secondary-packaging.jpg"
         "?rev=-1&hash=A6516EB8C6AA66EF1965520B03AF30AE")
LBRMED = f"{K}/industries/healthcare/lbr-med/lbr-med-feature-cell.jpg"

# robot id -> (render, family note for research_notes)
TARGETS: dict[int, tuple[str, str]] = {
    # Z-series SCARA — clean white 4-axis SCARA render
    4091: (SCARA, "KR SCARA family render"),
    4092: (SCARA, "KR SCARA family render"),
    4093: (SCARA, "KR SCARA family render"),
    4094: (SCARA, "KR SCARA family render"),
    4095: (SCARA, "KR SCARA family render"),
    # KR CYBERTECH nano — orange 6-axis arm on black
    4078: (NANO, "KR CYBERTECH nano family render"),
    4079: (NANO, "KR CYBERTECH nano family render"),
    4080: (NANO, "KR CYBERTECH nano family render"),
    4081: (NANO, "KR CYBERTECH nano family render"),
    # QUANTEC "K" (shelf/ceiling-mounted) variants — QUANTEC family render
    4085: (QUANTEC, "KR QUANTEC family render (K = shelf-mounted variant)"),
    4086: (QUANTEC, "KR QUANTEC family render (K = shelf-mounted variant)"),
    4087: (QUANTEC, "KR QUANTEC family render (K = shelf-mounted variant)"),
    # Delta
    4090: (DELTA, "KR DELTA family image (delta in packaging cell)"),
    # LBR Med — the only KUKA imagery showing the LBR Med itself
    4076: (LBRMED, "LBR Med family image"),
    4077: (LBRMED, "LBR Med family image"),
}
NOTE = ("[media] 2026-07-16: official KUKA {fam}; KUKA publishes renders per FAMILY, "
        "not per variant, so same-family variants share it (was: no image at all). "
        "Visually verified; rejected KUKA's -10% marketing graphic, family lineups and "
        "sibling cross-nav art.")


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


def _copy_media(rid: int, secret: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    try:
        r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
        return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return f"ERR {str(e)[:40]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Attach KUKA family renders to the 15 no-photo robots")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--created-by-id", type=int, default=1)
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
    by_id = {int(r["id"]): r for r in robots}

    ids = args.ids or list(TARGETS)
    plan = []
    for rid in ids:
        r = by_id.get(rid)
        if not r or rid not in TARGETS:
            print(f"SKIP {rid}: not a target", file=sys.stderr); continue
        if str(r.get("status") or "").lower() != "pending_review":
            print(f"SKIP {rid}: status={r.get('status')}", file=sys.stderr); continue
        cur = (r.get("s3_image") or r.get("image") or "").strip()
        if cur:
            print(f"SKIP {rid} {r['name']}: already has an image ({cur[:50]}) — not overwriting")
            continue
        render, fam = TARGETS[rid]
        plan.append({"id": rid, "name": r["name"], "render": render, "fam": fam})
        print(f"  {rid:<6}{r['name'][:26]:<27} <- {fam}")

    if not plan:
        print("Nothing to do."); return 0
    print(f"\nTargets: {len(plan)}")
    if not args.apply:
        print("Dry-run. Re-run with --apply (or --ids N to test one)."); return 0

    secret = _secret()
    if not secret:
        print("ERROR: INTERNAL_API_SECRET missing (needed for copy-media)", file=sys.stderr); return 1

    results, all_ok = [], True
    for p in plan:
        rid = p["id"]
        row = staging_dict_to_bulk_import_row({
            "id": rid, "name": p["name"], "company_slug": COMPANY_SLUG,
            "image": p["render"], "images": [{"url": p["render"]}],
            "research_notes": NOTE.format(fam=p["fam"]), "source_locale": "en",
        })
        row["id"] = rid
        try:
            res = client.bulk_import_robots(
                [row], update_existing=True, patch_existing=True, replace_media=True,
                status="pending_review", skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id))
            img = "updated" if int(res.get("updated_count") or 0) else str(res)[:60]
            if int(res.get("created_count") or 0):
                all_ok = False; img = f"CREATED?! {res}"
        except Exception as e:
            all_ok = False; img = f"FAIL {str(e)[:50]}"
        cm = _copy_media(rid, secret)
        if cm != "ok" or img != "updated":
            all_ok = False
        results.append({"id": rid, "name": p["name"], "image": img, "copy_media": cm})
        print(f"  {rid} {p['name']}: image={img} copy_media={cm}")
        time.sleep(0.2)

    out = {"ok": all_ok, "count": len(results), "results": results}
    (_RESEARCH_DIR / "staging" / "reports" / "kuka-photos-result.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": all_ok, "count": len(results)}, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
