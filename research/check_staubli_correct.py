"""
check_staubli_correct.py
Uses the correct ResearchApiClient methods to find Stäubli robots and verify images.
"""
import json
import inspect
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

# Check signatures of the correct methods
print("=== Method signatures ===")
for method_name in ['list_robots_for_company', 'list_robots_missing_image', 'get_robot_missing_data']:
    method = getattr(client, method_name)
    sig = inspect.signature(method)
    print(f"  {method_name}{sig}")

# Use list_robots_for_company for staubli-robotics
print("\n=== list_robots_for_company('staubli-robotics') ===")
try:
    robots = client.list_robots_for_company('staubli-robotics')
    print(f"  Total robots: {len(robots)}")
    for r in robots[:20]:
        has_image = bool(r.get('image_url', ''))
        print(f"  ID: {r.get('id')} | {r.get('name')} | Image: {'✓' if has_image else '✗'}")
        if r.get('image_url'):
            print(f"    → {r.get('image_url')[:80]}")
except Exception as e:
    print(f"  Error: {e}")

# Use list_robots_missing_image for staubli-robotics
print("\n=== list_robots_missing_image('staubli-robotics') ===")
try:
    robots = client.list_robots_missing_image('staubli-robotics')
    print(f"  Robots missing image: {len(robots)}")
    for r in robots[:10]:
        print(f"  ID: {r.get('id')} | {r.get('name')}")
except Exception as e:
    print(f"  Error: {e}")

# Also check staubli (company ID 437)
print("\n=== list_robots_for_company('staubli') ===")
try:
    robots = client.list_robots_for_company('staubli')
    print(f"  Total robots: {len(robots)}")
    for r in robots[:10]:
        has_image = bool(r.get('image_url', ''))
        print(f"  ID: {r.get('id')} | {r.get('name')} | Image: {'✓' if has_image else '✗'}")
        if r.get('image_url'):
            print(f"    → {r.get('image_url')[:80]}")
except Exception as e:
    print(f"  Error: {e}")
