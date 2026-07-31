"""Rebuild staging/gap_discovery/robots/{slug}/ from staged_import.json.

staged_import.json is the single source of truth after QA/review passes; the
per-company import dirs consumed by `cli.py import --dir` MUST be regenerated
from it, never edited independently. This script:

  1. Deletes robot dirs for companies no longer in staged_import.json.
  2. Rewrites every remaining company dir from scratch so robot files removed
     from the JSON disappear from the dirs too.
  3. Reports counts so the sync can be verified.

Run this after ANY change to staged_import.json (QA passes, manual review
edits, alias culls) and before any import.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent / "staging" / "gap_discovery"
STAGED = BASE / "staged_import.json"
ROBOTS_DIR = BASE / "robots"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "robot"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(STAGED.read_text(encoding="utf-8"))
    companies = {c["slug"] for c in data["companies"]}
    robots_by_co: dict[str, list[dict]] = {}
    for r in data["robots"]:
        robots_by_co.setdefault(r["company_slug"], []).append(r)

    existing = {d.name for d in ROBOTS_DIR.iterdir() if d.is_dir()} if ROBOTS_DIR.exists() else set()
    stale_dirs = sorted(existing - companies)
    valid_with_robots = {s for s in companies if robots_by_co.get(s)}
    empty_after_sync = sorted((existing & companies) - valid_with_robots)

    print(f"staged: {len(companies)} companies, {len(data['robots'])} robots "
          f"across {len(valid_with_robots)} companies")
    print(f"existing dirs: {len(existing)}")
    print(f"stale dirs to delete (company culled): {len(stale_dirs)}")
    print(f"dirs to delete (no robots remain): {len(empty_after_sync)}")
    print("stale sample:", stale_dirs[:10])

    if args.dry_run:
        # estimate file-level drift
        drift = 0
        for slug in sorted(valid_with_robots & existing):
            want = {slugify(r["name"]) + ".json" for r in robots_by_co[slug]}
            have = {f.name for f in (ROBOTS_DIR / slug).glob("*.json")}
            drift += len(have - want)
        print(f"junk robot files that would be removed from kept dirs: {drift}")
        return

    removed_files = 0
    for slug in stale_dirs + empty_after_sync:
        shutil.rmtree(ROBOTS_DIR / slug, ignore_errors=True)

    for slug in sorted(valid_with_robots):
        co_dir = ROBOTS_DIR / slug
        if co_dir.exists():
            removed_files += len(list(co_dir.glob("*.json")))
            shutil.rmtree(co_dir)
        co_dir.mkdir(parents=True, exist_ok=True)
        for r in robots_by_co[slug]:
            (co_dir / f"{slugify(r['name'])}.json").write_text(
                json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8",
            )

    final_dirs = [d for d in ROBOTS_DIR.iterdir() if d.is_dir()]
    final_files = sum(len(list(d.glob("*.json"))) for d in final_dirs)
    print(f"synced: {len(final_dirs)} dirs, {final_files} robot files "
          f"(JSON has {len(data['robots'])} robots)")
    assert final_files == len(data["robots"]), "dir/JSON robot count mismatch!"
    print("OK: dirs now exactly mirror staged_import.json")


if __name__ == "__main__":
    main()
