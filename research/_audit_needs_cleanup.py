"""Audit Needs cleanup companies' pending robots."""
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

COMPANIES = [
    (1369, "ACY Automation"),
    (1398, "Geek+"),
    (1484, "Yamaha Robotics"),
    (49, "Hyundai Robotics"),
    (1206, "DELTA Electronics"),
    (810, "Mujin"),
    (974, "Gurki"),
    (1073, "Intamsys"),
    (52, "Intuitive Surgical"),
    (397, "inVia Robotics"),
    (1373, "6 River Systems"),
    (1322, "AGV Network"),
    (1511, "Auris Health"),
    (783, "Infinium Robotics"),
    (1512, "Jiangsu DINGS"),
    (254, "Plus One Robotics"),
]


def list_pending(client: ResearchApiClient, cid: int) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": cid,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        if not batch:
            break
        rows.extend(batch)
        if not data.get("next"):
            break
        page += 1
    return rows


def gaps(r: dict) -> list[str]:
    g = []
    if not (r.get("s3_image") or r.get("image")):
        g.append("no_image")
    if not (r.get("manufacturer_country_ref") or r.get("manufacturer_country")):
        g.append("no_country")
    if not (r.get("uses") or []):
        g.append("no_uses")
    if not (r.get("categories") or []):
        g.append("no_categories")
    if not (r.get("family_key") or "").strip():
        g.append("no_family")
    if not (r.get("purpose") or "").strip():
        g.append("no_purpose")
    return g


def main() -> int:
    client = ResearchApiClient()
    report = []
    for cid, name in COMPANIES:
        rows = list_pending(client, cid)
        gap_counts: dict[str, int] = {}
        for r in rows:
            for g in gaps(r):
                gap_counts[g] = gap_counts.get(g, 0) + 1
        entry = {
            "id": cid,
            "name": name,
            "pending": len(rows),
            "gaps": gap_counts,
            "robots": [
                {
                    "id": r["id"],
                    "name": r.get("name"),
                    "url": r.get("url"),
                    "gaps": gaps(r),
                    "family_key": r.get("family_key"),
                    "has_image": bool(r.get("s3_image") or r.get("image")),
                }
                for r in rows
            ],
        }
        report.append(entry)
        print(f"=== {cid} {name} pending={len(rows)} gaps={gap_counts} ===")
        for r in rows[:5]:
            print(f"  {r['id']} {(r.get('name') or '')[:50]} {gaps(r)}")
        if len(rows) > 5:
            print(f"  ... +{len(rows) - 5} more")

    out = _RESEARCH / "staging" / "reports" / "needs-cleanup-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
