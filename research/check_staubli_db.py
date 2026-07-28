"""
check_staubli_db.py
Checks the RobotAIGeek database for Stäubli company record and robot profiles,
verifying images are correctly set.
"""
import json
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

# 1. Find the Stäubli company record
print("=== Searching for Stäubli company ===")
try:
    result = client._get('/companies/', params={'search': 'staubli', 'page_size': 10})
    companies = result.get('results', result) if isinstance(result, dict) else result
    for c in companies[:5]:
        print(f"  ID: {c.get('id')} | Slug: {c.get('slug')} | Name: {c.get('name')}")
except Exception as e:
    print(f"  Error: {e}")

# 2. Find robots for company_id 1475
print("\n=== Robots for company_id=1475 (first 10) ===")
try:
    result = client._get('/robots/', params={'company': 1475, 'page_size': 10})
    if isinstance(result, dict):
        robots = result.get('results', [])
    elif isinstance(result, list):
        robots = result
    else:
        robots = []
    for r in robots:
        has_image = bool(r.get('image_url', ''))
        slug = r.get('slug', r.get('id', '?'))
        print(f"  ID: {r.get('id')} | Slug: {slug} | Name: {r.get('name')} | Image: {'\u2713' if has_image else '\u2717'}")
        print(f"    image_url: {r.get('image_url', 'NONE')[:80]}")
except Exception as e:
    print(f"  Error: {e}")

# 3. Try a direct robot lookup for TX2-40
print("\n=== Searching for TX2-40 robot ===")
try:
    result = client._get('/robots/', params={'search': 'TX2-40', 'page_size': 5})
    if isinstance(result, dict):
        robots = result.get('results', [])
    elif isinstance(result, list):
        robots = result
    else:
        robots = []
    for r in robots:
        has_image = bool(r.get('image_url', ''))
        print(f"  ID: {r.get('id')} | Slug: {r.get('slug')} | Company: {r.get('company_name', r.get('company'))} | Image: {'\u2713' if has_image else '\u2717'}")
        print(f"    image_url: {r.get('image_url', 'NONE')[:80]}")
except Exception as e:
    print(f"  Error: {e}")
