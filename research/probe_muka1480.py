"""Probe company 1480 (Xiamen MUKA) for content-queue enrich."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from web_extract import WebFetcher

COMPANY_ID = 1480
OUT = _RESEARCH_DIR / "staging" / "reports" / "muka1480_probe.json"


def main() -> int:
    client = ResearchApiClient()
    try:
        co = client._get(f"companies/companies/{COMPANY_ID}/")
    except Exception:
        co = {}
        try:
            # list may embed company_ref
            pass
        except Exception:
            pass

    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:  # noqa: BLE001
            print(f"retry {a}: {e}")
            time.sleep(5)
    assert robots is not None

    if not co and robots:
        cref = robots[0].get("company_ref") or {}
        if isinstance(cref, dict):
            co = cref

    print(f"company {COMPANY_ID}: {co.get('name')} web={co.get('website')} country={co.get('country')}")
    print(f"robots={len(robots)} status={Counter(str(r.get('status')) for r in robots)}")

    rows = []
    for r in sorted(robots, key=lambda x: int(x["id"])):
        img = (r.get("image") or r.get("s3_image") or "").strip()
        rows.append(
            {
                "id": r["id"],
                "name": r.get("name"),
                "url": r.get("url"),
                "status": r.get("status"),
                "has_image": bool(img),
                "desc_len": len((r.get("description") or "").strip()),
                "feat_len": len((r.get("features") or "").strip()),
                "n_vid": len(r.get("videos") or r.get("video_urls") or []),
                "country": r.get("manufacturer_country"),
                "cats": r.get("categories"),
                "uses": bool(r.get("uses") or r.get("use_keys")),
                "year": r.get("release_year"),
                "payload": r.get("payload_kg"),
            }
        )
        print(
            f"  {r['id']} img={bool(img)} feat={len((r.get('features') or '').strip())} "
            f"url={(r.get('url') or '')[:60]} | {(r.get('name') or '')[:70]}"
        )

    # probe OEM homepage
    site = (co.get("website") or "https://muka-tech.com/").strip()
    fetcher = WebFetcher(stealth=False)
    html = fetcher.get(site) or ""
    print(f"OEM {site} html_len={len(html)}")
    for path in ("/products", "/product", "/en", "/en/products", "/cobot", "/robot"):
        u = site.rstrip("/") + path
        h = fetcher.get(u) or ""
        print(f"  {u} len={len(h)}")
        time.sleep(0.2)

    OUT.write_text(
        json.dumps({"company": co, "robots": rows, "site": site}, indent=2, ensure_ascii=False, default=str)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
