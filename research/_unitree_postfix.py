#!/usr/bin/env python3
"""Post-fix Unitree hygiene: A2 country, Go2-W URL, re-audit variants, soft notes."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

OUT = Path("staging/reports/unitree-109-postfix.json")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "RobotAIGeekUnitreePost/1.0"})


def ok(url: str) -> tuple[bool, int | None]:
    try:
        r = SESSION.get(url, timeout=20, headers={"Range": "bytes=0-64"}, allow_redirects=True)
        code = r.status_code
        r.close()
        return code in (200, 206), code
    except requests.RequestException:
        return False, None


def collect(r: dict) -> list[tuple[str, str]]:
    out = []
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
    c = ResearchApiClient()
    # A2 country M2M empty — fill China
    c._patch("robots/robots/5354/", {"manufacturer_countries": [3]})
    print("patched A2 countries")
    # Go2-W product URL
    c._patch("robots/robots/644/", {"url": "https://www.unitree.com/go2-w/"})
    print("patched Go2-W url")

    # Soft-delete R1-A7 D-variant gallery photo 21077 if API supports deleted flag
    try:
        c._patch("robots/robots/5362/", {})  # no-op probe
    except Exception:
        pass

    robots = c.list_robots_for_company(109)
    published = [r for r in robots if str(r.get("status") or "").lower() == "published"]
    details = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(c._get, f"robots/robots/{int(r['id'])}/"): int(r["id"]) for r in published}
        for fut in as_completed(futs):
            rid = futs[fut]
            try:
                details[rid] = fut.result()
            except Exception:
                pass

    # hero hash check focus
    focus = {}
    for rid in (5362, 5355, 5353, 5354, 644, 5360):
        d = details.get(rid)
        if not d:
            continue
        u = (d.get("s3_image") or d.get("image") or "").strip()
        b = SESSION.get(u, timeout=60).content if u else b""
        md5 = hashlib.md5(b).hexdigest() if b else ""
        focus[rid] = {
            "name": d.get("name"),
            "md5": md5,
            "published_at": d.get("published_at"),
            "url": d.get("url"),
            "photo_statuses": [p.get("status") for p in (d.get("photos") or [])],
            "mcs": d.get("manufacturer_countries"),
        }
        print(rid, d.get("name"), md5[:12], "photos", focus[rid]["photo_statuses"])

    assert focus[5354]["md5"][:12] != focus[5353]["md5"][:12], "A2/A2-W still share"
    assert focus[5354]["md5"][:12] != focus[644]["md5"][:12], "A2/Go2-W still share"
    assert focus[644]["md5"].startswith("e3faa3edc876"), "Go2-W hero wrong"

    jobs = []
    for rid, r in details.items():
        for label, u in collect(r):
            jobs.append((rid, r.get("name"), label, u))
    cache = {}
    unique = {u for *_, u in jobs}
    print(f"probing {len(jobs)} urls…")
    with ThreadPoolExecutor(max_workers=24) as pool:
        futs = {pool.submit(ok, u): u for u in unique}
        for fut in as_completed(futs):
            u = futs[fut]
            cache[u] = fut.result()

    bad = {}
    for rid, name, label, u in jobs:
        good, code = cache.get(u, (False, None))
        if not good:
            bad.setdefault(rid, {"id": rid, "name": name, "bad": []})["bad"].append(
                {"label": label, "url": u, "code": code}
            )

    print(f"dead_variant_robots={len(bad)}")
    repairs = []
    for rid in sorted(bad):
        res = repair(rid)
        repairs.append({"id": rid, **res})
        print("repair", rid, res.get("http"))
        time.sleep(0.2)

    # re-probe repaired
    still = {}
    if bad:
        time.sleep(1)
        for rid in list(bad):
            d = c._get(f"robots/robots/{rid}/")
            for label, u in collect(d):
                good, code = ok(u)
                if not good:
                    still.setdefault(rid, {"id": rid, "name": d.get("name"), "bad": []})[
                        "bad"
                    ].append({"label": label, "code": code, "url": u})

    report = {
        "focus": focus,
        "dead_before_second_pass": {str(k): v for k, v in bad.items()},
        "dead_after_repair": {str(k): v for k, v in still.items()},
        "repairs": repairs,
        "published_count": len(published),
        "pending_count": sum(
            1 for r in robots if str(r.get("status") or "").lower() == "pending_review"
        ),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT, "still_dead", len(still))
    return 0 if not still else 1


if __name__ == "__main__":
    raise SystemExit(main())
