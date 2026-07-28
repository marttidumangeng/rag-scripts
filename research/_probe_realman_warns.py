#!/usr/bin/env python3
"""Snapshot Realman 882 soft-warn fields (photos / year / price)."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient


def fetch(client: ResearchApiClient, status: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": 882,
                "status": status,
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        rows.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1
    return rows


def main() -> int:
    client = ResearchApiClient()
    pending = fetch(client, "pending_review")
    published = fetch(client, "published")
    out = []
    for r in pending + published:
        imgs = r.get("images") or []
        n = (
            len(imgs)
            if isinstance(imgs, list) and imgs
            else (1 if (r.get("s3_image") or r.get("image")) else 0)
        )
        out.append(
            {
                "id": r["id"],
                "name": r.get("name"),
                "status": r.get("status"),
                "photos": n,
                "year": r.get("release_year"),
                "price_min": r.get("price_min"),
                "price_max": r.get("price_max"),
                "price_range": r.get("price_range"),
                "url": r.get("url"),
                "model_name": r.get("model_name"),
            }
        )
    Path("staging/reports/_realman_warn_snapshot.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    pend = [x for x in out if x["status"] == "pending_review"]
    print(f"pending={len(pend)} published={len(published)}")
    print("photo counts", dict(Counter(x["photos"] for x in pend)))
    print("missing year", sum(1 for x in pend if not x["year"]))
    print(
        "missing price",
        sum(
            1
            for x in pend
            if not (x["price_min"] or x["price_max"] or x["price_range"])
        ),
    )
    for x in sorted(pend, key=lambda z: z["id"]):
        print(
            f"{x['id']:>5} ph={x['photos']} year={x['year']} "
            f"price={x['price_min'] or x['price_range'] or '-'}  {x['name']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
