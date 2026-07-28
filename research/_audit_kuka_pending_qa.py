"""Quality-flag audit for KUKA 1396 pending_review (local quality.py)."""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.path.insert(0, str(_RESEARCH_DIR.parents[1] / "robotaigeek-server"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from robots.quality import robot_quality_flags

COMPANY_ID = 1396
OUT = _RESEARCH_DIR / "staging" / "reports" / "kuka-1396-pending-qa.json"


def main() -> None:
    client = ResearchApiClient()
    co = client._get(f"companies/{COMPANY_ID}/")
    website = (co.get("website") or "").strip()

    pending = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": COMPANY_ID,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        pending.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1

    print(f"pending={len(pending)} website={website!r}")

    # Preload details + url share
    details = {}
    url_counts: Counter = Counter()
    name_counts: Counter = Counter()
    for r in pending:
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        details[rid] = full
        u = (full.get("url") or "").strip()
        if u:
            url_counts[u] += 1
        name_counts[(full.get("name") or "").strip().casefold()] += 1
        time.sleep(0.03)

    err_c: Counter = Counter()
    warn_c: Counter = Counter()
    rows = []
    for rid, full in sorted(details.items()):
        url = (full.get("url") or "").strip()
        img = (full.get("s3_image") or full.get("image") or "").strip()
        tags = full.get("tags")
        if isinstance(tags, list):
            n_tags = len(tags)
            tag_str = "|".join(
                (t.get("name") if isinstance(t, dict) else str(t)) for t in tags
            )
        else:
            tag_str = (tags or "").strip()
            n_tags = len([x for x in tag_str.split("|") if x.strip()]) if tag_str else 0

        cats = full.get("categories") or []
        uses = full.get("uses") or []
        moves = full.get("movement_types") or []
        inds = full.get("industries") or []
        vids = full.get("videos") or full.get("video_urls") or []
        photos = full.get("photos") or []
        n_photos = len(photos) if isinstance(photos, list) else 0
        if n_photos == 0 and img:
            n_photos = 1

        country_ref = full.get("manufacturer_country_ref")
        country_id = None
        if isinstance(country_ref, dict):
            country_id = country_ref.get("id")
        elif isinstance(country_ref, int):
            country_id = country_ref

        avail = full.get("availability_status")
        avail_id = avail.get("id") if isinstance(avail, dict) else avail

        ns = SimpleNamespace(
            url=url,
            image=img,
            s3_image=img,
            description=(full.get("description") or "").strip(),
            features=(full.get("features") or "").strip(),
            purpose=(full.get("purpose") or "").strip(),
            release_year=full.get("release_year"),
            availability_status_id=avail_id,
            manufacturer_country_ref_id=country_id,
            price_min=full.get("price_min"),
            price_max=full.get("price_max"),
            price=full.get("price"),
            weight_kg=full.get("weight_kg"),
            payload_kg=full.get("payload_kg"),
            reach_mm=full.get("reach_mm"),
            dof=full.get("dof"),
            height_mm=full.get("height_mm"),
            width_mm=full.get("width_mm"),
            length_mm=full.get("length_mm"),
            n_categories=len(cats) if isinstance(cats, list) else 0,
            n_uses=len(uses) if isinstance(uses, list) else 0,
            n_industries=len(inds) if isinstance(inds, list) else 0,
            n_movement_types=len(moves) if isinstance(moves, list) else 0,
            n_tags=n_tags,
            tags=tag_str,
            notes=(full.get("notes") or ""),
        )
        flags = robot_quality_flags(
            ns,
            company_website=website,
            active_photo_count=n_photos,
            active_video_count=len(vids) if isinstance(vids, list) else 0,
            has_dup_name=name_counts[(full.get("name") or "").strip().casefold()] > 1,
            url_shared_count=url_counts[url] if url else 0,
        )
        errors = [f for f in flags if f.get("severity") == "error"]
        warns = [f for f in flags if f.get("severity") == "warn"]
        for f in errors:
            err_c[f.get("code") or f.get("key") or str(f)] += 1
        for f in warns:
            warn_c[f.get("code") or f.get("key") or str(f)] += 1
        rows.append(
            {
                "id": rid,
                "name": full.get("name"),
                "errors": errors,
                "warns": warns,
                "n_photos": n_photos,
                "family_key": full.get("family_key"),
                "notes_hub": "SERIES HUB" in (full.get("notes") or "").upper(),
            }
        )

    report = {
        "company_id": COMPANY_ID,
        "pending": len(pending),
        "error_counts": dict(err_c.most_common()),
        "warn_counts": dict(warn_c.most_common()),
        "with_errors": [r for r in rows if r["errors"]],
        "with_warns_only": [r for r in rows if r["warns"] and not r["errors"]],
        "clean": [r["id"] for r in rows if not r["errors"] and not r["warns"]],
        "robots": rows,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ERROR counts:", dict(err_c.most_common()))
    print("WARN counts:", dict(warn_c.most_common()))
    print(f"with_errors={len(report['with_errors'])} warns_only={len(report['with_warns_only'])} clean={len(report['clean'])}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
