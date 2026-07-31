"""Quick inspection of staged_import_2.json."""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

p = Path("staging/gap_discovery/staged_import_2.json")
d = json.loads(p.read_text(encoding="utf-8"))
cos = d.get("companies", [])
robs = d.get("robots", [])
low = d.get("low_signal_companies", [])
print(f"companies: {len(cos)}  robots: {len(robs)}  low_signal: {len(low)}")
with_web = [c for c in cos if c.get("website_url")]
print(f"companies with website: {len(with_web)}")

per: dict[str, int] = {}
for r in robs:
    per[r.get("company_slug", "?")] = per.get(r.get("company_slug", "?"), 0) + 1
print(f"companies with robots: {len(per)}")
print("\nTop 15 by robot count:")
for slug, n in sorted(per.items(), key=lambda x: -x[1])[:15]:
    print(f"  {n:3d}  {slug}")

print("\nAll companies:")
for c in sorted(cos, key=lambda x: x.get("name", "").lower()):
    nrob = per.get(c.get("slug", ""), 0)
    print(f"  {nrob:3d}  {c.get('name')}  ->  {c.get('website_url', '-')}")

print("\nSample robots (first 30):")
for r in robs[:30]:
    print(f"  [{r.get('company_slug')}] {r.get('name')}")
