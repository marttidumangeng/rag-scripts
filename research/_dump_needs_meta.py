"""Dump company meta for Needs cleanup IDs via first pending robot."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

IDS = [1369, 1398, 1484, 49, 1206, 810, 974, 1073, 52, 397, 1373, 1322, 1511, 783, 1512, 254]


def main() -> int:
    c = ResearchApiClient()
    # resolve country catalog
    countries = c._get("robots/countries/", params={"page_size": 300})
    rows = countries if isinstance(countries, list) else countries.get("results") or []
    cmap = {r["id"]: r.get("name") or r.get("code") for r in rows}
    print("countries sample", list(cmap.items())[:5])

    for cid in IDS:
        data = c._get(
            "robots/robots/",
            params={"company_ref": cid, "status": "pending_review", "page_size": 2},
        )
        batch = data.get("results") or []
        if not batch:
            data2 = c._get(
                "robots/robots/",
                params={"company_ref": cid, "page_size": 1},
            )
            batch = data2.get("results") or []
        if not batch:
            print(cid, "NO ROBOTS")
            continue
        r = batch[0]
        co = r.get("company") or {}
        if isinstance(co, int):
            co = {"id": co}
        print(
            cid,
            "company=",
            (co.get("name") if isinstance(co, dict) else co),
            "co_country=",
            co.get("country") if isinstance(co, dict) else None,
            "robot_country_ref=",
            r.get("manufacturer_country_ref"),
            "name0=",
            (r.get("name") or "")[:40],
            "url=",
            (r.get("url") or "")[:70],
        )
        # dump keys of interest for one DELTA / Yamaha / Geek
        if cid in (1206, 1484, 1398, 49, 1073):
            detail = c._get(f"robots/robots/{r['id']}/")
            keep = {
                k: detail.get(k)
                for k in (
                    "id",
                    "name",
                    "url",
                    "website_url",
                    "description",
                    "purpose",
                    "features",
                    "payload_kg",
                    "weight_kg",
                    "reach_mm",
                    "availability_status",
                    "manufacturer_country_ref",
                    "manufacturer_countries",
                    "categories",
                    "uses",
                    "industries",
                    "movement_types",
                    "family_key",
                    "family_name",
                    "s3_image",
                    "image",
                )
            }
            print(json.dumps(keep, ensure_ascii=False, default=str)[:800])
            print("---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
