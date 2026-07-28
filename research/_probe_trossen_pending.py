"""Find Trossen robots still pending or without photos."""
from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
rows = c.list_robots_for_company(307)
for r in sorted(rows, key=lambda x: (str(x.get("status")), x.get("id", 0))):
    rid = r["id"]
    full = c._session.get(c._url(f"robots/robots/{rid}/"), timeout=60).json()
    photos = full.get("photos") or []
    img = full.get("image") or full.get("image_url") or ""
    print(
        rid,
        full.get("status"),
        full.get("name"),
        "photos",
        len(photos),
        "img",
        bool(img),
        (img or "")[:90],
    )
    if full.get("status") == "pending_review" or len(photos) == 0 or not img:
        print("  url", full.get("url"))
        print("  notes", (full.get("notes") or "")[:240])
