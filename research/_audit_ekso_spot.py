"""Spot-check Ekso 147 queue for Approve presentation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

IDS = [1966, 1967, 437, 2481, 1968]
REJECTED = [436, 179]


def main() -> int:
    c = ResearchApiClient()
    print("=== PUBLISH CANDIDATES ===")
    for rid in IDS:
        r = c._get(f"robots/robots/{rid}/")
        img = (r.get("image") or r.get("s3_image") or "")[:80]
        avail = r.get("availability_status")
        fam = r.get("family_key")
        feats = len(r.get("features") or "")
        url = r.get("url") or ""
        w = r.get("weight_kg")
        print(
            f"{rid} | {r.get('name')} | status={r.get('status')} | avail={avail} | "
            f"family={fam} | feats={feats} | wt={w} | url={url}"
        )
        print(f"     img={img}")
    print("=== REJECTED ===")
    for rid in REJECTED:
        r = c._get(f"robots/robots/{rid}/")
        print(f"{rid} | {r.get('name')} | status={r.get('status')} | reason={r.get('rejection_reason')}")
    # company pending count
    page = c._get("robots/robots/", params={"company": 147, "status": "pending_review", "page_size": 50})
    results = page.get("results") or page if isinstance(page, list) else page.get("results") or []
    print(f"pending_review count: {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
