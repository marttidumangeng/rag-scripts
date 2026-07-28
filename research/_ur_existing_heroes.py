"""List existing Universal Robots heroes already on company 192."""

from __future__ import annotations

import sys
import time
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient


def main() -> int:
    client = ResearchApiClient()
    robots = client.list_robots_for_company(192)
    for r in sorted(robots, key=lambda x: int(x["id"])):
        img = (r.get("image") or r.get("s3_image") or "").strip()
        if not img:
            continue
        print(f"{r['id']} {r.get('name')}")
        print(f"  {img}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
