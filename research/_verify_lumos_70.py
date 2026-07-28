"""Confirm typed specs stuck on Lumos 70."""
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
for rid in (5290, 5291, 5292, 5293, 5294):
    d = c._get(f"robots/robots/{rid}/")
    img = d.get("s3_image") or d.get("image") or ""
    r = requests.get(img, timeout=25)
    print(
        f"{rid} fam={d.get('family_key')} cn={bool(d.get('manufacturer_countries'))} "
        f"avail={d.get('availability_status')} cat={bool(d.get('categories'))} "
        f"uses={bool(d.get('uses'))} feat={len(d.get('features') or '')} "
        f"pay={d.get('payload_kg')} w={d.get('weight_kg')} dof={d.get('dof')} "
        f"spd={d.get('speed')} reach={d.get('reach_mm')} torq={d.get('joint_torque_nm')} "
        f"LWH={d.get('length_mm')}/{d.get('width_mm')}/{d.get('height_mm')} "
        f"img={r.status_code}/{len(r.content)}"
    )
    print(f"  purpose={(d.get('purpose') or '')[:100]!r}")
