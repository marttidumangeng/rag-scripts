"""verify_muka_images.py — Check that all MUKA robots now have images set."""
from __future__ import annotations
import os, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

client = ResearchApiClient()
robots = client.list_robots_for_company(1480)
total = len(robots)
with_image = [r for r in robots if r.get("image") or r.get("image_url")]
without = [r for r in robots if not r.get("image") and not r.get("image_url")]

print(f"Company: Xiamen MUKA (1480)")
print(f"Total robots: {total}")
print(f"With image:   {len(with_image)}")
print(f"Without image:{len(without)}")
if without:
    print("\nStill missing images:")
    for r in without:
        print(f"  ID={r.get('id')} name={r.get('name','')[:50]}")
else:
    print("\nAll robots have images!")
