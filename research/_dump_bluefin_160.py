"""Dump Bluefin (160) pending + published for enrich planning."""
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

CID = 160


def main() -> int:
    c = ResearchApiClient()
    co = c._get(f"companies/{CID}/")
    print("COMPANY", co.get("id"), co.get("name"), "web", co.get("website"))
    country = co.get("country") or {}
    print("country", country.get("code") if isinstance(country, dict) else country)

    for status in ("pending_review", "published", "rejected"):
        data = c._get(
            "robots/robots/",
            params={"company_ref": CID, "status": status, "page_size": 50},
        )
        rows = data.get("results") or []
        print(f"\n=== {status} count={data.get('count')} n={len(rows)}")
        out = []
        for r in rows:
            rid = r["id"]
            full = c._get(f"robots/robots/{rid}/")
            avail = full.get("availability_status")
            if isinstance(avail, dict):
                avail = avail.get("key")
            item = {
                "id": rid,
                "name": full.get("name"),
                "url": full.get("url"),
                "family_key": full.get("family_key"),
                "availability": avail,
                "feats_len": len(full.get("features") or ""),
                "purpose": (full.get("purpose") or "")[:100],
                "desc": (full.get("description") or "")[:140],
                "img": bool(full.get("image") or full.get("s3_image")),
                "weight_kg": full.get("weight_kg"),
                "payload_kg": full.get("payload_kg"),
                "speed": full.get("speed"),
                "length_mm": full.get("length_mm"),
                "uses": [
                    u.get("key") if isinstance(u, dict) else u for u in (full.get("uses") or [])
                ],
                "tags": full.get("tags") or [],
            }
            out.append(item)
            print(
                f"{rid} | {item['name']} | avail={avail} | fam={item['family_key']} | "
                f"feats={item['feats_len']} img={item['img']} | url={item['url']}"
            )
            print(f"     purpose={item['purpose']!r}")
        if status == "pending_review":
            path = _RESEARCH / "staging" / "reports" / "bluefin-160-dump.json"
            path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
            print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
