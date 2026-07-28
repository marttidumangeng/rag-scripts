"""Rethink Robotics (195): OEM site dead; replace aggregator URLs; mark discontinued.

Catalog reality: Baxter + Sawyer only historically. URG no longer lists Rethink products.
Website rethinkrobotics.com returns empty even with stealth.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 195
US = 20
# discontinued availability PK used elsewhere (Cassie)
DISCONTINUED = 4
WIKI = "https://en.wikipedia.org/wiki/Rethink_Robotics"

ROBOTS = [
    {
        "id": 5315,
        "name": "Baxter",
        "model_name": "Baxter",
        "release_year": 2012,
        "url": WIKI,
        "notes": (
            "[AI Research] Rethink OEM site offline (2026-07-19). Replaced robotsguide.com "
            "aggregator URL with Wikipedia company/product reference. Baxter discontinued "
            "after 2018 bankruptcy / HAHN IP sale. No new catalog SKUs on URG."
        ),
    },
    {
        "id": 5316,
        "name": "Sawyer",
        "model_name": "Sawyer",
        "release_year": 2015,
        "url": WIKI,
        "notes": (
            "[AI Research] Rethink OEM site offline (2026-07-19). Replaced robotsguide.com "
            "aggregator URL with Wikipedia company/product reference. Sawyer discontinued "
            "after HAHN/URG wind-down. No live PDP; keep owned CDN hero."
        ),
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    client = ResearchApiClient()
    report = []
    for spec in ROBOTS:
        body = {
            "url": spec["url"],
            "model_name": spec["model_name"],
            "release_year": spec["release_year"],
            "availability_status": DISCONTINUED,
            "manufacturer_countries": [US],
            "manufacturer_country_ref": US,
            "notes": spec["notes"],
            "source_locale": "en",
            "information_source_urls": [WIKI],
        }
        print(f"{spec['name']} ({spec['id']}) → {spec['url']}")
        if args.apply:
            r = client._patch(f"robots/robots/{spec['id']}/", body)
            report.append(
                {
                    "id": spec["id"],
                    "name": r.get("name"),
                    "url": r.get("url"),
                    "availability": r.get("availability_status"),
                }
            )
            print("  patched")
        else:
            report.append({"id": spec["id"], "dry": body})
    out = _RESEARCH / "staging" / "reports" / "rethink-enrich.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Report", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
