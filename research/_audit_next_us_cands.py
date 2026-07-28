"""Quick audit of next US OEM candidates after Aethon."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
done = set(json.loads(Path("state/content_queue_done.json").read_text(encoding="utf-8"))["companies"])

# Prefer small/medium US fleets with websites from prior sweep
CANDS = [34, 198, 212, 147, 1378, 160, 423, 375, 236, 213, 114, 851, 814]

for cid in CANDS:
    if cid in done:
        print(f"{cid}: SKIP done")
        continue
    co = c.get_company(cid) or {}
    name = co.get("name") or "?"
    web = (co.get("website") or "")[:60]
    country = co.get("country") or {}
    code = country.get("code") if isinstance(country, dict) else ""
    robots = c.list_robots_for_company(cid) or []
    by = Counter(r.get("status") for r in robots)
    pending = [r for r in robots if r.get("status") == "pending_review"]
    print(f"\n=== {cid} {name} {code} web={web}")
    print(f"    status={dict(by)} pending={len(pending)}")
    gaps = Counter()
    for r in pending[:12]:
        d = c._get(f"robots/robots/{r['id']}/")
        g = []
        if not (d.get("image") or d.get("s3_image")):
            g.append("no_img")
        if len(d.get("features") or "") < 40:
            g.append("no_feat")
        if not (d.get("manufacturer_countries") or []):
            g.append("no_country")
        if not (d.get("categories") or []):
            g.append("no_cat")
        if not (d.get("uses") or []):
            g.append("no_use")
        if not d.get("family_key"):
            g.append("no_family")
        if d.get("availability_status") in (None, ""):
            g.append("no_avail")
        for x in g:
            gaps[x] += 1
        print(
            f"      {r['id']} {(r.get('name') or '')[:42]:42} "
            f"{','.join(g) or 'ok'} url={(d.get('url') or '')[:45]}"
        )
    print(f"    gap_counts={dict(gaps)}")
