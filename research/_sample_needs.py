"""Sample one pending robot per Needs cleanup company."""
from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

IDS = [1484, 1398, 49, 1206, 810, 974, 1073, 52, 397, 1373, 1322, 1511, 783, 1512, 254]


def main() -> int:
    c = ResearchApiClient()
    for cid in IDS:
        d = c._get(
            "robots/robots/",
            params={"company_ref": cid, "status": "pending_review", "page_size": 1},
        )
        r = (d.get("results") or [None])[0]
        if not r:
            print(cid, "empty")
            continue
        detail = c._get(f"robots/robots/{r['id']}/")
        co = detail.get("company")
        print("---", cid, detail.get("name"))
        print("  company", co)
        print(
            "  country_ref",
            detail.get("manufacturer_country_ref"),
            "countries",
            detail.get("manufacturer_countries"),
        )
        print("  uses", detail.get("uses"))
        print("  cats", detail.get("categories"))
        print("  fam", detail.get("family_key"), detail.get("family_name"))
        print("  url", (detail.get("url") or "")[:90])
        print("  avail", detail.get("availability_status"))
        print("  img", bool(detail.get("s3_image") or detail.get("image")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
