"""
verify_staubli_images.py
Verifies that all 45 Stäubli Robotics robots now have images in the database.
"""
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

print("=== Verifying Stäubli Robotics image status ===")
robots = client.list_robots_for_company(1475, page_size=100)
print(f"Total robots: {len(robots)}")

with_image = [r for r in robots if r.get('image_url', '')]
without_image = [r for r in robots if not r.get('image_url', '')]

print(f"✓ With image:    {len(with_image)}")
print(f"✗ Without image: {len(without_image)}")

if with_image:
    print("\nSample robots with images (first 10):")
    for r in with_image[:10]:
        slug = r.get('slug', r.get('id'))
        print(f"  ID {r.get('id')} | {r.get('name')} | slug: {slug}")
        print(f"    → {r.get('image_url', '')[:80]}")

if without_image:
    print("\nRobots still missing images:")
    for r in without_image:
        print(f"  ID {r.get('id')} | {r.get('name')}")
