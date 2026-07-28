#!/usr/bin/env python3
"""Audit KUKA (1396): published media dups + pending_review gaps/flags."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

COMPANY_ID = 1396
OUT = _HERE / "staging" / "reports" / "kuka-1396-audit.json"
UA = {"User-Agent": "RobotAIGeekCDNCheck/1.0"}


def list_by_status(client: ResearchApiClient, status: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": COMPANY_ID,
                "status": status,
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        rows.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1
        time.sleep(0.05)
    return rows


def hero_url(r: dict[str, Any]) -> str:
    return (r.get("s3_image") or r.get("image") or r.get("image_url") or "").strip()


def hash_url(url: str) -> tuple[str, int, str]:
    """Return (md5_or_err, status, note)."""
    if not url:
        return "", 0, "empty"
    try:
        resp = requests.get(url, headers=UA, timeout=40, stream=True)
        chunks = []
        total = 0
        for chunk in resp.iter_content(65536):
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > 8_000_000:
                break
        body = b"".join(chunks)
        resp.close()
        if resp.status_code != 200:
            return "", resp.status_code, f"HTTP {resp.status_code}"
        if not body.startswith((b"\x89PNG", b"\xff\xd8", b"GIF8", b"RIFF")):
            if b"AccessDenied" in body[:500]:
                return "", 403, "AccessDenied"
            return "", resp.status_code, "not_image"
        return hashlib.md5(body).hexdigest(), 200, f"{len(body)}b"
    except requests.RequestException as e:
        return "", 0, str(e)[:80]


def soft_gaps(r: dict[str, Any]) -> list[str]:
    gaps = []
    if not hero_url(r):
        gaps.append("no_image")
    feat = (r.get("features") or "").strip()
    if len(feat) < 40:
        gaps.append("no_features")
    if not (r.get("manufacturer_country_ref") or r.get("manufacturer_countries") or r.get("country")):
        gaps.append("no_country")
    cats = r.get("categories") or []
    if not cats:
        gaps.append("no_categories")
    uses = r.get("uses") or []
    if not uses:
        gaps.append("no_uses")
    if not (r.get("videos") or r.get("video_urls")):
        gaps.append("no_video")
    if not r.get("release_year"):
        gaps.append("no_year")
    if not (r.get("tags") or []):
        gaps.append("no_tags")
    notes = (r.get("notes") or "").upper()
    if "IMAGE TO-DO" in notes:
        gaps.append("image_todo")
    if "SERIES HUB" in notes:
        gaps.append("series_hub")
    flags = r.get("quality_flags") or r.get("flags") or []
    if isinstance(flags, list) and flags:
        for f in flags:
            if isinstance(f, dict):
                gaps.append(f"flag:{(f.get('code') or f.get('type') or f)}")
            else:
                gaps.append(f"flag:{f}")
    return gaps


def main() -> int:
    client = ResearchApiClient()
    published = list_by_status(client, "published")
    approved = list_by_status(client, "approved")
    pending = list_by_status(client, "pending_review")
    rejected = list_by_status(client, "rejected")

    print(
        f"counts published={len(published)} approved={len(approved)} "
        f"pending={len(pending)} rejected={len(rejected)}"
    )

    # User said 54 approved — treat published+approved as the public set
    public = published + approved
    print(f"public set: {len(public)}")

    # Hash heroes for public set
    hash_owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dead: list[dict[str, Any]] = []
    public_rows = []
    for i, r in enumerate(sorted(public, key=lambda x: int(x["id"]))):
        rid = int(r["id"])
        url = hero_url(r)
        md5, status, note = hash_url(url) if url else ("", 0, "empty")
        entry = {
            "id": rid,
            "name": r.get("name"),
            "status": r.get("status"),
            "url": r.get("url"),
            "hero": url[-80:] if url else "",
            "md5": md5,
            "http": status,
            "note": note,
            "photos_hint": len(r.get("photos") or []) if isinstance(r.get("photos"), list) else None,
        }
        public_rows.append(entry)
        if not md5:
            dead.append(entry)
        else:
            hash_owners[md5].append({"id": rid, "name": r.get("name"), "status": r.get("status")})
        if (i + 1) % 10 == 0:
            print(f"  hashed public {i+1}/{len(public)}")
        time.sleep(0.05)

    dup_clusters = {
        h: owners
        for h, owners in hash_owners.items()
        if len(owners) > 1
    }
    print(f"public dead/missing heroes: {len(dead)}")
    print(f"public shared-hero clusters: {len(dup_clusters)}")

    # Pending gaps
    pending_rows = []
    gap_counter: Counter[str] = Counter()
    for r in sorted(pending, key=lambda x: int(x["id"])):
        gaps = soft_gaps(r)
        for g in gaps:
            gap_counter[g.split(":")[0] if g.startswith("flag:") else g] += 1
        pending_rows.append(
            {
                "id": int(r["id"]),
                "name": r.get("name"),
                "url": r.get("url"),
                "hero": hero_url(r)[-80:] if hero_url(r) else "",
                "gaps": gaps,
                "features_len": len((r.get("features") or "").strip()),
                "notes_head": ((r.get("notes") or "")[:120]),
            }
        )

    # Name collisions within company (all statuses)
    all_robots = public + pending + rejected
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in all_robots:
        key = (r.get("name") or "").strip().casefold()
        by_name[key].append(
            {"id": int(r["id"]), "name": r.get("name"), "status": r.get("status")}
        )
    name_dups = {k: v for k, v in by_name.items() if len(v) > 1}

    report = {
        "company_id": COMPANY_ID,
        "counts": {
            "published": len(published),
            "approved": len(approved),
            "pending_review": len(pending),
            "rejected": len(rejected),
            "public": len(public),
        },
        "public_dead_heroes": dead,
        "public_shared_hero_clusters": [
            {"md5": h, "count": len(owners), "robots": owners}
            for h, owners in sorted(dup_clusters.items(), key=lambda x: -len(x[1]))
        ],
        "public_robots": public_rows,
        "pending_gap_counts": dict(gap_counter.most_common()),
        "pending_robots": pending_rows,
        "exact_name_duplicates": list(name_dups.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n=== pending gap counts ===")
    for k, v in gap_counter.most_common():
        print(f"  {k}: {v}")
    print("\n=== shared hero clusters (top) ===")
    for c in report["public_shared_hero_clusters"][:15]:
        names = ", ".join(f"{x['id']}:{x['name']}" for x in c["robots"][:8])
        print(f"  n={c['count']} {c['md5'][:12]} {names}")
    print("\n=== exact name dups ===")
    for group in report["exact_name_duplicates"][:20]:
        print(" ", group)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
