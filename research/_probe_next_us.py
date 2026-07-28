"""Verify Anduril cleared; probe next US OEM candidates."""
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

robots = c.list_robots_for_company(284) or []
print("Anduril", dict(Counter(r.get("status") for r in robots)))

done = set(
    json.loads(Path("state/content_queue_done.json").read_text(encoding="utf-8")).get(
        "companies"
    )
    or []
)
processed = set(load_processed_ids().companies)

cands = [350, 266, 259, 307, 12, 18, 837, 36, 39]
for cid in cands:
    co = c.get_company(cid)
    if not co:
        print(cid, "MISSING")
        continue
    name = co.get("name")
    web = co.get("website") or co.get("website_url") or ""
    country = co.get("country") or co.get("country_id") or co.get("hq_country")
    robots = c.list_robots_for_company(cid) or []
    by = Counter(r.get("status") for r in robots)
    pending = [r for r in robots if r.get("status") == "pending_review"]
    gaps = []
    for r in pending[:8]:
        d = c._get(f"robots/robots/{r['id']}/")
        g = []
        img = d.get("s3_image") or d.get("image") or ""
        if not img:
            g.append("no_img")
        if len(d.get("features") or "") < 40:
            g.append("no_feat")
        if not (d.get("manufacturer_countries") or d.get("manufacturer_country")):
            g.append("no_country")
        if not (d.get("categories") or []):
            g.append("no_cat")
        if not (d.get("uses") or []):
            g.append("no_use")
        if d.get("availability_status") in (None, ""):
            g.append("no_avail")
        if g:
            gaps.append((r["id"], r.get("name"), ",".join(g)))
    print(
        f"--- {cid} {name} done={cid in done} proc={cid in processed} "
        f"web={bool(web)} country={country}"
    )
    print(f"    status={dict(by)} pending_gaps={gaps[:6]}")
    print(f"    website={(web or '')[:70]}")
    for r in pending[:6]:
        print(f"      pending {r['id']} {r.get('name')}")
