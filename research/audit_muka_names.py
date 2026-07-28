"""
audit_muka_names.py
Fetches all MUKA robots from the API and prints their id, name, model_name, and slug
so we can identify which names are SEO titles vs clean product names.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from api_client import ResearchApiClient

client = ResearchApiClient()
robots = client.list_robots_for_company(1480, page_size=100)

print(f"Total MUKA robots: {len(robots)}\n")
print(f"{'ID':<8} {'MODEL':<20} {'NAME'}")
print("-" * 100)
for r in sorted(robots, key=lambda x: x.get('id', 0)):
    rid   = r.get('id', '')
    name  = r.get('name', '')
    model = r.get('model_name', '') or ''
    print(f"{rid:<8} {model:<20} {name}")
