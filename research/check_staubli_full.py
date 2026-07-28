"""
check_staubli_full.py
Finds all Stäubli robots in the database (both company IDs 437 and 1475)
and verifies their image status.
"""
import json
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()


def get_robots_for_company(company_id, company_name):
    print(f"\n=== Robots for {company_name} (company_id={company_id}) ===")
    try:
        # Try the research-specific endpoint that lists robots needing data
        result = client.get_company_missing_data(
            exclude_ids="",
            company_id=company_id,
        )
        print(f"  Missing data result type: {type(result)}")
        if isinstance(result, dict):
            print(f"  Keys: {list(result.keys())}")
    except Exception as e:
        print(f"  get_company_missing_data error: {e}")

    # Try the robots list endpoint with different param names
    for param_name in ['company', 'company_id', 'company__id']:
        try:
            result = client._get('/robots/', params={param_name: company_id, 'page_size': 50})
            if isinstance(result, dict):
                count = result.get('count', 0)
                robots = result.get('results', [])
            elif isinstance(result, list):
                robots = result
                count = len(robots)
            else:
                continue

            if robots:
                print(f"  Found {count} robots using param '{param_name}':")
                for r in robots[:20]:
                    has_image = bool(r.get('image_url', ''))
                    print(f"    ID: {r.get('id')} | {r.get('name')} | Image: {'✓' if has_image else '✗'} | {r.get('image_url', 'NO IMAGE')[:70]}")
                return robots
        except Exception as e:
            pass

    print(f"  No robots found with any param variant")
    return []


def check_robot_by_slug(slug):
    """Check a specific robot by its slug."""
    try:
        result = client._get(f'/robots/{slug}/')
        has_image = bool(result.get('image_url', ''))
        print(f"  Slug '{slug}': ID={result.get('id')} | Image: {'✓' if has_image else '✗'} | {result.get('image_url', 'NO IMAGE')[:70]}")
        return result
    except Exception as e:
        print(f"  Slug '{slug}': Error - {e}")
        return None


# Check both Stäubli company IDs
get_robots_for_company(437, "Stäubli (ID 437)")
get_robots_for_company(1475, "Stäubli Robotics (ID 1475)")

# Try direct slug lookups for known Stäubli robots
print("\n=== Direct slug lookups ===")
slugs_to_check = [
    'tx2-40', 'tx240', 'staubli-tx2-40', 'staubli_tx240',
    'ts2-40', 'ts240', 'staubli-ts2-40',
    'tp80', 'tp80-fast-picker',
    'pf3', 'staubli-pf3',
]
for slug in slugs_to_check:
    check_robot_by_slug(slug)

# Check the API endpoint structure
print("\n=== API endpoint discovery ===")
try:
    result = client._get('/')
    print(f"  Root API: {json.dumps(result, indent=2)[:500]}")
except Exception as e:
    print(f"  Root API error: {e}")
