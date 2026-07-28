"""Probe Hikrobot robots in the DB."""
import sys, io, os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).parent))

from api_client import ResearchApiClient

client = ResearchApiClient()
robots = client.list_robots_for_company(204)
print(f"Total Hikrobot robots: {len(robots)}")
for rb in robots:
    name = rb.get('name', '')
    model = rb.get('model_name', '')
    url = rb.get('url', '')
    status = rb.get('status', '')
    print(f"  id={rb['id']} status={status} name={name!r} model={model!r}")
    if url:
        print(f"    url={url!r}")
