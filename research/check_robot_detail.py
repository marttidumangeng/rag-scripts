"""
check_robot_detail.py
Checks the detail endpoint for a specific Stäubli robot to see all image fields.
"""
import json
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

# Check robot ID 4625 (TX2-40) via the detail endpoint
for robot_id in [4625, 4626, 4841]:
    print(f"\n=== Robot ID {robot_id} detail ===")
    try:
        result = client._get(f'robots/robots/{robot_id}/')
        # Print all image-related fields
        image_fields = {k: v for k, v in result.items()
                       if 'image' in k.lower() or 'photo' in k.lower() or 'media' in k.lower()}
        print(f"  Name: {result.get('name')}")
        print(f"  Image fields:")
        for k, v in image_fields.items():
            print(f"    {k}: {str(v)[:100]}")
        # Also print the full response keys
        print(f"  All keys: {list(result.keys())}")
    except Exception as e:
        print(f"  Error: {e}")
