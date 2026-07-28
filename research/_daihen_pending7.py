"""List DAIHEN pending_review robots + current primary URLs."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
pending = [
    r
    for r in c.list_robots_for_company(1402)
    if (r.get("status") or "") == "pending_review"
]
print("pending", len(pending))
for r in pending:
    full = c._get(f"robots/robots/{r['id']}/")
    img = (full.get("image") or "").strip()
    photos = full.get("photos") or []
    print(f"{r['id']} {r.get('name')}")
    print(f"  image={img}")
    for p in photos[:3]:
        print(f"  photo primary={p.get('is_primary')} {(p.get('url') or '')[:100]}")
