"""Dump taxonomy gaps for Locus + Seegrid published/pending."""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient


def dump(company_id: int) -> None:
    c = ResearchApiClient()
    print(f"=== company {company_id} ===")
    for r in sorted(c.list_robots_for_company(company_id), key=lambda x: x.get("id", 0)):
        if r.get("status") == "rejected":
            continue
        full = c._get(f"robots/robots/{r['id']}/")
        uses = full.get("uses") or []
        inds = full.get("industries") or []
        tags = full.get("tags") or []
        mov = full.get("movement_types") or []
        country = full.get("manufacturer_countries") or []
        ref = full.get("manufacturer_country_ref")
        print(
            f"{full['id']} {full.get('status')} {(full.get('name') or '')[:40]}\n"
            f"  country_m2m={len(country)} ref={ref}\n"
            f"  uses={len(uses)} ind={len(inds)} mov={len(mov)} tags={len(tags) if isinstance(tags, list) else tags}\n"
            f"  uses={[(u.get('key') if isinstance(u, dict) else u) for u in uses]}\n"
            f"  ind={[(u.get('key') if isinstance(u, dict) else u) for u in inds]}\n"
            f"  tags={[(t.get('name') if isinstance(t, dict) else t) for t in (tags if isinstance(tags, list) else [])][:8]}"
        )


dump(69)
dump(209)
