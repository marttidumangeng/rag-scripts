"""Find Huayan Robotics company ID by searching the triage report and missing-image list."""
import json
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

client = ResearchApiClient()

# Search via list_robots_missing_image and look for huayan in company name
print("Searching missing-image robots for Huayan...")
data = client._get("robots/robots/", params={"status": "pending_review", "page_size": 100, "page": 1})
results = data.get("results", [])
for r in results:
    cref = r.get("company_ref") or {}
    cname = (cref.get("name") or r.get("company") or "").lower()
    if "huayan" in cname or "hua yan" in cname:
        print(f"  Robot ID={r.get('id')} name={r.get('name')} company_id={cref.get('id')} company={cref.get('name')} website={cref.get('website')}")

# Also check the triage report
triage_path = _RESEARCH_DIR / "staging" / "reports" / "content-queue-triage.json"
if triage_path.exists():
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    companies = triage.get("companies_ranked") or triage.get("companies") or []
    print(f"\nSearching triage report ({len(companies)} companies) for 'huayan'...")
    for c in companies:
        name = (c.get("company_name") or c.get("name") or "").lower()
        if "huayan" in name or "hua yan" in name:
            print(f"  company_id={c.get('company_id')} name={c.get('company_name') or c.get('name')} website={c.get('website')}")
            print(f"    gap_counts={c.get('gap_counts')}")
