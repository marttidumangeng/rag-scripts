"""Dump Nitto Seiko America (1415) pending for enrich."""
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


def main() -> int:
    c = ResearchApiClient()
    co = c._get("companies/1415/")
    print("CO", co.get("name"), co.get("website"), co.get("country"))
    page = 1
    out = []
    while True:
        data = c._get(
            "robots/robots/",
            params={
                "company_ref": 1415,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        if not batch:
            break
        for r in batch:
            full = c._get(f"robots/robots/{r['id']}/")
            out.append(
                {
                    "id": full["id"],
                    "name": full.get("name"),
                    "url": full.get("url"),
                    "feats": (full.get("features") or "")[:200],
                    "feats_len": len(full.get("features") or ""),
                    "purpose": full.get("purpose"),
                    "img": bool(full.get("image") or full.get("s3_image")),
                    "family_key": full.get("family_key"),
                    "avail": full.get("availability_status"),
                }
            )
            print(full["id"], full.get("name"), "url=", full.get("url"), "feats", len(full.get("features") or ""))
        if not data.get("next"):
            break
        page += 1
    Path("staging/reports/nitto-1415-dump.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
