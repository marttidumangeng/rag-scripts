"""Verify Jaten 5185/5190 after restore."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
robots = c.list_robots_for_company(1461) or []
print("status", dict(Counter(r.get("status") for r in robots)))
for rid in (5185, 5190):
    d = c._get(f"robots/robots/{rid}/")
    img = d.get("s3_image") or d.get("image") or ""
    r = requests.get(img, timeout=30) if img else None
    print(
        f"{rid} status={d.get('status')} pub_at={d.get('published_at')} "
        f"reject={d.get('rejection_reason')!r} fam={d.get('family_key')} "
        f"countries={bool(d.get('manufacturer_countries'))}"
    )
    print(f"  image={(d.get('image') or '')[:100]}")
    print(f"  s3_image={(d.get('s3_image') or '')[:100]}")
    print(f"  http={getattr(r, 'status_code', None)} bytes={len(r.content) if r else 0}")
print("rejected remaining:")
for r in robots:
    if r.get("status") == "rejected":
        print(f"  {r['id']} {r.get('name')}")
