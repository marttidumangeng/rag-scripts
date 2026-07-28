"""Fetch Realman robot detail photo counts (list API omits images)."""
from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")
from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402


def main() -> None:
    c = ResearchApiClient()
    page = 1
    ids: list[int] = []
    while True:
        d = c._get(
            "robots/robots/",
            params={
                "company_ref": 882,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = d.get("results") or []
        ids.extend(int(r["id"]) for r in batch)
        if not d.get("next") or not batch:
            break
        page += 1

    buckets = {"4+": 0, "2-3": 0, "0-1": 0}
    for rid in sorted(ids):
        r = c._get(f"robots/robots/{rid}/")
        imgs = r.get("images") or []
        if isinstance(imgs, list) and imgs and isinstance(imgs[0], dict):
            n = len(imgs)
        elif isinstance(imgs, list):
            n = len([x for x in imgs if x])
        else:
            n = 0
        # also try photos / photo_count
        photos = r.get("photos") or r.get("robot_photos")
        if isinstance(photos, list) and len(photos) > n:
            n = len(photos)
        hero = bool(r.get("image") or r.get("s3_image"))
        name = (r.get("name") or "")[:36]
        print(f"{rid} {name:36s} images={n} hero={hero} image={(r.get('image') or '')[-40:]}")
        if n >= 4:
            buckets["4+"] += 1
        elif n >= 2:
            buckets["2-3"] += 1
        else:
            buckets["0-1"] += 1
        time.sleep(0.05)
    print("buckets", buckets)


if __name__ == "__main__":
    main()
