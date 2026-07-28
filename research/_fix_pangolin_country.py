#!/usr/bin/env python3
"""Set Pangolin company + robot manufacturer country to China so QA/approve clears."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

COMPANY_ID = 1413
PENDING_IDS = [
    2172,
    2176,
    2515,
    3497,
    3197,
    2179,
    2185,
    3499,
    3502,
    2189,
    3201,
    3503,
    2208,
    2193,
    2195,
    2203,
    3505,
    3506,
]


def main() -> int:
    client = ResearchApiClient()
    # Company-level country (full name per project convention)
    try:
        client._patch(f"companies/{COMPANY_ID}/", {"country": "China"})
        print("ok company country=China")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL company country: {e}")
        return 1

    ok = fail = 0
    for rid in PENDING_IDS:
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {"manufacturer_country": "China", "manufacturer_country_code": "CN"},
            )
            print(f"ok robot {rid}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL robot {rid}: {e}")
            fail += 1
        time.sleep(0.08)

    co = client._get(f"companies/{COMPANY_ID}/")
    sample = client._get(f"robots/robots/{PENDING_IDS[0]}/")
    print(
        "verify company.country=",
        co.get("country"),
        "sample.mc=",
        sample.get("manufacturer_countries"),
        "sample.country=",
        sample.get("country"),
    )
    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
