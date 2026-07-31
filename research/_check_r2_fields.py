"""Check field names of a staged company/robot entry in staged_import_2.json."""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

d = json.loads(Path("staging/gap_discovery/staged_import_2.json").read_text(encoding="utf-8"))
print("top-level keys:", list(d.keys()))
cos = d.get("companies", [])
if cos:
    print("\ncompany[0] fields:")
    for k, v in cos[0].items():
        print(f"  {k}: {repr(v)[:100]}")
# count website-ish
for f in ("website", "website_url", "url"):
    n = sum(1 for c in cos if c.get(f))
    print(f"companies with '{f}': {n}")
robs = d.get("robots", [])
if robs:
    print("\nrobot[0] fields:")
    for k, v in robs[0].items():
        print(f"  {k}: {repr(v)[:100]}")
