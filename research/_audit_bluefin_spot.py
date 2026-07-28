"""Spot-check Bluefin 160 for Approve presentation."""
from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

IDS = [3607, 5043, 3608, 197, 5044]


def main() -> int:
    c = ResearchApiClient()
    for rid in IDS:
        r = c._get(f"robots/robots/{rid}/")
        avail = r.get("availability_status")
        if isinstance(avail, dict):
            avail = avail.get("key")
        img = (r.get("image") or r.get("s3_image") or "")[:90]
        print(
            f"{rid} | {r.get('name')} | status={r.get('status')} | avail={avail} | "
            f"fam={r.get('family_key')} | wt={r.get('weight_kg')} spd={r.get('speed')} | "
            f"feats={len(r.get('features') or '')} | img={img}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
