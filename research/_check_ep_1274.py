"""Spot-check EP 1274 after apply."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
for r in sorted(c.list_robots_for_company(1274), key=lambda x: -x["id"]):
    img = bool(r.get("s3_image") or r.get("image"))
    avail = r.get("availability_status")
    if isinstance(avail, dict):
        avail = f"{avail.get('id')}:{avail.get('key')}"
    print(
        f"{r['id']}|{r['name']}|{r.get('status')}|img={img}|"
        f"pay={r.get('payload_kg')}|fk={r.get('family_key')}|"
        f"scope={r.get('product_url_scope')}|avail={avail}|"
        f"feat={len(r.get('features') or '')}"
    )
