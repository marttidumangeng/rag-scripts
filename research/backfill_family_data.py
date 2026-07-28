"""Backfill family_name / variant_label from a company's own catalogue.

Nothing in discovery or enrichment ever populated the family fields, so the
metadata has been arriving only via hand-written retrofit scripts. This applies
the same inference in one pass per company.

Writes through the bulk-import path rather than a plain PATCH so the server runs
`robots.family.resolve_import_family_metadata`, which derives
``family_key = {company_slug}:{slug(family_name)}`` and enforces
`assert_family_key_company_consistent`. Setting `family_name` via a bare PATCH
would leave `family_key` blank, and the key is what actually groups siblings.

  python -u backfill_family_data.py --company-id 107            # dry-run
  python -u backfill_family_data.py --company-id 107 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from family_infer import describe, infer_families  # noqa: E402
from import_staging import import_staging, resolve_created_by_id  # noqa: E402
from robot_auto_research import _robot_api_to_staged  # noqa: E402
from schema import StagedRobot  # noqa: E402
from slug_utils import resolve_company_slug  # noqa: E402

# Live records are never auto-edited; family metadata is not urgent enough to be
# the exception that breaks that rule.
EDITABLE_STATUSES = {"draft", "pending_review", "rejected"}


def _p(*a):
    try:
        print(*a, flush=True)
    except UnicodeEncodeError:
        print(" ".join(str(x) for x in a).encode("ascii", "replace").decode(), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-id", type=int, required=True)
    ap.add_argument("--apply", action="store_true", help="WRITE (default: dry-run)")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    co = client.get_company(args.company_id)
    name = str(co.get("name") or "")
    slug = resolve_company_slug(name, co.get("slug"))
    _p(f"=== Family backfill — {name} (id={args.company_id}) {'APPLY' if args.apply else 'DRY-RUN'} ===")

    # Infer from the WHOLE catalogue so already-approved siblings still count.
    allr = client.list_robots_for_company(args.company_id)
    inferred = infer_families(allr)
    _p(f"catalogue={len(allr)}  family assigned={len(inferred)}\n")
    _p(describe(allr, inferred))

    targets = []
    skipped_live, already = [], []
    for r in allr:
        rid = int(r.get("id") or 0)
        hit = inferred.get(rid)
        if not hit:
            continue
        if (r.get("family_name") or "").strip():
            already.append(rid)
            continue
        if str(r.get("status") or "").lower() not in EDITABLE_STATUSES:
            skipped_live.append(rid)
            continue
        targets.append((r, hit))

    _p(f"\nto write: {len(targets)}   already set: {len(already)}   skipped (live): {len(skipped_live)}")
    if not targets:
        _p("nothing to do")
        return 0

    staging_dir = _RESEARCH_DIR / "staging" / "robots" / slug / "family"
    staging_dir.mkdir(parents=True, exist_ok=True)
    created_by = resolve_created_by_id(None)
    written = failed = 0
    for robot, hit in targets:
        rid = int(robot["id"])
        base = _robot_api_to_staged(robot, slug, name)
        payload = base.to_dict()
        payload["family_name"] = hit["family_name"]
        payload["variant_label"] = hit["variant_label"]
        staged = StagedRobot.from_dict(payload)
        _p(f"  {rid:>5} {str(robot.get('name'))[:24]:24} -> family={hit['family_name']:<10} variant={hit['variant_label'] or '(base)'}")
        if not args.apply:
            continue
        path = staging_dir / f"robot_{rid}.json"
        path.write_text(json.dumps([staged.to_dict()], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        res = import_staging(
            path, client=client, patch=True, force_overwrite=True,
            status=str(robot.get("status") or "pending_review"),
            batch_size=1, skip_company_update=True, dry_run=False, created_by_id=created_by,
        )
        if res.get("ok"):
            written += 1
        else:
            failed += 1
            _p(f"        import failed: {str(res)[:160]}")

    if args.apply:
        _p(f"\nwritten={written} failed={failed}")
        # Confirm the server actually derived the key — a family_name without a
        # family_key does not group anything.
        ok = 0
        for robot, _hit in targets[:5]:
            fresh = client._get(f"robots/robots/{robot['id']}/")
            if (fresh.get("family_name") or "").strip():
                ok += 1
                _p(f"  verify {robot['id']}: family_name={fresh.get('family_name')!r} "
                   f"family_key={fresh.get('family_key')!r} variant={fresh.get('variant_label')!r}")
        _p(f"verified {ok}/{min(5, len(targets))} sampled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
