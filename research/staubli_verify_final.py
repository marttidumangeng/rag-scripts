"""
staubli_verify_final.py
Checks all Stäubli robots (company_id=1475) to confirm the image field is now set.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

client = ResearchApiClient()
robots = client.list_robots_for_company(1475)

has_image = 0
no_image = 0
no_image_list = []

for r in robots:
    rid = r.get("id")
    name = r.get("name", "")
    image = r.get("image") or r.get("image_url") or ""
    photos = r.get("photos", [])
    if image or photos:
        has_image += 1
    else:
        no_image += 1
        no_image_list.append(f"  id={rid} {name!r}")

print(f"Total robots: {len(robots)}")
print(f"With image:   {has_image}")
print(f"No image:     {no_image}")
if no_image_list:
    print("Still missing images:")
    for line in no_image_list:
        print(line)
else:
    print("\nAll 45 Stäubli robots now have images!")

# Show a sample of 5 robots with their image URLs
print("\nSample (first 5 robots with images):")
count = 0
for r in robots:
    image = r.get("image") or r.get("image_url") or ""
    photos = r.get("photos", [])
    photo_url = photos[0].get("url", "") if photos else ""
    display = image or photo_url
    if display:
        print(f"  id={r['id']} {r['name']!r}")
        print(f"    image field: {r.get('image') or 'None'}")
        print(f"    photos[0]:   {photo_url or 'None'}")
        count += 1
        if count >= 5:
            break
