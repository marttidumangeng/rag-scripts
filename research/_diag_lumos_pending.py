"""Diagnose Lumos 70 pending that didn't publish."""
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
    code = size = None
    if img:
        r = requests.get(img, timeout=20)
        code, size = r.status_code, len(r.content)
    print(
        f"{rid} {d.get('name')}: status={d.get('status')} "
        f"countries={bool(d.get('manufacturer_countries'))} "
        f"cat={bool(d.get('categories'))} uses={bool(d.get('uses'))} "
        f"feat={len(d.get('features') or '')} "
        f"img={code}/{size} {(img or '')[:90]}"
    )
