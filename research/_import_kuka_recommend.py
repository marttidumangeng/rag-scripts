#!/usr/bin/env python3
"""Import only KUKA robots from the recommend_import triage list."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api_client import ResearchApiClient
from import_staging import load_json_robots, resolve_created_by_id
from map_to_bulk_import import staging_robots_to_bulk_import_rows

ROOT = Path(__file__).resolve().parent
TRIAGE = ROOT / "staging" / "reports" / "kuka_discovery_triage.json"
STAGING = ROOT / "staging" / "robots" / "kuka"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    triage = json.loads(TRIAGE.read_text(encoding="utf-8"))
    files = [STAGING / row["file"] for row in triage["recommend_import"]]
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        print("Missing staging files:", *missing[:10], sep="\n  ")
        if len(missing) > 10:
            print(f"  ... +{len(missing) - 10} more")
        return 1

    print(f"Importing {len(files)} recommend_import KUKA robots…")
    client = ResearchApiClient()
    created_by = resolve_created_by_id(1)
    robots: list[dict] = []
    for path in files:
        robots.extend(load_json_robots(path))

    bad = [r for r in robots if not r.get("name") or not (r.get("url") or r.get("website_url"))]
    if bad:
        print(f"WARN: {len(bad)} rows missing name/url")

    rows = staging_robots_to_bulk_import_rows(robots)
    print(f"mapped {len(rows)} bulk-import rows")

    batch_size = 20
    created = updated = errors = skipped = 0
    all_results: list = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        result = client.bulk_import_robots(
            batch,
            update_existing=False,
            patch_existing=False,
            status="pending_review",
            skip_company_update=True,
            created_by_id=created_by,
        )
        created += int(result.get("created_count") or 0)
        updated += int(result.get("updated_count") or 0)
        errors += int(result.get("error_count") or 0)
        skipped += int(result.get("skipped_count") or 0)
        all_results.extend(result.get("results") or [])
        print(
            f"  batch {i // batch_size + 1}: "
            f"created={result.get('created_count')} "
            f"updated={result.get('updated_count')} "
            f"errors={result.get('error_count')} "
            f"skipped={result.get('skipped_count')}"
        )
        if result.get("warnings"):
            print(f"    warnings: {result['warnings'][:5]}")
        if result.get("error_count"):
            for r in result.get("results") or []:
                if r.get("action") in {"error", "failed"} or r.get("error"):
                    print(f"    ERR {r}")

    print(f"\nDONE created={created} updated={updated} skipped={skipped} errors={errors}")
    for r in all_results[:10]:
        print(f"  {r.get('action')} id={r.get('id')} {r.get('name')}")
    if len(all_results) > 10:
        print(f"  ... +{len(all_results) - 10} more")

    out = ROOT / "staging" / "reports" / "kuka_recommend_import_result.json"
    out.write_text(
        json.dumps(
            {
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "errors": errors,
                "results": all_results,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
