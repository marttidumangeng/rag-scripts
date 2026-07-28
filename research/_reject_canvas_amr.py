"""Reject Canvas Technology (Amazon) Canvas AMR (3612) — phantom / wrong-brand.

Company website was Instructure Canvas LMS (edtech), unrelated to the 2015–2022
Boulder warehouse robotics startup Amazon acquired (2019) and shuttered (2022).
No public sellable 'Canvas AMR' SKU remains; tech folded into Amazon Robotics (e.g. Proteus).
"""
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
    "phantom_sku: Canvas Technology (Boulder warehouse AMR) acquired by Amazon Apr 2019 "
    "and shuttered Oct 2022; no public 'Canvas AMR' product SKU. Company website wrongly "
    "pointed to Instructure Canvas LMS (unrelated edtech). Navigation/safety tech reportedly "
    "folded into Amazon Robotics (e.g. Proteus) — do not keep this shell. Sources: "
    "TechCrunch 2019-04-10 acquisition; Business Insider 2022-10 Canvas shutdown."
)


def main() -> int:
    c = ResearchApiClient()
    rid = 3612
    c._patch(
        f"robots/robots/{rid}/",
        {
            "status": "rejected",
            "rejection_reason": REASON[:500],
            "notes": (
                "[AI Research] Rejected 2026-07-20 overnight US drain: " + REASON
            )[:2000],
        },
    )
    # Clear wrong Instructure LMS website; no live Canvas Technology OEM domain.
    c._patch(
        "companies/805/",
        {
            "website": "",
            "notes": (
                "[AI Research] 2026-07-20: cleared wrong website "
                "https://www.instructure.com/canvas (Instructure LMS ≠ Canvas Technology). "
                "Startup acquired by Amazon 2019, shuttered 2022; queue emptied via reject 3612."
            ),
        },
    )
    after = c._get(f"robots/robots/{rid}/")
    co = c._get("companies/805/")
    print("robot status=", after.get("status"), "reason=", (after.get("rejection_reason") or "")[:120])
    print("company website=", repr(co.get("website")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
