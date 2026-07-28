#!/usr/bin/env python3
"""Fleet audit: variants + shared-hero clusters for one or more company IDs.

Usage:
  python _audit_company_media.py 1028 239
  python _audit_company_media.py 1028 239 --repair
  python _audit_company_media.py 1028 --heroes   # also download unique heroes for visual QA
"""
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

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "RobotAIGeekFleetMediaAudit/1.0"})
REPORT_DIR = Path("staging/reports")
QA_DIR = Path("staging/fleet_media_qa")


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


def hero_md5(url: str) -> tuple[str | None, bytes]:
    if not url:
        return None, b""
    try:
        b = SESSION.get(url, timeout=60).content
        if len(b) < 50:
            return None, b
        return hashlib.md5(b).hexdigest(), b
    except Exception:
        return None, b""


def audit_company(c: ResearchApiClient, company_id: int, *, do_repair: bool, save_heroes: bool) -> dict:
    robots = c.list_robots_for_company(company_id)
    by_status: dict[str, list] = defaultdict(list)
    for r in robots:
        by_status[str(r.get("status") or "?").lower()].append(r)

    company_name = ""
    if robots:
        # hydrate one for company name
        sample = c._get(f"robots/robots/{int(robots[0]['id'])}/")
        cref = sample.get("company_ref") or {}
        if isinstance(cref, dict):
            company_name = cref.get("name") or ""
        elif sample.get("company"):
            company_name = str(sample.get("company"))

    print(f"\n=== company {company_id} {company_name} ===")
    print("status:", {k: len(v) for k, v in sorted(by_status.items())})

    published = by_status.get("published", []) + by_status.get("approved", [])
    details: dict[int, dict] = {}

    def fetch(rid: int):
        for a in range(4):
            try:
                return rid, c._get(f"robots/robots/{rid}/")
            except Exception:
                time.sleep(1.2 * (a + 1))
        return rid, None

    print(f"hydrating {len(published)} published…")
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(fetch, int(r["id"])) for r in published]
        n = 0
        for fut in as_completed(futs):
            rid, d = fut.result()
            n += 1
            if d:
                details[rid] = d
            if n % 25 == 0 or n == len(published):
                print(f"  hydrated {n}/{len(published)}")

    # Hero clusters
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tiny: list[dict] = []
    no_hero: list[dict] = []
    qa = QA_DIR / str(company_id)
    if save_heroes:
        qa.mkdir(parents=True, exist_ok=True)

    print("hashing heroes…")
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {}
        for rid, r in details.items():
            u = (r.get("s3_image") or r.get("image") or "").strip()
            futs[pool.submit(hero_md5, u)] = (rid, r.get("name"), u)
        for fut in as_completed(futs):
            rid, name, u = futs[fut]
            md5, body = fut.result()
            if not u:
                no_hero.append({"id": rid, "name": name})
                continue
            if not md5:
                no_hero.append({"id": rid, "name": name, "url": u})
                continue
            if len(body) < 2000:
                tiny.append({"id": rid, "name": name, "md5": md5, "bytes": len(body)})
            clusters[md5].append({"id": rid, "name": name, "url": u, "bytes": len(body)})
            if save_heroes and body:
                ext = (
                    "png"
                    if body.startswith(b"\x89PNG")
                    else (
                        "jpg"
                        if body.startswith(b"\xff\xd8")
                        else ("webp" if body[:4] == b"RIFF" else "bin")
                    )
                )
                (qa / f"{rid}_{md5[:12]}.{ext}").write_bytes(body)

    shared = {k: v for k, v in clusters.items() if len(v) > 1}
    print(f"shared_hero_hashes={len(shared)} tiny={len(tiny)} no_hero={len(no_hero)}")
    for md5, members in sorted(shared.items(), key=lambda x: -len(x[1])):
        names = [f"{m['id']}:{m['name']}" for m in members]
        print(f"  {md5[:12]} x{len(members)} {names}")

    # Variant probe
    jobs: list[tuple[int, str, str, str]] = []
    missing_map = []
    for rid, r in details.items():
        urls = collect_variant_urls(r)
        primary = (r.get("s3_image") or r.get("image") or "").strip()
        if not urls and primary:
            missing_map.append({"id": rid, "name": r.get("name"), "primary": primary})
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
    for m in bad[:30]:
        print(f"  {m['id']} {m['name']}: {[b['label'] for b in m['bad'][:6]]} n={len(m['bad'])}")

    repairs = []
    if do_repair and (bad or missing_map):
        ids = sorted({m["id"] for m in bad} | {m["id"] for m in missing_map})
        print(f"repairing {len(ids)}…")
        for rid in ids:
            res = repair(rid)
            repairs.append({"id": rid, **res})
            print(f"  repair {rid}: http={res.get('http')}")
            time.sleep(0.25)

    report = {
        "company_id": company_id,
        "company_name": company_name,
        "status_counts": {k: len(v) for k, v in sorted(by_status.items())},
        "published": len(published),
        "shared_heroes": {
            md5: members for md5, members in sorted(shared.items(), key=lambda x: -len(x[1]))
        },
        "tiny_heroes": tiny,
        "no_hero": no_hero,
        "robots_with_dead_variants": bad,
        "no_variant_map": missing_map,
        "variant_urls": len(jobs),
        "unique_urls": len(unique),
        "repairs": repairs,
    }
    out = REPORT_DIR / f"company-{company_id}-media-audit.json"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return report


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print("usage: _audit_company_media.py COMPANY_ID [COMPANY_ID…] [--repair] [--heroes]")
        return 2
    do_repair = "--repair" in flags
    save_heroes = "--heroes" in flags
    c = ResearchApiClient()
    reports = []
    for cid in args:
        reports.append(audit_company(c, int(cid), do_repair=do_repair, save_heroes=save_heroes))
    # summary
    print("\n=== SUMMARY ===")
    for r in reports:
        print(
            f"co {r['company_id']} {r['company_name']}: published={r['published']} "
            f"dead_var={len(r['robots_with_dead_variants'])} shared={len(r['shared_heroes'])} "
            f"tiny={len(r['tiny_heroes'])} no_hero={len(r['no_hero'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
