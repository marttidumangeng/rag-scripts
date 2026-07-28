"""One-off backfill: sync RobotInformationSource citations (parsed from
url/notes) for robots enriched before citations.py existed, and clean up
notes where the "[AI Research]" boilerplate prefix got duplicated across
repeated runs.

Usage:
  python backfill_information_sources.py --company-id 1424
  python backfill_information_sources.py --company-id 1424 --apply
"""
from __future__ import annotations

import argparse
import sys

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

from api_client import ResearchApiClient
from citations import dedupe_ai_research_prefix, parse_citations, sync_information_sources


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-id", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    all_robots = client.list_robots_for_company(args.company_id)
    # Safety guard: never touch already-approved/published (live) robots — same
    # rule the research pipeline enforces (robot_auto_research.py).
    robots = [r for r in all_robots if str(r.get("status") or "").lower() in ("draft", "pending_review")]
    skipped = len(all_robots) - len(robots)
    if skipped:
        print(f"Skipping {skipped} non-draft/pending_review robot(s) (live status)")

    sources_synced = 0
    notes_cleaned = 0

    for r in robots:
        rid = r["id"]
        name = r.get("name") or f"id={rid}"

        parsed = parse_citations(r.get("url") or "", r.get("notes") or "")
        if parsed:
            print(f"[{rid}] {name}: {len(parsed)} citation(s) parsed")
            if args.apply:
                try:
                    sync_information_sources(client, rid)
                    sources_synced += 1
                except Exception as exc:
                    print(f"    sync ERROR: {exc}")
            else:
                sources_synced += 1

        cleaned = dedupe_ai_research_prefix(r.get("notes") or "")
        if cleaned != (r.get("notes") or ""):
            print(f"[{rid}] {name}: notes had duplicated [AI Research] prefix")
            if args.apply:
                try:
                    client._patch(f"robots/robots/{rid}/", {"notes": cleaned})
                except Exception as exc:
                    print(f"    notes patch ERROR: {exc}")
            notes_cleaned += 1

    print(f"\nDone. sources_synced={sources_synced} notes_cleaned={notes_cleaned} apply={args.apply}")


if __name__ == "__main__":
    main()
