"""Fast: US companies not in content_queue_done with pending_review > 0."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
done = set(json.loads(Path("state/content_queue_done.json").read_text(encoding="utf-8"))["companies"])

# Page companies/?country=US or country_id=20
hits = []
page = 1
while page <= 50:
    data = c._get("companies/", params={"page": page, "page_size": 100, "country": "US"})
    results = data.get("results") or []
    if not results:
        # fallback without filter once
        if page == 1:
            data = c._get("companies/", params={"page": 1, "page_size": 100})
            results = data.get("results") or []
            print("country=US filter empty; sample keys", list((results[0] or {}).keys())[:20] if results else None)
        break
    for co in results:
        cid = co.get("id")
        if not cid or cid in done:
            continue
        country = co.get("country") or {}
        code = (country.get("code") if isinstance(country, dict) else "") or ""
        if code and code.upper() != "US":
            continue
        pr = c._get(
            "robots/robots/",
            params={"company_ref": cid, "status": "pending_review", "page_size": 1},
        )
        cnt = int(pr.get("count") or 0) if isinstance(pr, dict) else 0
        if cnt > 0:
            hits.append(
                (
                    cnt,
                    cid,
                    co.get("name"),
                    (co.get("website") or "")[:55],
                    code or "?",
                )
            )
            print("HIT", hits[-1])
    if not data.get("next"):
        break
    page += 1
    if page % 5 == 0:
        print(f"... company page {page}, hits={len(hits)}")

hits.sort(reverse=True)
print("TOTAL HITS", len(hits))
for row in hits[:30]:
    print(row)
