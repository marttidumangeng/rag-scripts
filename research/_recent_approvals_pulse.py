#!/usr/bin/env python3
"""Find recently published robots grouped by company (stakeholder approve pulse)."""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

# Companies already cleared in this session / checklist — skip noise
SKIP = {109, 1028, 239, 1396, 882, 1413, 192, 131, 14, 9, 92, 237, 1369}


def parse_ts(v: str | None):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def main() -> int:
    c = ResearchApiClient()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    by_co: dict[int, dict] = {}
    page = 1
    scanned = 0
    while page <= 30:
        data = c._get(
            "robots/robots/",
            params={"status": "published", "page": page, "page_size": 100, "ordering": "-published_at"},
        )
        results = data.get("results") if isinstance(data, dict) else data
        if not results:
            break
        stop = False
        for r in results:
            scanned += 1
            ts = parse_ts(r.get("published_at")) or parse_ts(r.get("reviewed_at"))
            if ts and ts < cutoff:
                stop = True
                break
            cref = r.get("company_ref") or {}
            if isinstance(cref, dict):
                cid = cref.get("id")
                cname = cref.get("name") or "?"
            else:
                cid = r.get("company")
                cname = str(cid)
            if not cid:
                continue
            cid = int(cid)
            entry = by_co.setdefault(
                cid,
                {"id": cid, "name": cname, "n": 0, "latest": None, "samples": []},
            )
            entry["n"] += 1
            if entry["latest"] is None or (ts and (entry["latest"] is None or ts > entry["latest"])):
                entry["latest"] = ts
            if len(entry["samples"]) < 3:
                entry["samples"].append(f"{r.get('id')}:{r.get('name')}")
        if stop or not (isinstance(data, dict) and data.get("next")):
            break
        page += 1

    rows = sorted(by_co.values(), key=lambda x: x["latest"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    print(f"scanned={scanned} companies_with_recent_publish={len(rows)} cutoff={cutoff.isoformat()}")
    for e in rows:
        flag = " (already cleared)" if e["id"] in SKIP else ""
        latest = e["latest"].isoformat() if e["latest"] else "?"
        print(f"  co {e['id']:4d} {e['name'][:40]:40} n≈{e['n']:3d} latest={latest}{flag}")
        print(f"       samples: {', '.join(e['samples'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
