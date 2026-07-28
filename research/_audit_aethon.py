"""Audit Aethon (7) pending robots."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
co = c.get_company(7)
print("company", co.get("name"), co.get("website"), co.get("country"))
robots = c.list_robots_for_company(7) or []
print("status", dict(Counter(r.get("status") for r in robots)))
for r in robots:
    if r.get("status") != "pending_review":
        continue
    d = c._get(f"robots/robots/{r['id']}/")
    img = (d.get("image") or d.get("s3_image") or "")[:90]
    name = (r.get("name") or "")[:42]
    print(
        f"{r['id']} {name:42} feat={len(d.get('features') or ''):3} "
        f"img={bool(img)} countries={bool(d.get('manufacturer_countries'))} "
        f"cat={bool(d.get('categories'))} uses={bool(d.get('uses'))} "
        f"avail={d.get('availability_status')} family={d.get('family_key')}"
    )
    print("  url", (d.get("url") or "")[:70])
    print("  img", img)
    print("  purpose", (d.get("purpose") or "")[:80])
    print("  desc", (d.get("description") or "")[:100])
