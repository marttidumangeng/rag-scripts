"""Export full pending names for overnight family mapping."""
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

IDS = [1398, 1484, 49, 1206, 810, 974, 1073, 52, 397, 1373, 1322, 1511, 783, 1512, 254]


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


def main() -> int:
    c = ResearchApiClient()
    out = {}
    for cid in IDS:
        rows = list_pending(c, cid)
        out[str(cid)] = [
            {
                "id": r["id"],
                "name": r.get("name"),
                "url": r.get("url"),
                "has_image": bool(r.get("s3_image") or r.get("image")),
                "image": r.get("s3_image") or r.get("image"),
            }
            for r in rows
        ]
        print(f"=== {cid} ({len(rows)}) ===")
        for r in rows:
            print(f"  {r['id']}|{r.get('name')}|img={bool(r.get('s3_image') or r.get('image'))}")
    path = _RESEARCH / "staging" / "reports" / "needs-cleanup-names.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
