#!/usr/bin/env python3
"""Deep-check KUKA published: every image_variants / variants URL must be HTTP OK."""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

COMPANY_ID = 1396
OUT = Path("staging/reports/kuka-1396-variant-depths.json")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "RobotAIGeekKukaVariantDeep/1.0"})


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
    rid = r.get("id")
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


def main() -> int:
    apply = "--repair" in sys.argv
    c = ResearchApiClient()
    robots = c.list_robots_for_company(COMPANY_ID)
    published = [
        r for r in robots if str(r.get("status") or "").lower() in ("published", "approved")
    ]
    print(f"published={len(published)}")

    details: dict[int, dict] = {}

    def fetch(rid: int):
        for a in range(4):
            try:
                return rid, c._get(f"robots/robots/{rid}/")
            except Exception:
                time.sleep(1.2 * (a + 1))
        return rid, None

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(fetch, int(r["id"])) for r in published]
        n = 0
        for fut in as_completed(futs):
            rid, d = fut.result()
            n += 1
            if d:
                details[rid] = d
            if n % 50 == 0 or n == len(published):
                print(f"hydrated {n}/{len(published)}")

    jobs: list[tuple[int, str, str, str]] = []  # rid, name, label, url
    for rid, r in details.items():
        for label, u in collect_variant_urls(r):
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
    report = {
        "published": len(published),
        "variant_urls": len(jobs),
        "unique_urls": len(unique),
        "robots_with_dead_variants": len(bad),
        "robots": bad,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"robots_with_dead_variants={len(bad)} -> {OUT}")
    for m in bad[:40]:
        labels = [b["label"] for b in m["bad"]]
        print(f"  {m['id']} {m['name']}: {labels}")

    if not apply or not bad:
        return 0

    still = []
    for m in bad:
        rid = m["id"]
        res = repair(rid)
        print(f"repair {rid}: http={res.get('http')} gen={res.get('total_generated')} ok={res.get('success')}")
        time.sleep(0.25)
        # recheck
        r = c._get(f"robots/robots/{rid}/")
        dead = []
        for label, u in collect_variant_urls(r):
            g, code = ok(u)
            if not g:
                dead.append((label, code, u))
        if dead:
            still.append({"id": rid, "dead": dead[:8]})
            print(f"  STILL {rid}: {[(a,b) for a,b,_ in dead[:4]]}")
        else:
            print(f"  fixed {rid}")
    report["still_after_repair"] = still
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"still_missing={len(still)}")
    return 0 if not still else 1


if __name__ == "__main__":
    raise SystemExit(main())
