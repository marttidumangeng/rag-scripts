"""
check_staubli_v2.py
Uses the correct API endpoint structure to find Stäubli robots and verify images.
"""
import json
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

# Use the correct robots endpoint with company slug filter
print("=== Robots for staubli-robotics (slug filter) ===")
try:
    result = client._get('/robots/', params={'company__slug': 'staubli-robotics', 'page_size': 50})
    if isinstance(result, dict):
        count = result.get('count', 0)
        robots = result.get('results', [])
        print(f"  Total count: {count}")
        for r in robots:
            has_image = bool(r.get('image_url', ''))
            print(f"  ID: {r.get('id')} | {r.get('name')} | Image: {'✓' if has_image else '✗'}")
            if r.get('image_url'):
                print(f"    → {r.get('image_url')[:80]}")
    else:
        print(f"  Unexpected result type: {type(result)}")
        print(json.dumps(result, indent=2)[:500])
except Exception as e:
    print(f"  Error: {e}")

print("\n=== Robots for staubli (slug filter) ===")
try:
    result = client._get('/robots/', params={'company__slug': 'staubli', 'page_size': 50})
    if isinstance(result, dict):
        count = result.get('count', 0)
        robots = result.get('results', [])
        print(f"  Total count: {count}")
        for r in robots[:10]:
            has_image = bool(r.get('image_url', ''))
            print(f"  ID: {r.get('id')} | {r.get('name')} | Image: {'✓' if has_image else '✗'}")
except Exception as e:
    print(f"  Error: {e}")

# Try the content queue endpoint used by the discovery pipeline
print("\n=== Content queue for staubli-robotics ===")
try:
    result = client._get('/robots/content-queue/', params={'company_id': 1475, 'page_size': 20})
    if isinstance(result, dict):
        count = result.get('count', 0)
        robots = result.get('results', [])
        print(f"  Queue count: {count}")
        for r in robots[:10]:
            has_image = bool(r.get('image_url', ''))
            print(f"  ID: {r.get('id')} | {r.get('name')} | Image: {'✓' if has_image else '✗'}")
    else:
        print(f"  Result: {json.dumps(result, indent=2)[:300]}")
except Exception as e:
    print(f"  Error: {e}")

# Check what the import actually created by looking at recently created robots
print("\n=== Recently created robots (last 50) ===")
try:
    result = client._get('/robots/', params={'page_size': 50, 'ordering': '-id'})
    if isinstance(result, dict):
        robots = result.get('results', [])
        staubli_robots = [r for r in robots if 'staubli' in r.get('company_slug', '').lower() or
                         'staubli' in str(r.get('company', '')).lower() or
                         'tx2' in r.get('name', '').lower() or
                         'ts2' in r.get('name', '').lower()]
        print(f"  Stäubli-related in last 50: {len(staubli_robots)}")
        for r in staubli_robots:
            has_image = bool(r.get('image_url', ''))
            print(f"  ID: {r.get('id')} | {r.get('name')} | company_slug: {r.get('company_slug')} | Image: {'✓' if has_image else '✗'}")
            if r.get('image_url'):
                print(f"    → {r.get('image_url')[:80]}")
        if not staubli_robots:
            # Print all recent robots to understand what was created
            print("  Last 10 created robots:")
            for r in robots[:10]:
                print(f"    ID: {r.get('id')} | {r.get('name')} | company: {r.get('company_slug', r.get('company'))}")
except Exception as e:
    print(f"  Error: {e}")
