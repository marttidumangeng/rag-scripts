"""Find the correct company ID for Huayan Robotics."""
import sys
from pathlib import Path
_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

client = ResearchApiClient()

# Search for companies matching 'huayan'
resp = client._get("companies/", params={"search": "huayan", "page_size": 20})
results = resp.get("results", [])
print(f"Found {len(results)} companies matching 'huayan':")
for c in results:
    print(f"  ID={c.get('id')} name={c.get('name')} slug={c.get('slug')} website={c.get('website')}")

# Also try 'hua yan'
resp2 = client._get("companies/", params={"search": "hua", "page_size": 50})
results2 = resp2.get("results", [])
print(f"\nFound {len(results2)} companies matching 'hua':")
for c in results2:
    name = (c.get('name') or '').lower()
    if 'hua' in name:
        print(f"  ID={c.get('id')} name={c.get('name')} slug={c.get('slug')} website={c.get('website')}")
