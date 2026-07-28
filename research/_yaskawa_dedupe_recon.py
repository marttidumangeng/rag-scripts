#!/usr/bin/env python3
"""Read-only recon of Yaskawa (company 772) content-queue duplicates.

Fetches all Yaskawa robots, separates the two known groups, pairs them by
normalized model token, and reports field-level comparison so we can plan a
merge. Touches nothing. pending_review only for merge candidacy; anything
Approved/Published is flagged and excluded.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

COMPANY_ID = 772
OUT = _RESEARCH_DIR / "staging" / "reports" / "yaskawa-dedupe-recon.json"


def norm_model(name: str) -> str:
    """Extract the model token: strip 'Motoman' prefix and 'Robot' suffix, then
    lowercase alnum-only."""
    n = name.strip()
    n = re.sub(r'(?i)^motoman\s+', '', n)
    n = re.sub(r'(?i)\s+robot$', '', n)
    return re.sub(r'[^a-z0-9]', '', n.lower())


def main() -> int:
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID, page_size=50)
    print(f"Fetched {len(robots)} robots for company {COMPANY_ID}")

    # Show the shape of one record so we know which fields are available.
    if robots:
        sample = robots[0]
        print("\nSample record keys:")
        print(sorted(sample.keys()))
        print("\nSample record (id, name, status, release_year, url, has image, information_sources):")
        for r in robots[:3]:
            print(json.dumps({
                "id": r.get("id"),
                "name": r.get("name"),
                "status": r.get("status"),
                "release_year": r.get("release_year"),
                "url": r.get("url"),
                "image": r.get("image") or r.get("s3_image") or r.get("image_url"),
                "information_sources": r.get("information_sources"),
                "source_locale": r.get("source_locale"),
            }, ensure_ascii=False, indent=2))

    # Status breakdown
    by_status: dict[str, int] = {}
    for r in robots:
        by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
    print(f"\nStatus breakdown: {by_status}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(robots, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote raw dump -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
