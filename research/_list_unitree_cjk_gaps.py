#!/usr/bin/env python3
"""List Unitree robots with CJK/short features and remaining QA gaps."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
COMPANY_ID = 109


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    client = ResearchApiClient()
    robots = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={"company_ref": COMPANY_ID, "page": page, "page_size": 20},
        )
        robots.extend(data.get("results") or [])
        if not data.get("next"):
            break
        page += 1

    rows = []
    for r in robots:
        feats = r.get("features") or ""
        if isinstance(feats, list):
            feats = "\n".join(str(x) for x in feats)
        purpose = r.get("purpose") or ""
        desc = r.get("description") or ""
        flags = []
        if CJK.search(feats):
            flags.append("cjk_features")
        if len(feats.strip()) < 40:
            flags.append("short_features")
        if CJK.search(purpose):
            flags.append("cjk_purpose")
        if CJK.search(desc):
            flags.append("cjk_description")
        if not any(
            r.get(k)
            for k in ("weight_kg", "payload_kg", "height_mm", "speed", "battery_capacity", "dof")
        ):
            flags.append("missing_specs")
        if not (r.get("website_url") or r.get("url")):
            flags.append("missing_url")
        if flags:
            rows.append(
                {
                    "id": r["id"],
                    "name": r.get("name"),
                    "status": r.get("status"),
                    "url": r.get("website_url") or r.get("url"),
                    "resolved_language": r.get("resolved_language"),
                    "features_preview": feats[:100],
                    "flags": flags,
                }
            )

    out = {
        "count": len(robots),
        "flagged": len(rows),
        "rows": rows,
    }
    path = Path(__file__).resolve().parent / "staging" / "reports" / "unitree_cjk_gaps.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(robots), "flagged": len(rows)}, indent=2))
    for row in rows:
        print(f"{row['id']}\t{row['name']}\t{row['flags']}\t{row['features_preview'][:60]}")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
