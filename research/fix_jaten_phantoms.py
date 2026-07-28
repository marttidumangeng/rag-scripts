"""Retire the 5 phantom Jaten SDM-*-335-MG0 records (company 1461).

Evidence (2026-07-16): these 5 model names return ZERO results anywhere —
absent from the live jaten-robotics.com catalog (267 cards), absent from the CN
site jtrobots.com (which uses different SKUs, e.g. SDM1000-D287-MGO), and zero
exact-match web hits. Their only stored image is one shared URL that 404s
(146 B of HTML). Their claimed chassis (L1200x800x300) does not match the real
335-MG0 platform (R2SDM1500-335-MG0 = L1190x860x280), so they are almost certainly
artefacts of the reassigned-CRM-detail-id import flagged on 2026-07-14.

Action: back up each full record to JSON, then set status=rejected (the platform's
reversible removal mechanism — Robot has no soft-delete flag). NOT a hard delete:
the rows stay recoverable. Run with --hard-delete only on explicit instruction.

Usage:
  python fix_jaten_phantoms.py                 # dry-run
  python fix_jaten_phantoms.py --apply         # backup + status=rejected
  python fix_jaten_phantoms.py --apply --hard-delete   # irreversible row removal
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

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

COMPANY_ID = 1461
PHANTOM_IDS = [2912, 5186, 5187, 5188, 5189]
DEAD_IMAGE = "1705307770172342.png"
NOTE = ("Retired 2026-07-16: model name has zero hits on jaten-robotics.com (delisted), "
        "jtrobots.com (CN, different SKUs) or the open web; sole image 404s; claimed "
        "chassis L1200x800x300 conflicts with the real 335-MG0 platform "
        "(R2SDM1500-335-MG0 = L1190x860x280). Probable artefact of the reassigned "
        "CRM detail-id import.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Retire phantom Jaten SDM-335-MG0 records")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--hard-delete", action="store_true",
                    help="IRREVERSIBLE: DELETE the rows instead of status=rejected")
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

    targets = []
    for rid in PHANTOM_IDS:
        r = by_id.get(rid)
        if not r:
            print(f"SKIP {rid}: not found (already removed?)"); continue
        # Safety: only touch pending_review, and only if the dead image is still there.
        status = str(r.get("status") or "").lower()
        img = (r.get("s3_image") or r.get("image") or "")
        if status != "pending_review":
            print(f"SKIP {rid} {r['name']}: status={status} (only pending_review)", file=sys.stderr)
            continue
        if DEAD_IMAGE not in img:
            print(f"SKIP {rid} {r['name']}: image no longer the known-dead URL ({img[:60]}) "
                  f"— re-verify before retiring", file=sys.stderr)
            continue
        targets.append(r)
        print(f"  {rid} {r['name']}: status={status} image={img[:62]}")

    if not targets:
        print("Nothing to retire.")
        return 0

    backup = _RESEARCH_DIR / "staging" / "reports" / "jaten-phantoms-backup.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps(targets, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"\nFull records backed up -> {backup}")
    mode = "HARD DELETE (irreversible)" if args.hard_delete else "status=rejected (reversible)"
    print(f"Targets: {len(targets)} | mode: {mode}")
    if not args.apply:
        print("Dry-run. Re-run with --apply")
        return 0

    ok = fail = 0
    for r in targets:
        rid = int(r["id"])
        try:
            if args.hard_delete:
                resp = client._session.delete(client._url(f"robots/robots/{rid}/"), timeout=client.timeout)
                resp.raise_for_status()
                print(f"  DELETED {rid} {r['name']} -> HTTP {resp.status_code}")
            else:
                notes = (r.get("notes") or "").strip()
                merged = f"{notes}\n{NOTE}".strip() if NOTE not in notes else notes
                client._patch(f"robots/robots/{rid}/", {"status": "rejected", "notes": merged})
                print(f"  REJECTED {rid} {r['name']}")
            ok += 1
        except Exception as exc:
            fail += 1
            print(f"  FAIL {rid}: {str(exc)[:90]}", file=sys.stderr)

    out = {"ok": fail == 0, "mode": mode, "retired": ok, "failed": fail, "backup": str(backup)}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "jaten-phantoms-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
