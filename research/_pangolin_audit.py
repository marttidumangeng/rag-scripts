"""Quick audit for Pangolin Robotics (company 1413)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

COMPANY_ID = 1413
OUT = _RESEARCH_DIR / "staging" / "reports" / "pangolin-audit.json"


def main() -> None:
    client = ResearchApiClient()
    co = {}
    for path in (f"companies/{COMPANY_ID}/",):
        try:
            co = client._get(path)
            print(f"company via {path}")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"skip {path}: {exc}")
            co = {}

    robots = client.list_robots_for_company(COMPANY_ID)
    by_status = Counter(str(r.get("status") or "").lower() for r in robots)
    print(f"robots={len(robots)} by_status={dict(by_status)}")

    pending = [r for r in robots if str(r.get("status") or "").lower() == "pending_review"]
    gaps = Counter()
    rows = []
    domains = Counter()
    for r in sorted(pending, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        img = (full.get("image") or full.get("s3_image") or "").strip()
        feat = (full.get("features") or "").strip()
        url = (full.get("url") or full.get("website_url") or "").strip()
        tags = full.get("tags") or []
        vids = full.get("video_urls") or full.get("videos") or []
        country = full.get("manufacturer_country") or full.get("manufacturer_countries")
        cats = full.get("categories") or []
        uses = full.get("uses") or []
        g = []
        if not img:
            g.append("no_image")
        if len(feat) < 40:
            g.append("no_features")
        if not url:
            g.append("no_url")
        if not tags:
            g.append("no_tags")
        if not vids:
            g.append("no_videos")
        if not country:
            g.append("no_country")
        if not cats or not uses:
            g.append("no_taxonomy")
        if full.get("payload_kg") is None and full.get("reach_mm") is None:
            g.append("no_specs")
        for x in g:
            gaps[x] += 1
        if url:
            domains[urlparse(url).netloc.lower()] += 1
        rows.append(
            {
                "id": rid,
                "name": full.get("name"),
                "gaps": g,
                "url": url,
                "img": bool(img),
                "feat_len": len(feat),
                "country": country,
                "n_tags": len(tags) if isinstance(tags, list) else 0,
                "n_vids": len(vids) if isinstance(vids, list) else 0,
            }
        )
        print(
            f"{rid:>5} gaps={'+'.join(g) or 'ok'} "
            f"feat={len(feat)} img={bool(img)} "
            f"name={(full.get('name') or '')[:45]!r}"
        )

    print("\ngap totals:", dict(gaps))
    print("url domains:", dict(domains.most_common(10)))

    # probe OEM homepage
    site = (co.get("website") or "https://www.csjbot.com/").strip()
    if not site.startswith("http"):
        site = "https://" + site
    try:
        resp = requests.get(site, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        print(f"OEM GET {site} -> {resp.status_code} final={resp.url} len={len(resp.text)}")
    except Exception as exc:  # noqa: BLE001
        print(f"OEM FAIL {site}: {exc}")

    OUT.write_text(
        json.dumps(
            {
                "company": {"id": COMPANY_ID, "name": co.get("name"), "website": co.get("website")},
                "status_counts": dict(by_status),
                "pending": len(pending),
                "gaps": dict(gaps),
                "domains": dict(domains),
                "rows": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
