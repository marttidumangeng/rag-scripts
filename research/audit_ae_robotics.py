#!/usr/bin/env python3
"""Audit AE Robotics (1375) robots: check country, description length, price.
Also scrapes product pages to gather richer descriptions and specs.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
load_research_env()

from api_client import ResearchApiClient

COMPANY_ID = 1375
REPORT_DIR = _HERE / "staging" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def list_company_robots(client: ResearchApiClient, company_id: int) -> list[dict]:
    rows = []
    page = 1
    while True:
        data = client._get("robots/robots/", params={"company_ref": company_id, "page": page, "page_size": 50})
        batch = data.get("results") or []
        rows.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1
        time.sleep(0.1)
    return rows


def main() -> None:
    client = ResearchApiClient()
    robots = list_company_robots(client, COMPANY_ID)
    print(f"Total robots: {len(robots)}")
    print()

    issues = []
    for r in robots:
        rid = r["id"]
        name = r.get("name", "")
        mc = r.get("manufacturer_countries") or []
        desc = r.get("description") or ""
        price_min = r.get("price_min")
        price_max = r.get("price_max")
        price = r.get("price")
        features = r.get("features") or ""
        tags = r.get("tags") or []
        payload = r.get("payload_kg")
        reach = r.get("reach_mm")
        dof = r.get("dof")
        status = r.get("status")
        url = r.get("url") or ""

        robot_issues = []
        if not mc:
            robot_issues.append("no_country")
        if len(desc) < 100:
            robot_issues.append(f"short_desc({len(desc)})")
        if not price_min and not price_max and not price:
            robot_issues.append("no_price")
        if not features:
            robot_issues.append("no_features")
        if not tags:
            robot_issues.append("no_tags")
        if not payload and not reach and not dof:
            robot_issues.append("no_specs")

        print(
            f"{rid:5d} | {status:14s} | {name[:38]:38s} | "
            f"country={'✓' if mc else '✗'} | "
            f"desc={len(desc):3d} | "
            f"price={'✓' if (price_min or price_max or price) else '✗'} | "
            f"issues={robot_issues}"
        )
        issues.append({
            "id": rid,
            "name": name,
            "status": status,
            "url": url,
            "manufacturer_countries": mc,
            "desc_len": len(desc),
            "has_price": bool(price_min or price_max or price),
            "has_features": bool(features),
            "has_tags": bool(tags),
            "payload_kg": payload,
            "reach_mm": reach,
            "dof": dof,
            "issues": robot_issues,
        })

    no_country = [r for r in issues if "no_country" in r["issues"]]
    short_desc = [r for r in issues if any("short_desc" in i for i in r["issues"])]
    no_price = [r for r in issues if "no_price" in r["issues"]]

    print()
    print(f"No country: {len(no_country)}")
    print(f"Short description (<100 chars): {len(short_desc)}")
    print(f"No price: {len(no_price)}")

    out = REPORT_DIR / "audit-ae-robotics-1375.json"
    out.write_text(json.dumps(issues, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
