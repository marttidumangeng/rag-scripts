"""Identify company 772 + pending gap overview."""
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
co = c.get_company(772) or {}
print("company", co.get("id"), co.get("name"))
print("website", co.get("website"))
print("country", co.get("country") or co.get("country_id"))
robots = c.list_robots_for_company(772) or []
print("status", dict(Counter(r.get("status") for r in robots)))
print("total", len(robots))
pending = sorted(
    [r for r in robots if r.get("status") == "pending_review"],
    key=lambda x: x.get("id") or 0,
)
print("pending", len(pending))
for r in pending:
    d = c._get(f"robots/robots/{r['id']}/")
    img = d.get("s3_image") or d.get("image") or ""
    code = size = None
    if img:
        try:
            resp = requests.get(img, timeout=15)
            code, size = resp.status_code, len(resp.content)
        except Exception as e:
            code, size = "ERR", str(e)[:40]
    print(
        f"  {r['id']}\t{(r.get('name') or '')[:42]:42}\t"
        f"feat={len(d.get('features') or ''):3} cn={bool(d.get('manufacturer_countries'))} "
        f"cat={bool(d.get('categories'))} uses={bool(d.get('uses'))} "
        f"fam={d.get('family_key') or '-':20} "
        f"img={code}/{size} "
        f"pay={d.get('payload_kg')} w={d.get('weight_kg')} dof={d.get('dof')} "
        f"url={(d.get('url') or '')[:55]}"
    )
