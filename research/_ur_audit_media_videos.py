"""Audit photos/videos for Universal Robots company 192."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from fix_universal_robots import normalize_model

COMPANY_ID = 192


def main() -> None:
    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    ]
    print(f"pending={len(robots)}")
    no_vid = 0
    thin_gallery = 0
    by_model: dict[str, list[int]] = {}
    for r in sorted(robots, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        model = normalize_model(full.get("name") or "") or "?"
        by_model.setdefault(model, []).append(rid)
        imgs = full.get("images") or []
        if isinstance(imgs, str):
            imgs = [imgs] if imgs else []
        n_img = len([x for x in imgs if x]) or (1 if (full.get("image") or full.get("s3_image")) else 0)
        videos = full.get("video_urls") or full.get("videos") or []
        if isinstance(videos, dict):
            videos = list(videos.values()) if videos else []
        n_vid = len(videos) if isinstance(videos, list) else 0
        # also check nested
        if not n_vid:
            for key in ("youtube_videos", "video_list"):
                v = full.get(key)
                if isinstance(v, list) and v:
                    n_vid = len(v)
                    videos = v
                    break
        if n_vid == 0:
            no_vid += 1
        if n_img < 2:
            thin_gallery += 1
        print(
            f"{rid:>5} {model:<10} imgs={n_img} vids={n_vid} "
            f"name={(full.get('name') or '')[:40]!r}"
        )
    print(f"\nno_video={no_vid}/{len(robots)} gallery<2={thin_gallery}/{len(robots)}")
    print("model clusters:")
    for m, ids in sorted(by_model.items(), key=lambda x: -len(x[1])):
        print(f"  {m}: {ids}")


if __name__ == "__main__":
    main()
