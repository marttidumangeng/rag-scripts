#!/usr/bin/env python3
"""Merge Yaskawa (company 772) duplicate pairs.

Policy (decided 2026-07-16):
  * KEEPER = the richer "Motoman <MODEL> Robot" record (features, specs, more
    videos, grounded/cited release years, model-specific URLs).
  * LOSER  = the short-name "<MODEL>" record (uncited legacy years, generic
    yaskawa-global case-study gallery thumbnails — nothing worth migrating).
  * Rename the keeper to the clean short model name.
  * Release year: keep the keeper's value untouched (a cited year, or None when
    grounding found no evidence). The loser's uncited year is dropped by deletion.

Ordering: DELETE the loser first, THEN rename the keeper — the unique constraint
(company_ref, dedupe_name_key) would otherwise reject the rename while the short
record still holds the "<model>" key.

Safety: at apply time every record is re-fetched live and must still be
status=pending_review; anything else is skipped (never touch Approved/Published).

Usage:
  python _yaskawa_merge.py            # build/print staged plan (read-only)
  python _yaskawa_merge.py --apply    # execute (delete loser, rename keeper)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

COMPANY_ID = 772
DUMP = _DIR / "staging" / "reports" / "yaskawa-dedupe-recon.json"
PLAN = _DIR / "staging" / "reports" / "yaskawa-merge-plan.json"


def norm_model(name: str) -> str:
    n = re.sub(r'(?i)^motoman\s+', '', name.strip())
    n = re.sub(r'(?i)\s+robot$', '', n)
    return re.sub(r'[^a-z0-9]', '', n.lower())


def is_motoman_named(name: str) -> bool:
    return bool(re.match(r'(?i)^motoman\s+.+\brobot$', name.strip()))


def build_plan(robots: list[dict]) -> dict:
    motoman: dict[str, list[dict]] = {}
    short: dict[str, list[dict]] = {}
    for r in robots:
        (motoman if is_motoman_named(r.get("name", "")) else short).setdefault(
            norm_model(r.get("name", "")), []
        ).append(r)

    merges = []
    skipped_multi = []
    for k in sorted(set(motoman) & set(short)):
        m, s = motoman[k], short[k]
        if len(m) != 1 or len(s) != 1:
            skipped_multi.append({"key": k, "motoman_ids": [x["id"] for x in m],
                                  "short_ids": [x["id"] for x in s]})
            continue
        keeper, loser = m[0], s[0]
        merges.append({
            "key": k,
            "keeper_id": keeper["id"],
            "keeper_old_name": keeper["name"],
            "new_name": loser["name"],           # clean short model name
            "keeper_release_year": keeper.get("release_year"),
            "loser_id": loser["id"],
            "loser_name": loser["name"],
            "loser_dropped_year": loser.get("release_year"),
            "year_action": ("keep_cited" if keeper.get("release_year") is not None
                            else "null_uncited"),
        })
    return {"company_id": COMPANY_ID, "merges": merges, "skipped_multi": skipped_multi}


def print_plan(plan: dict) -> None:
    merges = plan["merges"]
    keep_cited = [m for m in merges if m["year_action"] == "keep_cited"]
    null_unc = [m for m in merges if m["year_action"] == "null_uncited"]
    print(f"MERGE PLAN — company {plan['company_id']}: {len(merges)} pairs")
    print(f"  release_year: keep cited={len(keep_cited)}  null uncited (drop loser year)={len(null_unc)}")
    if plan["skipped_multi"]:
        print(f"  SKIPPED (non 1:1): {plan['skipped_multi']}")
    print("-" * 100)
    print(f"{'model':10} {'keeper':6} -> rename            {'loser':6} (delete)   year")
    for m in merges:
        yr = m["keeper_release_year"]
        ya = "cited" if m["year_action"] == "keep_cited" else f"NULL (drop {m['loser_dropped_year']})"
        print(f"{m['key']:10} {m['keeper_id']:<6} '{m['keeper_old_name']}' -> '{m['new_name']}'   "
              f"del {m['loser_id']:<6}  yr={yr} [{ya}]")


def apply(plan: dict, client: ResearchApiClient) -> int:
    ok = err = skipped = 0
    for m in plan["merges"]:
        keeper_id, loser_id = m["keeper_id"], m["loser_id"]
        # Re-fetch live; both must still be pending_review.
        try:
            keeper = client._get(f"robots/robots/{keeper_id}/")
            loser = client._get(f"robots/robots/{loser_id}/")
        except Exception as exc:
            print(f"  [{m['key']}] FETCH ERROR: {exc}"); err += 1; continue
        if keeper.get("status") != "pending_review" or loser.get("status") != "pending_review":
            print(f"  [{m['key']}] SKIP — status keeper={keeper.get('status')} loser={loser.get('status')}")
            skipped += 1; continue
        if norm_model(keeper.get("name", "")) != m["key"] or loser.get("id") != loser_id:
            print(f"  [{m['key']}] SKIP — identity drift"); skipped += 1; continue
        # 1) delete loser, then 2) rename keeper
        try:
            resp = client._session.delete(client._url(f"robots/robots/{loser_id}/"), timeout=client.timeout)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  [{m['key']}] DELETE {loser_id} ERROR: {exc}"); err += 1; continue
        try:
            client._patch(f"robots/robots/{keeper_id}/", {"name": m["new_name"]})
        except Exception as exc:
            print(f"  [{m['key']}] RENAME {keeper_id} ERROR after delete: {exc}"); err += 1; continue
        print(f"  [{m['key']}] deleted {loser_id}; renamed {keeper_id} -> '{m['new_name']}'")
        ok += 1
    print(f"\nApplied: {ok} merged | {skipped} skipped | {err} errors")
    return 1 if err else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--live", action="store_true", help="re-fetch robots instead of using dump")
    args = ap.parse_args()

    client = ResearchApiClient()
    if args.live or args.apply:
        robots = client.list_robots_for_company(COMPANY_ID, page_size=50)
    else:
        robots = json.loads(DUMP.read_text(encoding="utf-8"))

    plan = build_plan(robots)
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print_plan(plan)
    print(f"\nPlan written -> {PLAN}")

    if args.apply:
        print("\n=== APPLYING ===")
        return apply(plan, client)
    print("\n(dry-run — rerun with --apply to execute)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
