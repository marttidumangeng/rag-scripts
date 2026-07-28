"""
check_staubli_codes.py
Checks the robot_code field for Stäubli robots to understand the public URL pattern.
"""
import json
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

# Get detail for a few Stäubli robots to see all fields including robot_code
print("=== Robot detail check for Stäubli TX2-40 (ID 4625) ===")
try:
    detail = client._get('robots/robots/4625/')
    # Print key fields
    print(f"  id: {detail.get('id')}")
    print(f"  name: {detail.get('name')}")
    print(f"  robot_code: {detail.get('robot_code')}")
    print(f"  slug: {detail.get('slug', 'NOT IN RESPONSE')}")
    print(f"  status: {detail.get('status')}")
    print(f"  image: {detail.get('image')}")
    print(f"  s3_image: {detail.get('s3_image')}")
    print(f"  image_url: {detail.get('image_url')}")
    photos = detail.get('photos', [])
    print(f"  photos count: {len(photos)}")
    for p in photos[:3]:
        print(f"    photo: {p.get('url', '')[:80]}")
    print(f"  company_ref: {detail.get('company_ref')}")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== Check public frontend URL pattern ===")
# The frontend uses robot_code as the URL slug
# Let's check what robot_code looks like for a few robots
robots = client.list_robots_for_company(1475, page_size=20)
print(f"Checking robot_codes for first 10 Stäubli robots:")
for r in robots[:10]:
    robot_id = r.get('id')
    try:
        detail = client._get(f'robots/robots/{robot_id}/')
        code = detail.get('robot_code', 'NONE')
        status = detail.get('status', 'unknown')
        print(f"  ID {robot_id} | {detail.get('name')} | robot_code: {code} | status: {status}")
        print(f"    → Public URL: https://www.robotaigeek.com/robot/{code.lower() if code else 'NONE'}")
    except Exception as e:
        print(f"  ID {robot_id}: Error — {e}")
