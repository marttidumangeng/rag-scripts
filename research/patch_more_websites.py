"""Patch website URLs for companies that are missing them."""
import sys
sys.path.insert(0, '.')
from api_client import ResearchApiClient

client = ResearchApiClient()

patches = [
    (1474, 'https://www.rprobotic.com'),
    (1434, 'https://ep-equipment.com'),
    (1411, 'https://robotics.omron.com'),
]

for cid, url in patches:
    try:
        r = client._patch(f'companies/{cid}/', {'website': url})
        print(f'Company {cid}: website set to {r.get("website", "ERROR")}')
    except Exception as e:
        print(f'Company {cid}: FAILED - {e}')
