"""
audit_rokae_specs_tags.py
--------------------------
Quick audit of specs and tags coverage for all ROKAE robots (company 1416).
Prints a summary and saves a JSON report.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

COMPANY_ID = 1416
client = ResearchApiClient()

robots = client.list_robots_for_company(COMPANY_ID)
print(f"Total robots: {len(robots)}")

no_specs = []
no_tags  = []
both_missing = []

for r in robots:
    rid   = r.get("id")
    name  = r.get("name", f"Robot {rid}")
    specs = r.get("specs") or {}
    tags  = r.get("tags") or []
    url   = r.get("url", "")
    has_specs = bool(specs)
    has_tags  = bool(tags)
    if not has_specs:
        no_specs.append({"id": rid, "name": name, "url": url})
    if not has_tags:
        no_tags.append({"id": rid, "name": name, "url": url})
    if not has_specs and not has_tags:
        both_missing.append({"id": rid, "name": name, "url": url})

print(f"\nNo specs:       {len(no_specs)}/{len(robots)}")
print(f"No tags:        {len(no_tags)}/{len(robots)}")
print(f"Both missing:   {len(both_missing)}/{len(robots)}")

print("\n--- Sample robot full detail (first with both missing) ---")
if both_missing:
    sample = client._get(f"robots/robots/{both_missing[0]['id']}/")
    print(json.dumps({k: v for k, v in sample.items() if k in
          ("id","name","specs","tags","url","model_name","family_name","features","description")}, indent=2, ensure_ascii=False))

out = {
    "total": len(robots),
    "no_specs": no_specs,
    "no_tags": no_tags,
    "both_missing": both_missing,
}
out_path = os.path.join(os.path.dirname(__file__), "staging", "reports", "rokae_specs_tags_audit.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\nReport saved to {out_path}")
