"""Record the Jaten OEM Product Specification PDF URLs on the robots themselves.

Why: the spec PDF's page 1 carries a higher-res product photo that is NOT published
as a standalone image, so it cannot be attached via the research API (DRF `images`
takes URL strings only; the admin photos endpoint is session-auth). A human admin
CAN upload it from the admin UI — but only if they know the URL. Previously these
URLs lived only in the repo changelog, which is useless to someone working the queue.

This writes, per robot:
  - information_source_urls: OEM PDP + Product Specification PDF (upsert by url, never deletes)
  - notes: an appended, actionable line naming the PDF and what to do with it

For the 4 delisted models (no live PDP/PDF) it instead records that fact, so nobody
re-runs the same dead hunt.

Idempotent: notes are only appended when the marker is absent.

Usage:
  python fix_jaten_pdf_notes.py            # dry-run
  python fix_jaten_pdf_notes.py --apply
"""

from __future__ import annotations

import argparse
import json
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

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

COMPANY_ID = 1461
COMPANY_SLUG = "jaten-robot"
MARKER = "[media] OEM spec PDF"
MARKER_DELISTED = "[media] delisted"

_D = "https://jaten-robotics.com/index/Agv/detail.html?id="
_U = "https://jaten-robotics.com/upload/"

# Verified 2026-07-16: each URL fetched HTTP 200, Content-Type application/pdf, %PDF magic.
LIVE_PDF: dict[int, dict[str, str]] = {
    2911: {"pdp": _D + "1001025", "pdf": _U + "20240711/86d8f414e343b8fa7e91118b2749cc4e.pdf"},
    5185: {"pdp": _D + "1001026", "pdf": _U + "20240711/22bf9a8f7afc70214088674776c4eab4.pdf"},
    5190: {"pdp": _D + "1000003", "pdf": _U + "20230511/23f6cbc7c5921834a5f164e02ddf4c3a.pdf"},
    5191: {"pdp": _D + "1000001", "pdf": _U + "20231006/d7ca58b5c0f5da23b33484b78a575fd9.pdf"},
    # DB record is "AGV-31-MC500"; live card is the -ZER variant (id=1000292).
    2916: {"pdp": _D + "1000292", "pdf": _U + "20230401/58fa0bca471f0cbd6b1bf943ae42bdc8.pdf"},
}

# Delisted from the live 267-card catalog -> no PDP, no datasheet.
DELISTED: dict[int, str] = {
    2914: "MN100-164",
    2918: "SDM2000-D228",
    5192: "SDM1000-D228",
    5193: "SDM3000-D228",
}
# 3 of the 4 share SDM500-D228's hero (same D228 chassis, L990xW776xH305).
D228_SHARED = {2918, 5192, 5193}


def live_note(pdf: str) -> str:
    return (f"{MARKER}: {pdf} — page 1 has a higher-res OEM product photo (larger than the "
            f"500x374 site image) that Jaten does NOT publish as a standalone image URL, so it "
            f"cannot be attached via the research API (images accept URLs only). To reach the "
            f"4-photo standard an admin must download it from this PDF and upload it manually. "
            f"Pages 3+ are dimension line-drawings — not valid heroes. Jaten's PDP itself carries "
            f"only ONE product image per model (Playwright-verified).")


def delisted_note(name: str, shared: bool) -> str:
    base = (f"{MARKER_DELISTED}: {name} is not in Jaten's live catalog (267 cards) and has no OEM "
            f"PDP or Product Specification PDF — no additional photos are obtainable from the "
            f"manufacturer; do not re-hunt.")
    if shared:
        base += (" Hero is shared with platform sibling SDM500-D228 (same D228 chassis, "
                 "L990xW776xH305) — expected, not a bug.")
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Record Jaten spec-PDF URLs on the robots")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(15):
        try:
            robots = client.list_robots_for_company(COMPANY_ID); break
        except Exception as e:
            print(f"list retry {a}: {str(e)[:60]}", file=sys.stderr); time.sleep(6)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr); return 1
    by_id = {int(r["id"]): r for r in robots}

    plan: list[dict[str, Any]] = []
    for rid, urls in LIVE_PDF.items():
        r = by_id.get(rid)
        if not r or str(r.get("status") or "").lower() != "pending_review":
            print(f"SKIP {rid}: missing/not pending_review", file=sys.stderr); continue
        notes = (r.get("notes") or "").strip()
        plan.append({"id": rid, "name": r["name"], "kind": "live",
                     "sources": [urls["pdp"], urls["pdf"]],
                     "note": live_note(urls["pdf"]),
                     "note_needed": MARKER not in notes, "notes_cur": notes})
    for rid, name in DELISTED.items():
        r = by_id.get(rid)
        if not r or str(r.get("status") or "").lower() != "pending_review":
            print(f"SKIP {rid}: missing/not pending_review", file=sys.stderr); continue
        notes = (r.get("notes") or "").strip()
        plan.append({"id": rid, "name": r["name"], "kind": "delisted",
                     "sources": [],
                     "note": delisted_note(name, rid in D228_SHARED),
                     "note_needed": MARKER_DELISTED not in notes, "notes_cur": notes})

    for p in plan:
        print(f"  {p['id']:<5} {p['name'][:20]:<21} {p['kind']:<9} "
              f"sources+{len(p['sources'])} note={'APPEND' if p['note_needed'] else 'already'}")
    print(f"\nTargets: {len(plan)} (live w/ PDF: {sum(1 for p in plan if p['kind']=='live')}, "
          f"delisted: {sum(1 for p in plan if p['kind']=='delisted')})")
    if not args.apply:
        print("Dry-run. Re-run with --apply")
        return 0

    ok = fail = 0
    for p in plan:
        rid = p["id"]
        # 1) structured sources. NOTE: bulk-import patch mode SKIPS sources entirely when the
        # robot already has any -- `if info_urls and (not patch_existing or not has_sources or
        # replace_media)` is all-False -- and replace_media would DELETE the existing ones.
        # The DRF serializer's `information_source_urls` runs upsert_information_sources(),
        # which upserts by url and never deletes. That is the correct path here.
        if p["sources"]:
            try:
                client._patch(f"robots/robots/{rid}/", {"information_source_urls": p["sources"]})
            except Exception as exc:
                fail += 1
                print(f"  SOURCES FAIL {rid}: {str(exc)[:70]}", file=sys.stderr); continue
        # 2) notes append (patch mode never overwrites non-blank notes -> direct PATCH)
        if p["note_needed"]:
            merged = f"{p['notes_cur']}\n{p['note']}".strip() if p["notes_cur"] else p["note"]
            try:
                client._patch(f"robots/robots/{rid}/", {"notes": merged})
            except Exception as exc:
                fail += 1
                print(f"  NOTES FAIL {rid}: {str(exc)[:70]}", file=sys.stderr); continue
        ok += 1
        print(f"  ok {rid} {p['name']}: sources+{len(p['sources'])} "
              f"note={'appended' if p['note_needed'] else 'already'}")

    out = {"ok": fail == 0, "updated": ok, "failed": fail}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "jaten-pdf-notes-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
