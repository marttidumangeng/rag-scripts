"""
check_staubli_final.py
Uses the correct integer company_id parameter for list_robots_for_company.
"""
import json
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

# Use list_robots_for_company with integer company IDs
print("=== list_robots_for_company(1475) — Stäubli Robotics ===")
try:
    robots = client.list_robots_for_company(1475, page_size=100)
    print(f"  Total robots: {len(robots)}")
    missing_image = []
    has_image = []
    for r in robots:
        img = r.get('image_url', '')
        if img:
            has_image.append(r)
        else:
            missing_image.append(r)

    print(f"  With image: {len(has_image)}")
    print(f"  Missing image: {len(missing_image)}")

    if has_image:
        print("\n  Robots WITH images:")
        for r in has_image[:30]:
            print(f"    ID: {r.get('id')} | {r.get('name')} | {r.get('image_url', '')[:70]}")

    if missing_image:
        print("\n  Robots MISSING images:")
        for r in missing_image[:30]:
            print(f"    ID: {r.get('id')} | {r.get('name')}")

except Exception as e:
    print(f"  Error: {e}")

print("\n=== list_robots_for_company(437) — Stäubli ===")
try:
    robots = client.list_robots_for_company(437, page_size=100)
    print(f"  Total robots: {len(robots)}")
    for r in robots[:10]:
        img = r.get('image_url', '')
        print(f"  ID: {r.get('id')} | {r.get('name')} | Image: {'✓' if img else '✗'}")
        if img:
            print(f"    → {img[:70]}")
except Exception as e:
    print(f"  Error: {e}")
