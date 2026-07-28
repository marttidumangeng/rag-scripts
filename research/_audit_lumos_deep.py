"""Deep gap audit Lumos Robotics (70)."""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
for r in sorted(c.list_robots_for_company(70) or [], key=lambda x: x["id"]):
    d = c._get(f"robots/robots/{r['id']}/")
    img = d.get("s3_image") or d.get("image") or ""
    code = size = None
    if img:
        try:
            resp = requests.get(img, timeout=20)
            code, size = resp.status_code, len(resp.content)
        except Exception as e:
            code, size = "ERR", str(e)
    purpose = d.get("purpose") or ""
    desc = d.get("description") or ""
    print(f"\n=== {r['id']} {r.get('name')} ===")
    print(f"  status={d.get('status')} avail={d.get('availability_status')}")
    print(f"  img http={code} bytes={size} {(img or '')[:90]}")
    print(f"  feat={len(d.get('features') or '')} countries={bool(d.get('manufacturer_countries'))}")
    print(f"  cat={bool(d.get('categories'))} uses={bool(d.get('uses'))} tags={len(d.get('tags') or [])}")
    print(f"  family={d.get('family_key')!r} model={d.get('model_name')!r}")
    print(f"  url={(d.get('url') or '')[:90]}")
    print(f"  payload={d.get('payload_kg')} weight={d.get('weight_kg')} speed={d.get('speed')} dof={d.get('dof')}")
    print(f"  dims={d.get('length_mm')}x{d.get('width_mm')}x{d.get('height_mm')} year={d.get('release_year')}")
    print(f"  purpose={purpose[:120]!r}")
    print(f"  desc={desc[:120]!r}")
    print(f"  purpose~desc={purpose.strip()[:80]==desc.strip()[:80] if purpose and desc else False}")
