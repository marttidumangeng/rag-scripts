#!/usr/bin/env python3
"""Retry Pangolin name fixes for robots that 500 on DRF PATCH."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import resolve_created_by_id

FIXES = {
    2208: "熊猫消杀 (Panda Disinfection)",
    3197: "精灵 (Jingling)",
}


def main() -> int:
    client = ResearchApiClient()
    created_by = resolve_created_by_id(client)
    rows = []
    for rid, name in FIXES.items():
        r = client._get(f"robots/robots/{rid}/")
        rows.append(
            {
                "id": rid,
                "name": name,
                "company_name": "Pangolin Robotics",
                "status": r.get("status") or "published",
            }
        )
    result = client.bulk_import_robots(
        rows,
        patch_existing=True,
        skip_company_update=True,
        created_by_id=created_by,
        status="published",
    )
    print(result)
    for rid, name in FIXES.items():
        r = client._get(f"robots/robots/{rid}/")
        print(rid, repr(r.get("name")), "want", repr(name), "ok" if r.get("name") == name else "MISS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
