import json
from pathlib import Path

d = json.loads(Path("staging/reports/us-overnight-queue.json").read_text(encoding="utf-8"))
us = [c for c in d["companies"] if (c.get("country") or "").upper() == "US"]
print("US explicit", len(us), "pending", sum(c["pending"] for c in us))
for c in sorted(us, key=lambda x: x["pending"]):
    web = (c.get("website") or "")[:50]
    print(f"{c['pending']:3d} {c['company_id']:5d} {(c['name'] or '')[:45]:45} {web}")
