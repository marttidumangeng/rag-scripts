"""Inspect Trossen robot fields that drive admin WARN chips."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.path.insert(0, str(_RESEARCH.parents[1] / "robotaigeek-server"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from robots.quality import robot_quality_flags

c = ResearchApiClient()
co = c.get_company(307)
website = (co.get("website") or co.get("website_url") or "").strip()
print("company website", website)

rows = c.list_robots_for_company(307)
summary = []
for r in sorted(rows, key=lambda x: x.get("id", 0)):
    if r.get("status") != "pending_review":
        continue
    rid = r["id"]
    full = c._session.get(c._url(f"robots/robots/{rid}/"), timeout=60).json()
    images = full.get("photos") or full.get("images") or []
    videos = full.get("videos") or []
    tags = full.get("tags") or []
    industries = full.get("industries") or []
    movements = full.get("movement_types") or []
    uses = full.get("uses") or []
    cats = full.get("categories") or []

    ns = SimpleNamespace(**{k: full.get(k) for k in full.keys()})
    # quality uses *_id attrs
    av = full.get("availability_status")
    ns.availability_status_id = av.get("id") if isinstance(av, dict) else av
    cref = full.get("manufacturer_country_ref")
    ns.manufacturer_country_ref_id = cref.get("id") if isinstance(cref, dict) else cref
    ns.n_categories = len(cats)
    ns.n_movement_types = len(movements)
    ns.n_industries = len(industries)
    ns.n_uses = len(uses)
    ns.n_tags = len(tags) if isinstance(tags, list) else (1 if tags else 0)
    if isinstance(tags, list):
        ns.tags = "|".join(
            str(t.get("name") if isinstance(t, dict) else t) for t in tags
        )
    ns.url_verified_at = full.get("url_verified_at")
    ns.s3_image = SimpleNamespace(name=full.get("s3_image") or "") if full.get("s3_image") else None
    ns.image = full.get("image") or full.get("image_url") or ""
    ns.url = full.get("url") or ""

    photo_n = len(images)
    flags = robot_quality_flags(
        ns,
        company_website=website,
        active_photo_count=photo_n,
        active_video_count=len(videos),
        url_status=200,
        image_status=200,
    )
    codes = [f["flag"] for f in flags]
    entry = {
        "id": rid,
        "name": full.get("name"),
        "photo_n": photo_n,
        "video_n": len(videos),
        "tags_n": ns.n_tags,
        "industries_n": len(industries),
        "movements_n": len(movements),
        "uses_n": len(uses),
        "year": full.get("release_year"),
        "price_min": full.get("price_min"),
        "price_max": full.get("price_max"),
        "price_range": full.get("price_range"),
        "flags": codes,
    }
    summary.append(entry)
    print(
        f"{rid} {full.get('name')}: photos={photo_n} vids={len(videos)} "
        f"tags={ns.n_tags} ind={len(industries)} mov={len(movements)} "
        f"year={full.get('release_year')} -> {codes}"
    )

Path("staging/reports/trossen-quality.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
