"""Dump a lightweight baseline of prod companies + robots for gap dedupe.

Produces staging/reports/prod_baseline.json:
  {
    "generated_at": ISO8601,
    "companies": [{id, name, slug, website}],
    "robots":    [{id, name, model_name, company_id, company_name, family_key}],
    "company_name_index": [normalized names],
    "robot_name_index":   ["companyNorm::robotNorm", ...]
  }

Usage:
  python dump_prod_baseline.py
  python dump_prod_baseline.py --local
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402

OUT = _HERE / "staging" / "reports" / "prod_baseline.json"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def main() -> None:
    client = ResearchApiClient()

    print("Fetching companies ...", flush=True)
    companies: list[dict] = []
    page = 1
    while True:
        for attempt in range(4):
            try:
                data = client._get("companies/", params={"page": page, "page_size": 100})
                break
            except Exception as exc:
                print(f"  companies page {page} attempt {attempt+1} failed: {str(exc)[:120]}")
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"companies page {page} failed after retries")
        batch = data.get("results", [])
        for c in batch:
            companies.append({
                "id": c.get("id"),
                "name": c.get("name") or "",
                "slug": c.get("slug") or "",
                "website": c.get("website") or "",
            })
        print(f"  companies page {page}: +{len(batch)} (total {len(companies)})", flush=True)
        if not data.get("next"):
            break
        page += 1

    print("Fetching robots ...", flush=True)
    robots: list[dict] = []
    page = 1
    while True:
        for attempt in range(5):
            try:
                data = client._get("robots/robots/", params={"page": page, "page_size": 50})
                break
            except Exception as exc:
                print(f"  robots page {page} attempt {attempt+1} failed: {str(exc)[:120]}")
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"robots page {page} failed after retries")
        batch = data.get("results", [])
        for r in batch:
            comp = r.get("company") or {}
            if not isinstance(comp, dict):
                comp = {}
            robots.append({
                "id": r.get("id"),
                "name": r.get("name") or "",
                "model_name": r.get("model_name") or "",
                "company_id": comp.get("id") or r.get("company_ref"),
                "company_name": comp.get("name") or "",
                "family_key": r.get("family_key") or "",
                "status": r.get("status") or "",
            })
        if page % 10 == 0 or not data.get("next"):
            print(f"  robots page {page}: total {len(robots)}", flush=True)
        if not data.get("next"):
            break
        page += 1

    company_name_index = sorted({norm(c["name"]) for c in companies if c["name"]})
    robot_name_index = sorted({
        f"{norm(r['company_name'])}::{norm(k)}"
        for r in robots
        for k in (r["name"], r["model_name"])
        if k
    })

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company_count": len(companies),
        "robot_count": len(robots),
        "companies": companies,
        "robots": robots,
        "company_name_index": company_name_index,
        "robot_name_index": robot_name_index,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT} — {len(companies)} companies, {len(robots)} robots", flush=True)


if __name__ == "__main__":
    main()
