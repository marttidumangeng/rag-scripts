"""Fix Hikrobot robot names in the DB.

Strips the "(Hikrobot)" company suffix and replaces Chinese names with their
English equivalents so the tab extractor can match model codes correctly.

Also sets manufacturer_countries to China (id=3) for all Hikrobot robots
that are missing it.

Usage:
    python3 fix_hikrobot_names.py [--dry-run]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
load_research_env()

from api_client import ResearchApiClient

DRY_RUN = "--dry-run" in sys.argv

# Map of current DB name → corrected name + model_name
# Chinese names are translated to their official English equivalents from hikrobotics.com
NAME_FIXES: dict[str, dict] = {
    # Strip "(Hikrobot)" suffix
    "Q3-600D (Hikrobot)": {
        "name": "Q3-600D",
        "model_name": "Q3-600D",
    },
    "F3-1500 (Hikrobot)": {
        "name": "F3-1500",
        "model_name": "F3-1500",
    },
    # Chinese name → English
    # "Q3S 潜行式清扫机器人" = "Q3S Latent Cleaning Robot" (official: Q3S Latent Lifting AMR)
    "Q3S 潜行式清扫机器人": {
        "name": "Q3S",
        "model_name": "Q3S",
    },
}

# Country fix: all Hikrobot robots should have manufacturer_countries = [China (id=3)]
CHINA_COUNTRY_ID = 3


def main() -> None:
    client = ResearchApiClient()
    robots = client.list_robots_for_company(204)
    print(f"Hikrobot robots: {len(robots)}")

    patched = 0
    skipped = 0
    failed = 0

    for robot in robots:
        rid = robot["id"]
        current_name = robot.get("name", "")
        current_model = robot.get("model_name", "")
        current_countries = robot.get("manufacturer_countries") or []
        status = robot.get("status", "")

        # Only fix draft/pending_review robots
        if status not in ("draft", "pending_review"):
            print(f"  SKIP id={rid} {current_name!r} (status={status})")
            skipped += 1
            continue

        patch: dict = {}

        # Name fix
        if current_name in NAME_FIXES:
            fix = NAME_FIXES[current_name]
            patch["name"] = fix["name"]
            patch["model_name"] = fix["model_name"]
            print(f"  NAME  id={rid} {current_name!r} → {fix['name']!r}")

        # Country fix
        country_ids = [c.get("id") if isinstance(c, dict) else c for c in current_countries]
        if CHINA_COUNTRY_ID not in country_ids:
            patch["manufacturer_countries"] = [CHINA_COUNTRY_ID]
            print(f"  COUNTRY id={rid} {current_name!r} → China")

        if not patch:
            skipped += 1
            continue

        if DRY_RUN:
            print(f"  [DRY-RUN] would patch id={rid}: {patch}")
            patched += 1
            continue

        try:
            client._patch(f"robots/robots/{rid}/", patch)
            patched += 1
            print(f"    \u2192 OK")
        except Exception as exc:
            print(f"  ERROR id={rid}: {exc}")
            failed += 1

    print(f"\nSummary: patched={patched} skipped={skipped} failed={failed}")
    if DRY_RUN:
        print("(dry-run — no changes applied)")


if __name__ == "__main__":
    main()
