"""
cyberdyne_import_patched.py
Imports all patched Cyberdyne staged JSON files one-by-one (per-file),
bypassing the batch-level duplicate-name validator that rejects variant
families sharing the same display name (e.g. HAL-FL08/07/05 all named
"Well-Being HAL® – Lower Limb Type").

Uses update_existing=True + patch_existing=True so only blank fields are
filled — existing good data is never overwritten.

Run from the research directory:
  python cyberdyne_import_patched.py
  python cyberdyne_import_patched.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from import_staging import load_json_robots, resolve_created_by_id
from map_to_bulk_import import staging_robots_to_bulk_import_rows

STAGING_DIR = Path(__file__).resolve().parent / "staging" / "robots" / "cyberdyne-inc" / "overnight"
RESULT_PATH = Path(__file__).resolve().parent / "staging" / "reports" / "cyberdyne_patch_import_result.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Import patched Cyberdyne JSON files one-by-one")
    parser.add_argument("--dry-run", action="store_true", help="Print rows but do not call API")
    args = parser.parse_args()

    files = sorted(STAGING_DIR.glob("robot_*.json"))
    if not files:
        print(f"ERROR: No robot_*.json files found in {STAGING_DIR}", file=sys.stderr)
        return 1

    print(f"\n=== Cyberdyne Patch Import ({'DRY RUN' if args.dry_run else 'LIVE'}) ===")
    print(f"Staging dir: {STAGING_DIR}")
    print(f"Files to import: {len(files)}\n")

    client = ResearchApiClient()
    created_by = resolve_created_by_id()

    created = updated = errors = skipped = 0
    all_results: list[dict] = []

    for json_file in files:
        robots = load_json_robots(json_file)
        rows = staging_robots_to_bulk_import_rows(robots)
        if not rows:
            print(f"  SKIP {json_file.name} — no rows after mapping")
            continue

        row = rows[0]
        robot_id = row.get("id")
        name = row.get("name", "")
        model = row.get("model_name", "")

        if args.dry_run:
            print(f"  DRY  {json_file.name}: id={robot_id} name={name!r} model={model!r}")
            continue

        result = client.bulk_import_robots(
            rows,
            update_existing=True,
            patch_existing=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=created_by,
            replace_media=False,
        )
        fc = result.get("created_count", 0)
        fu = result.get("updated_count", 0)
        fe = result.get("error_count", 0)
        fs = result.get("skipped_count", 0)
        created += fc
        updated += fu
        errors += fe
        skipped += fs
        all_results.extend(result.get("results") or [])

        action_str = f"created={fc} updated={fu} skipped={fs} errors={fe}"
        print(f"  {'OK' if fe == 0 else 'ERR'} {json_file.name}: {name!r} ({model}) — {action_str}")
        if fe > 0:
            for r in result.get("results") or []:
                if r.get("action") in {"error", "failed"} or r.get("error"):
                    print(f"      ERR detail: {r}")

    if not args.dry_run:
        print(f"\nDONE  created={created} updated={updated} skipped={skipped} errors={errors}")
        RESULT_PATH.write_text(
            json.dumps(
                {"created": created, "updated": updated, "skipped": skipped, "errors": errors, "results": all_results},
                indent=2, ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )
        print(f"Results written to: {RESULT_PATH}")
    else:
        print(f"\nDry run complete — {len(files)} files would be imported.")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
