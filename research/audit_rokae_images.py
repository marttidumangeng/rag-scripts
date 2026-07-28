"""
audit_rokae_images.py
---------------------
Audit the current photos for the 15 ROKAE robots with bad primary images.
For each robot, list all photos (primary + gallery) so we can identify
which secondary images are usable product shots.

Output: staging/reports/rokae_image_audit.json
"""
from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

# Robot names as reported by the user (bad primary images)
BAD_IMAGE_ROBOT_NAMES = [
    "CR7-7/0.98C",
    "CR12-12/1.4C",
    "CR18-18/1.0C",
    "CR20-20/1.8C",
    "CR20-25/1.8C-5",
    "CR20-17/2.0C-5",
    "CR35-35/2.2C",
    "CR35-45/1.9C",
    "SR3-3/0.7C",
    "SR5-5/0.9C",
    "SR3-C-H",
    "ER3",
    "ER3 Pro-M",
    "ER7 Pro-M",
    "ROKAE CR20-17/2.0C-5",  # blurry variant
]

COMPANY_ID = 1416

def main():
    client = ResearchApiClient()
    
    print(f"Fetching all robots for company {COMPANY_ID}...")
    robots = client.list_robots_for_company(COMPANY_ID)
    print(f"  Total robots: {len(robots)}")
    
    # Build a lookup by name
    robot_by_name = {r["name"]: r for r in robots}
    
    results = []
    for name in BAD_IMAGE_ROBOT_NAMES:
        robot = robot_by_name.get(name)
        if not robot:
            # Try partial match
            matches = [r for r in robots if name.lower() in r["name"].lower()]
            if matches:
                robot = matches[0]
                print(f"  [partial match] '{name}' -> '{robot['name']}' (id={robot['id']})")
            else:
                print(f"  [NOT FOUND] '{name}'")
                results.append({"name": name, "id": None, "error": "not_found"})
                continue
        
        rid = robot["id"]
        # Fetch full robot detail to get photos
        detail = client._get(f"robots/robots/{rid}/")
        
        primary_image = detail.get("image") or detail.get("s3_image") or ""
        photos = detail.get("photos") or []
        
        # Summarise photos
        photo_list = []
        for p in photos:
            photo_list.append({
                "id": p.get("id"),
                "url": p.get("url") or p.get("s3_image") or "",
                "is_primary": p.get("is_primary", False),
                "order": p.get("order", 0),
                "status": p.get("status", ""),
            })
        
        # Sort by order
        photo_list.sort(key=lambda x: x["order"])
        
        print(f"  [{rid}] {robot['name']}: primary={bool(primary_image)}, photos={len(photo_list)}")
        for p in photo_list:
            flag = " <-- PRIMARY" if p["is_primary"] else ""
            print(f"         [{p['id']}] order={p['order']} {p['url'][:80]}{flag}")
        
        results.append({
            "id": rid,
            "name": robot["name"],
            "primary_image": primary_image,
            "photos": photo_list,
            "product_url": detail.get("url") or "",
        })
    
    out_path = os.path.join(os.path.dirname(__file__), "staging", "reports", "rokae_image_audit.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nAudit saved to {out_path}")

if __name__ == "__main__":
    main()
