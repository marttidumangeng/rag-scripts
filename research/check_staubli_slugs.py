"""
check_staubli_slugs.py
Gets the slugs for all Stäubli robots so we can check their public URLs.
"""
import json
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

robots = client.list_robots_for_company(1475, page_size=100)
print(f"Total: {len(robots)} robots\n")
print("Slugs and photo status:")
for r in robots[:15]:
    robot_id = r.get('id')
    # Get detail to check photos
    try:
        detail = client._get(f'robots/robots/{robot_id}/')
        photos = detail.get('photos', [])
        slug = detail.get('slug', '')
        name = detail.get('name', '')
        photo_urls = [p.get('url', '')[:60] for p in photos[:2]]
        print(f"  ID {robot_id} | slug: {slug} | photos: {len(photos)}")
        for url in photo_urls:
            print(f"    → {url}")
    except Exception as e:
        print(f"  ID {robot_id}: Error — {e}")
