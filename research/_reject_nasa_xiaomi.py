"""Reject NASA (174) pending that are Xiaomi vacuums misfiled under NASA."""
from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

REASON = (
    "wrong_company: Xiaomi robot vacuum / CyberDog misfiled under NASA (174); "
    "not a NASA robot — reject from NASA queue"
)


def main() -> int:
    c = ResearchApiClient()
    page = 1
    ids = []
    while True:
        data = c._get(
            "robots/robots/",
            params={
                "company_ref": 174,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        if not batch:
            break
        for r in batch:
            name = (r.get("name") or "").lower()
            if "xiaomi" in name or "cyberdog" in name or "vacuum" in name:
                ids.append((r["id"], r.get("name")))
        if not data.get("next"):
            break
        page += 1
    print(f"reject candidates: {len(ids)}")
    for rid, name in ids:
        c._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": REASON[:500],
                "notes": f"[AI Research] Rejected 2026-07-20: {REASON}",
            },
        )
        print("rejected", rid, name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
