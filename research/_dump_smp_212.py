"""Deep dump SMP 212 pending via company_ref (content-queue filter)."""
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
    co = c._get("companies/212/")
    print("COMPANY", co.get("id"), co.get("name"), "web", co.get("website"))
    page = 1
    rows = []
    while True:
        data = c._get(
            "robots/robots/",
            params={
                "company_ref": 212,
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
    # also published for context
    pub = c._get(
        "robots/robots/",
        params={"company_ref": 212, "status": "published", "page_size": 50},
    )
    pubs = pub.get("results") or []
    print(f"pending={len(rows)} published={len(pubs)}")
    for p in pubs:
        print(f"  PUB {p['id']} {p.get('name')}")

    out = []
    for r in rows:
        rid = r["id"]
        full = c._get(f"robots/robots/{rid}/")
        avail = full.get("availability_status")
        if isinstance(avail, dict):
            avail = avail.get("key")
        sources = full.get("information_sources") or full.get("information_source_urls") or []
        item = {
            "id": rid,
            "name": full.get("name"),
            "model_name": full.get("model_name"),
            "variant_code": full.get("variant_code"),
            "url": full.get("url"),
            "family_key": full.get("family_key"),
            "family_name": full.get("family_name"),
            "family_url": full.get("family_url"),
            "availability": avail,
            "feats": (full.get("features") or "")[:200],
            "feats_len": len(full.get("features") or ""),
            "desc": (full.get("description") or "")[:200],
            "purpose": full.get("purpose") or "",
            "img": (full.get("image") or full.get("s3_image") or "")[:120],
            "weight_kg": full.get("weight_kg"),
            "payload_kg": full.get("payload_kg"),
            "speed": full.get("speed"),
            "length_mm": full.get("length_mm"),
            "width_mm": full.get("width_mm"),
            "height_mm": full.get("height_mm"),
            "runtime_minutes": full.get("runtime_minutes"),
            "uses": [
                u.get("key") if isinstance(u, dict) else u for u in (full.get("uses") or [])
            ],
            "industries": [
                i.get("key") if isinstance(i, dict) else i
                for i in (full.get("industries") or [])
            ],
            "tags": full.get("tags") or [],
            "sources_n": len(sources),
            "notes": (full.get("notes") or "")[:120],
        }
        out.append(item)
        soft_gaps = []
        if not avail:
            soft_gaps.append("no_avail")
        if not item["family_key"]:
            soft_gaps.append("no_family")
        if not item["url"]:
            soft_gaps.append("no_url")
        if item["weight_kg"] is None and item["payload_kg"] is None and item["speed"] is None:
            soft_gaps.append("no_typed_specs")
        if item["sources_n"] == 0:
            soft_gaps.append("no_sources")
        print(
            f"{rid} | {item['name']} | avail={avail} | fam={item['family_key']} | "
            f"gaps={soft_gaps or 'ok'} | url={item['url']}"
        )
        print(f"     purpose={item['purpose'][:90]!r}")
    path = _RESEARCH / "staging" / "reports" / "smp-212-dump.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
