"""Verify Yaskawa 772 enrich coverage."""
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
robots = c.list_robots_for_company(772) or []
print("status", dict(Counter(r.get("status") for r in robots)))
pay = fam = cn = feat_ok = reach = weight = rep = 0
junk = 0
for r in robots:
    d = c._get(f"robots/robots/{r['id']}/")
    if d.get("payload_kg"):
        pay += 1
    if d.get("reach_mm"):
        reach += 1
    if d.get("family_key"):
        fam += 1
    if d.get("manufacturer_countries"):
        cn += 1
    feat = d.get("features") or ""
    if len(feat) >= 40 and not feat.startswith("Search for:"):
        feat_ok += 1
    if feat.startswith("Search for:"):
        junk += 1
    if d.get("weight_kg"):
        weight += 1
    if d.get("repeatability_mm") is not None:
        rep += 1

n = len(robots)
print(f"payload={pay}/{n} reach={reach} family={fam} country={cn}")
print(f"features_ok={feat_ok} junk_features={junk} weight={weight} repeat={rep}")
for rid in (2594, 2600, 2601, 2634, 3007, 3032, 2629, 3029):
    d = c._get(f"robots/robots/{rid}/")
    print(
        f"{rid} {d.get('name')}: fam={d.get('family_key')} pay={d.get('payload_kg')} "
        f"reach={d.get('reach_mm')} w={d.get('weight_kg')} r={d.get('repeatability_mm')} "
        f"cn={bool(d.get('manufacturer_countries'))} feat={len(d.get('features') or '')}"
    )
    print(f"  purpose={(d.get('purpose') or '')[:80]!r}")
