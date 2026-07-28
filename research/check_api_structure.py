"""
check_api_structure.py
Inspects the API structure to find the correct robots endpoint and query params.
"""
import json
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

# 1. Check what the robots endpoint returns for a basic query
print("=== Basic robots endpoint test ===")
try:
    result = client._get('/robots/', params={'page_size': 3})
    if isinstance(result, dict):
        print(f"  Keys: {list(result.keys())}")
        print(f"  Count: {result.get('count')}")
        robots = result.get('results', [])
        if robots:
            print(f"  First robot keys: {list(robots[0].keys())}")
            print(f"  First robot: {robots[0].get('name')} | company: {robots[0].get('company')} | company_slug: {robots[0].get('company_slug')}")
    else:
        print(f"  Type: {type(result)}, content: {str(result)[:200]}")
except Exception as e:
    print(f"  Error: {e}")

# 2. Try the bulk-import endpoint to see what it returns
print("\n=== Bulk import robots endpoint (GET) ===")
try:
    result = client._get('/robots/bulk-import/', params={'page_size': 3})
    print(f"  Result: {json.dumps(result, indent=2)[:400]}")
except Exception as e:
    print(f"  Error: {e}")

# 3. Check the import_staging.py to understand the correct endpoint
print("\n=== Check ResearchApiClient methods ===")
methods = [m for m in dir(client) if not m.startswith('_')]
print(f"  Public methods: {methods}")

# 4. Try the robots endpoint with the correct company filter
print("\n=== Try robots with company name search ===")
for search_term in ['TX2-40', 'Stäubli TX2', 'staubli tx2', 'TS2-40']:
    try:
        result = client._get('/robots/', params={'search': search_term, 'page_size': 5})
        if isinstance(result, dict):
            count = result.get('count', 0)
            robots = result.get('results', [])
            print(f"  Search '{search_term}': count={count}, results={len(robots)}")
            for r in robots[:3]:
                print(f"    ID: {r.get('id')} | {r.get('name')} | company: {r.get('company')} | image: {'✓' if r.get('image_url') else '✗'}")
    except Exception as e:
        print(f"  Search '{search_term}': Error - {e}")

# 5. Check the company_missing_data signature
print("\n=== get_company_missing_data signature ===")
import inspect
sig = inspect.signature(client.get_company_missing_data)
print(f"  Params: {sig}")

# 6. Use get_company_missing_data correctly
print("\n=== get_company_missing_data for staubli-robotics ===")
try:
    result = client.get_company_missing_data(company_slug='staubli-robotics')
    if isinstance(result, dict):
        print(f"  Keys: {list(result.keys())}")
        robots = result.get('results', result.get('robots', []))
        print(f"  Robots count: {len(robots)}")
        for r in robots[:5]:
            has_image = bool(r.get('image_url', ''))
            print(f"    ID: {r.get('id')} | {r.get('name')} | Image: {'✓' if has_image else '✗'}")
    elif isinstance(result, list):
        print(f"  List count: {len(result)}")
        for r in result[:5]:
            has_image = bool(r.get('image_url', ''))
            print(f"    ID: {r.get('id')} | {r.get('name')} | Image: {'✓' if has_image else '✗'}")
    else:
        print(f"  Result: {str(result)[:300]}")
except Exception as e:
    print(f"  Error: {e}")
