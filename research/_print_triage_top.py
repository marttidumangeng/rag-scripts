import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
r = json.loads(Path("staging/reports/content-queue-triage.json").read_text(encoding="utf-8"))
print(
    "scanned",
    r.get("scanned_robots"),
    "incomplete",
    r.get("incomplete_robots"),
    "ranked",
    r.get("companies_ranked"),
)
for i, c in enumerate(r.get("top") or [], 1):
    print(
        f"{i:>2} score={c['rank_score']} n={c['incomplete_count']} "
        f"id={c.get('company_id')} {c['company_name']}"
    )
    print(f"    gaps={c.get('gap_counts')} site={c.get('website')}")
    for s in (c.get("sample_robots") or [])[:3]:
        print(f"      sample {s.get('id')} {s.get('name')} {s.get('gaps')}")
