"""Patch missing manufacturer country on company 1602 robots (China=3)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1602
CN_COUNTRY_ID = 3


def has_country(robot: dict) -> bool:
    """Queue 'No country' checks manufacturer_country_ref_id only (not M2M)."""
    ref = robot.get("manufacturer_country_ref")
    if isinstance(ref, dict):
        return bool(ref.get("id"))
    return bool(ref)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    missing = []
    for r in client.list_robots_for_company(COMPANY_ID):
        full = client._get(f"robots/robots/{r['id']}/")
        if has_country(full):
            continue
        missing.append(
            {
                "id": full["id"],
                "name": full.get("name"),
                "status": full.get("status"),
            }
        )
        print(f"MISSING {full['id']} {full.get('status')} {full.get('name')}")

    print(f"total missing: {len(missing)}")
    if not args.apply:
        print("Re-run --apply to patch China (id=3)")
        return 0

    for row in missing:
        rid = row["id"]
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "manufacturer_countries": [CN_COUNTRY_ID],
                    "manufacturer_country_ref": CN_COUNTRY_ID,
                },
            )
            print(f"patched {rid}")
        except Exception as exc:
            print(f"FAIL {rid}: {exc}", file=sys.stderr)
            return 1

    # verify
    still = []
    for row in missing:
        full = client._get(f"robots/robots/{row['id']}/")
        if not has_country(full):
            still.append(row["id"])
    print(f"still missing after patch: {still}")
    return 1 if still else 0


if __name__ == "__main__":
    raise SystemExit(main())
