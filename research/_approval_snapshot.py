#!/usr/bin/env python3
"""Recent approvals pulse with 502 retry; also check pending counts for likely approved cos."""
from __future__ import annotations

import sys
import time
from collections import defaultdict

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

# Likely recent from this session + checklist "approve tonight" / big fleets
CANDIDATES = [
    400, 1028, 239, 109, 428, 195, 73, 771, 259, 307, 266, 12, 18, 975,
    834, 368, 133, 773, 1445,
]


def main() -> int:
    c = ResearchApiClient()
    print("company pending/published snapshot:")
    for cid in CANDIDATES:
        for attempt in range(4):
            try:
                robots = c.list_robots_for_company(cid)
                break
            except Exception as e:
                print(f"  co {cid} retry {attempt}: {e}")
                time.sleep(2 ** attempt)
                robots = []
        by = defaultdict(int)
        name = "?"
        for r in robots:
            by[str(r.get("status") or "?").lower()] += 1
        if robots:
            try:
                d = c._get(f"robots/robots/{int(robots[0]['id'])}/")
                cref = d.get("company_ref") or {}
                if isinstance(cref, dict):
                    name = cref.get("name") or name
            except Exception:
                pass
        pub = by.get("published", 0) + by.get("approved", 0)
        pend = by.get("pending_review", 0)
        flag = "CLEARED" if pend == 0 and pub > 0 else ("partial" if pend and pub else "pending-heavy" if pend else "empty")
        print(f"  {cid:4d} {name[:42]:42} pub={pub:3d} pend={pend:3d}  {flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
