"""Deep audit Universal Robots company 192."""

from __future__ import annotations

import json
import re
import sys
import time
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

COMPANY_ID = 192
OUT = _RESEARCH_DIR / "staging" / "reports" / "ur192_audit.json"


def main() -> int:
    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:  # noqa: BLE001
            print(f"retry {a}: {e}")
            time.sleep(5)
    assert robots

    rows = []
    for r in sorted(robots, key=lambda x: int(x["id"])):
        if str(r.get("status") or "").lower() != "pending_review":
            continue
        full = client._get(f"robots/robots/{r['id']}/")
        time.sleep(0.05)
        row = {
            "id": full["id"],
            "name": full.get("name"),
            "url": full.get("url"),
            "image": (full.get("image") or full.get("s3_image") or "")[:120],
            "desc_len": len((full.get("description") or "").strip()),
            "feat_len": len((full.get("features") or "").strip()),
            "purpose": (full.get("purpose") or "")[:100],
            "features": (full.get("features") or "")[:200],
            "country": full.get("manufacturer_country"),
            "categories": full.get("categories"),
            "uses": full.get("uses") or full.get("use_keys"),
            "year": full.get("release_year"),
            "payload_kg": full.get("payload_kg"),
            "reach_mm": full.get("reach_mm"),
            "n_vid": len(full.get("videos") or []),
            "avail": full.get("availability_status") or full.get("availability_status_id"),
            "tags": (full.get("tags") or [])[:8],
        }
        rows.append(row)
        print(
            f"{row['id']} {row['name']} img={bool(row['image'])} "
            f"feat={row['feat_len']} y={row['year']} p={row['payload_kg']} "
            f"country={row['country']} cats={row['categories']}"
        )
        print(f"  url={row['url']}")

    # scrape a few PDPs
    f = WebFetcher(stealth=False)
    samples = [
        "https://www.universal-robots.com/products/ur3e/",
        "https://www.universal-robots.com/products/ur5e/",
        "https://www.universal-robots.com/products/ur10e/",
        "https://www.universal-robots.com/products/ur20/",
        "https://www.universal-robots.com/products/ur30/",
    ]
    scraped = {}
    for u in samples:
        html = f.get(u) or ""
        title = ""
        m = re.search(r"<title>([^<]+)", html, re.I)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
        # og:image
        og = ""
        m = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html, re.I)
        if not m:
            m = re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', html, re.I)
        if m:
            og = m.group(1)
        # payload/reach hints
        specs = re.findall(
            r"(payload|reach|weight|degrees of freedom|repeatability)[^.<]{0,40}([\d.]+)\s*(kg|mm|m|kgf)?",
            html,
            re.I,
        )[:8]
        scraped[u] = {"html_len": len(html), "title": title[:80], "og": og, "spec_hits": specs[:6]}
        print(f"PDP {u} len={len(html)} og={bool(og)} title={title[:60]}")
        time.sleep(0.3)

    OUT.write_text(
        json.dumps({"robots": rows, "scraped": scraped}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} n={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
