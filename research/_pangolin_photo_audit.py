#!/usr/bin/env python3
"""Audit Pangolin published robots for photo counts + CDN health."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

OUT = Path("staging/reports/_pangolin_photo_audit.json")


def main() -> int:
    client = ResearchApiClient()
    rows = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": 1413,
                "status": "published",
                "page": page,
                "page_size": 50,
            },
        )
        for r in data.get("results") or []:
            imgs = r.get("images") or []
            if not isinstance(imgs, list):
                imgs = []
            urls = []
            for im in imgs:
                if isinstance(im, dict):
                    urls.append(im.get("s3_image") or im.get("image") or im.get("url") or "")
                else:
                    urls.append(str(im))
            hero = r.get("s3_image") or r.get("image") or ""
            if hero and hero not in urls:
                urls = [hero] + urls
            hashes = []
            ok = 0
            for u in urls:
                if not u:
                    continue
                try:
                    resp = requests.get(u, timeout=25)
                    body = resp.content if resp.ok else b""
                    if resp.ok and body[:3] in (b"\xff\xd8\xff", b"\x89PN") or (
                        resp.ok and body[:4] == b"RIFF"
                    ) or (resp.ok and body[:4] == b"\x00\x00\x00\x1c") or (
                        resp.ok and len(body) > 1000
                    ):
                        # magic: jpeg/png/webp-ish; len fallback for CDN octet-stream
                        ok += 1
                        hashes.append(hashlib.md5(body).hexdigest()[:12])
                    else:
                        hashes.append(f"bad:{resp.status_code}")
                except requests.RequestException as exc:
                    hashes.append(f"err:{exc.__class__.__name__}")
            rows.append(
                {
                    "id": r["id"],
                    "name": r.get("name"),
                    "model_name": r.get("model_name"),
                    "url": r.get("url") or r.get("website_url"),
                    "photo_slots": len(urls),
                    "cdn_ok": ok,
                    "unique_hashes": len(set(h for h in hashes if not h.startswith(("bad", "err")))),
                    "hashes": hashes,
                    "image_urls": urls,
                }
            )
        if not data.get("next"):
            break
        page += 1

    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"published={len(rows)}")
    for x in sorted(rows, key=lambda z: z["id"]):
        print(
            f"{x['id']:>5} slots={x['photo_slots']} ok={x['cdn_ok']} "
            f"uniq={x['unique_hashes']}  {x['name']}"
        )
    thin = [x for x in rows if x["unique_hashes"] < 4]
    print(f"\nbelow-4-photos: {len(thin)}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
