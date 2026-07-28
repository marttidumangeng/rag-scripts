"""Probe next US OEM candidates after Stryker."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env
from workflow_backfill import load_processed_ids

load_research_env()
c = ResearchApiClient()
done = set(
    json.loads(Path("state/content_queue_done.json").read_text(encoding="utf-8")).get(
        "companies"
    )
    or []
)
processed = set(load_processed_ids().companies)

# Prefer US with pending gaps, not yet queue-done, real website
cands = [266, 259, 307, 12, 18, 837, 36, 39, 368, 13, 15, 826, 223, 271, 274, 311]
for cid in cands:
    co = c.get_company(cid)
    if not co:
        continue
    name = co.get("name")
    web = co.get("website") or co.get("website_url") or ""
    country = co.get("country") or {}
    code = country.get("code") if isinstance(country, dict) else country
    robots = c.list_robots_for_company(cid) or []
    by = Counter(r.get("status") for r in robots)
    pending = [r for r in robots if r.get("status") == "pending_review"]
    if not pending and cid in done:
        continue
    gaps = []
    for r in pending[:5]:
        d = c._get(f"robots/robots/{r['id']}/")
        g = []
        if not (d.get("s3_image") or d.get("image")):
            g.append("no_img")
        if len(d.get("features") or "") < 40:
            g.append("no_feat")
        if not (d.get("manufacturer_countries") or []):
            g.append("no_country")
        if not (d.get("categories") or []):
            g.append("no_cat")
        if not (d.get("uses") or []):
            g.append("no_use")
        if d.get("availability_status") in (None, ""):
            g.append("no_avail")
        typed = any(
            d.get(k) not in (None, "", 0)
            for k in (
                "weight_kg",
                "payload_kg",
                "height_mm",
                "length_mm",
                "dof",
                "speed",
            )
        )
        if not typed:
            g.append("no_specs")
        if g:
            gaps.append((r["id"], (r.get("name") or "")[:40], ",".join(g)))
    print(
        f"--- {cid} {name} done={cid in done} proc={cid in processed} "
        f"country={code} pending={len(pending)}"
    )
    print(f"    status={dict(by)} web={(web or '')[:60]}")
    for g in gaps[:5]:
        print(f"    gap {g}")
    for r in pending[:4]:
        print(f"    pending {r['id']} {r.get('name')}")
