#!/usr/bin/env python3
"""Finish Unitree pending3 publish hygiene + hero correctness check."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from map_to_bulk_import import staging_dict_to_bulk_import_row
from import_staging import resolve_created_by_id

IDS = [5362, 5355, 5353]
QA = Path("staging/unitree_pending_qa")


def md5url(url: str) -> tuple[str, int, bytes]:
    b = requests.get(url, timeout=60).content
    return hashlib.md5(b).hexdigest(), len(b), b


def main() -> int:
    c = ResearchApiClient()
    # Hash published H1 / G1 / R1 heroes for contamination check
    robots = c.list_robots_for_company(109)
    samples = {}
    for r in robots:
        name = (r.get("name") or "").lower()
        if any(x in name for x in ("h1", "g1", "r1", "aliengo", "a2")):
            rid = int(r["id"])
            d = c._get(f"robots/robots/{rid}/")
            hero = (d.get("s3_image") or d.get("image") or "").strip()
            if not hero:
                continue
            try:
                h, n, body = md5url(hero)
            except Exception as e:
                print(f"skip {rid}: {e}")
                continue
            samples[rid] = {
                "id": rid,
                "name": d.get("name"),
                "status": d.get("status"),
                "md5": h,
                "bytes": n,
                "url": d.get("url"),
            }
            if rid in IDS:
                ext = "png" if body.startswith(b"\x89PNG") else (
                    "jpg" if body.startswith(b"\xff\xd8") else (
                        "webp" if body[:4] == b"RIFF" else "bin"
                    )
                )
                QA.mkdir(parents=True, exist_ok=True)
                (QA / f"{rid}_hero.{ext}").write_bytes(body)
            time.sleep(0.05)

    # Cluster by md5 among samples
    by_hash: dict[str, list] = {}
    for s in samples.values():
        by_hash.setdefault(s["md5"], []).append(s)

    print("=== pending3 status ===")
    for rid in IDS:
        d = c._get(f"robots/robots/{rid}/")
        photos = d.get("photos") or []
        print(
            rid,
            d.get("name"),
            d.get("status"),
            "published_at=",
            d.get("published_at"),
            "hero_md5=",
            samples.get(rid, {}).get("md5"),
            "photos=",
            [(p.get("id"), p.get("status"), p.get("is_primary")) for p in photos],
        )
        # gallery hashes
        for p in photos[:4]:
            u = (p.get("s3_image") or p.get("url") or "").strip()
            if not u.startswith("http"):
                continue
            try:
                h, n, _ = md5url(u)
                print(f"  photo {p.get('id')} md5={h[:12]} bytes={n} primary={p.get('is_primary')}")
            except Exception as e:
                print(f"  photo {p.get('id')} ERR {e}")

    print("=== shared hero clusters (name samples) ===")
    for h, group in sorted(by_hash.items(), key=lambda x: -len(x[1])):
        if len(group) < 2:
            continue
        names = [f"{g['id']}:{g['name']}" for g in group]
        print(f"  {h[:12]} x{len(group)} {names}")

    # Try bulk_import force status published with published_at via status param
    # And try to promote photo statuses by replace_media? No - don't destroy media.
    # Check if photo status writable via nested API — skip if not.

    Path("staging/reports/unitree-109-pending3-hero-check.json").write_text(
        json.dumps({"samples": list(samples.values()), "clusters": {
            k: [{"id": g["id"], "name": g["name"]} for g in v]
            for k, v in by_hash.items() if len(v) > 1
        }}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
