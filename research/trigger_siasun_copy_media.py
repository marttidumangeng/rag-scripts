"""Trigger copy-media for SIASUN robots with external en.siasun.com images."""

from fix_siasun_images import COMPANY_ID, trigger_copy_media
from load_env import load_research_env
from api_client import ResearchApiClient

load_research_env()
client = ResearchApiClient()
targets = [
    r for r in client.list_robots_for_company(COMPANY_ID)
    if (r.get("image") or "").startswith("https://en.siasun.com") and not r.get("s3_image")
]
print(f"targets: {len(targets)}")
ok, fail = trigger_copy_media([r["id"] for r in targets])
print(f"done ok={ok} fail={fail}")
