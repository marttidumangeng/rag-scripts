#!/usr/bin/env python3
"""Unitree (109): status inventory, shared-hero clusters, variant depth audit."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

COMPANY_ID = 109
OUT = Path("staging/reports/unitree-109-fleet-audit.json")
QA = Path("staging/unitree_fleet_qa")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "RobotAIGeekUnitreeAudit/1.0"})

# Known contamination / family-share expectations
EXPECTED_SHARE = {
    # fixed dual-arm family
    frozenset({"R1-A5", "Dual-Arm Humanoid R1-A7", "R1-A7"}): "ok_family_fixed",
    frozenset({"R1-A5-D", "R1-A7-D"}): "ok_family_mobile",
}
CONTAMINATION = {
    frozenset({"A2", "A2-W"}): "bad_a2_a2w_share",
}


def ok(url: str) -> tuple[bool, int | None]:
    try:
        r = SESSION.get(url, timeout=20, headers={"Range": "bytes=0-64"}, allow_redirects=True)
        code = r.status_code
        r.close()
        return code in (200, 206), code
    except requests.RequestException:
        return False, None


def collect_variant_urls(r: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for kind, m in (
        ("primary_jpg", r.get("image_variants")),
        ("primary_webp", r.get("image_variants_webp")),
    ):
        if isinstance(m, dict):
            for w, u in m.items():
                if u:
                    out.append((f"{kind}:{w}", str(u)))
    for p in r.get("photos") or []:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        for kind, m in (
            ("photo_jpg", p.get("variants") or p.get("image_variants")),
            ("photo_webp", p.get("variants_webp") or p.get("image_variants_webp")),
        ):
            if isinstance(m, dict):
                for w, u in m.items():
                    if u:
                        out.append((f"{kind}#{pid}:{w}", str(u)))
    return out


def repair(rid: int) -> dict:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        env = Path("../../robotaigeek-server/.env")
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("INTERNAL_API_SECRET="):
                    secret = line.split("=", 1)[1].strip()
    base = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/repair-images/"
    r = requests.get(url, headers={"X-Internal-Secret": secret}, timeout=300)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:160]}
    return {"http": r.status_code, **(body if isinstance(body, dict) else {})}


def hero_md5(url: str) -> str | None:
    if not url:
        return None
    try:
        b = SESSION.get(url, timeout=60).content
        if len(b) < 100:
            return None
        return hashlib.md5(b).hexdigest()
    except Exception:
        return None


def main() -> int:
    do_repair = "--repair" in sys.argv
    do_heroes = "--heroes" in sys.argv or True
    c = ResearchApiClient()
    robots = c.list_robots_for_company(COMPANY_ID)
    by_status: dict[str, list] = defaultdict(list)
    for r in robots:
        by_status[str(r.get("status") or "?").lower()].append(r)

    print("status counts:", {k: len(v) for k, v in sorted(by_status.items())})
    published = by_status.get("published", []) + by_status.get("approved", [])
    pending = by_status.get("pending_review", [])

    details: dict[int, dict] = {}

    def fetch(rid: int):
        for a in range(4):
            try:
                return rid, c._get(f"robots/robots/{rid}/")
            except Exception:
                time.sleep(1.2 * (a + 1))
        return rid, None

    targets = published + pending
    print(f"hydrating {len(targets)}…")
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(fetch, int(r["id"])) for r in targets]
        n = 0
        for fut in as_completed(futs):
            rid, d = fut.result()
            n += 1
            if d:
                details[rid] = d
            if n % 20 == 0 or n == len(targets):
                print(f"  hydrated {n}/{len(targets)}")

    # Hero hash clusters
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if do_heroes:
        QA.mkdir(parents=True, exist_ok=True)
        print("hashing heroes…")
        with ThreadPoolExecutor(max_workers=12) as pool:
            futs = {}
            for rid, r in details.items():
                if str(r.get("status") or "").lower() not in ("published", "approved"):
                    continue
                u = (r.get("s3_image") or r.get("image") or "").strip()
                futs[pool.submit(hero_md5, u)] = (rid, r.get("name"), u)
            for fut in as_completed(futs):
                rid, name, u = futs[fut]
                md5 = fut.result()
                if md5:
                    clusters[md5].append({"id": rid, "name": name, "url": u})

    shared = {k: v for k, v in clusters.items() if len(v) > 1}
    print(f"shared hero hashes: {len(shared)}")
    for md5, members in sorted(shared.items(), key=lambda x: -len(x[1])):
        names = sorted({m["name"] for m in members})
        print(f"  {md5[:12]} ({len(members)}): {names}")

    # Variant depth
    jobs: list[tuple[int, str, str, str]] = []
    missing_map: list[dict] = []
    for rid, r in details.items():
        if str(r.get("status") or "").lower() not in ("published", "approved"):
            continue
        urls = collect_variant_urls(r)
        primary = (r.get("s3_image") or r.get("image") or "").strip()
        if not urls and primary:
            missing_map.append(
                {
                    "id": rid,
                    "name": r.get("name"),
                    "issue": "no_variant_map",
                    "primary": primary,
                }
            )
        for label, u in urls:
            jobs.append((rid, str(r.get("name") or ""), label, u))

    print(f"probing {len(jobs)} variant URLs…")
    cache: dict[str, tuple[bool, int | None]] = {}
    unique = {u for *_, u in jobs}
    with ThreadPoolExecutor(max_workers=24) as pool:
        futs = {pool.submit(ok, u): u for u in unique}
        for fut in as_completed(futs):
            u = futs[fut]
            try:
                cache[u] = fut.result()
            except Exception:
                cache[u] = (False, None)

    bad_by_robot: dict[int, dict[str, Any]] = {}
    for rid, name, label, u in jobs:
        good, code = cache.get(u, (False, None))
        if good:
            continue
        entry = bad_by_robot.setdefault(rid, {"id": rid, "name": name, "bad": []})
        entry["bad"].append({"label": label, "url": u, "code": code})

    bad = sorted(bad_by_robot.values(), key=lambda x: x["id"])
    print(f"robots_with_dead_variants={len(bad)} no_variant_map={len(missing_map)}")

    pending_detail = []
    for rid in sorted(int(r["id"]) for r in pending):
        d = details.get(rid) or {}
        pending_detail.append(
            {
                "id": rid,
                "name": d.get("name"),
                "status": d.get("status"),
                "published_at": d.get("published_at"),
                "mcs": d.get("manufacturer_countries"),
                "mc_ref": d.get("manufacturer_country_ref"),
                "hero": (d.get("s3_image") or d.get("image") or "")[:80],
                "photo_statuses": [
                    p.get("status") for p in (d.get("photos") or []) if isinstance(p, dict)
                ],
            }
        )

    focus_ids = [5362, 5355, 5353, 5354, 5360]
    focus = {}
    for rid in focus_ids:
        d = details.get(rid)
        if not d:
            continue
        u = (d.get("s3_image") or d.get("image") or "").strip()
        md5 = hero_md5(u) if u else None
        focus[rid] = {
            "name": d.get("name"),
            "status": d.get("status"),
            "published_at": d.get("published_at"),
            "hero_md5": md5,
            "mcs": d.get("manufacturer_countries"),
            "n_photos": len(d.get("photos") or []),
            "photo_statuses": [p.get("status") for p in (d.get("photos") or [])],
        }
        print(
            f"focus {rid} {d.get('name')}: status={d.get('status')} "
            f"pub_at={d.get('published_at')} md5={(md5 or '')[:12]} mcs={d.get('manufacturer_countries')}"
        )

    repairs = []
    if do_repair and (bad or missing_map):
        ids = sorted({m["id"] for m in bad} | {m["id"] for m in missing_map})
        print(f"repairing {len(ids)}…")
        for rid in ids:
            res = repair(rid)
            repairs.append({"id": rid, **res})
            print(f"  repair {rid}: http={res.get('http')}")
            time.sleep(0.3)

    report = {
        "status_counts": {k: len(v) for k, v in sorted(by_status.items())},
        "pending": pending_detail,
        "shared_heroes": {
            md5: members for md5, members in sorted(shared.items(), key=lambda x: -len(x[1]))
        },
        "robots_with_dead_variants": bad,
        "no_variant_map": missing_map,
        "focus": focus,
        "repairs": repairs,
        "variant_urls": len(jobs),
        "unique_urls": len(unique),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
