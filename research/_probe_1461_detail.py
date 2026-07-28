"""Dump detailed gaps for Jaten (1461) robots."""
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
import json

c = ResearchApiClient()
robots = list(c.list_robots_for_company(1461))
for r in robots:
    print("=" * 60)
    print(f"id={r['id']} {r['name']}")
    print(f"  url={r.get('url')}")
    print(f"  image={r.get('image')}")
    print(f"  s3_image={r.get('s3_image')}")
    print(f"  description={(r.get('description') or '')[:200]}")
    print(f"  features={(r.get('features') or '')[:300]}")
    print(f"  weight_kg={r.get('weight_kg')} weight={r.get('weight')} dimensions={r.get('dimensions_mm')} dof={r.get('dof')}")
    print(f"  payload={r.get('payload_kg') or r.get('payload')}")
    print(f"  tags={r.get('tags') or r.get('tag_names')}")
    print(f"  videos={r.get('videos')}")
    # extra keys that might help
    for k in ("model_name", "price", "reach_mm", "speed", "battery", "notes", "research_notes"):
        v = r.get(k)
        if v:
            print(f"  {k}={str(v)[:150]}")
