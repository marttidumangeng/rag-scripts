#!/usr/bin/env python3
"""Pair Yaskawa duplicates from the recon dump and report field conflicts. Read-only."""
from __future__ import annotations

import json
import re
from pathlib import Path

_DIR = Path(__file__).resolve().parent
DUMP = _DIR / "staging" / "reports" / "yaskawa-dedupe-recon.json"
OUT = _DIR / "staging" / "reports" / "yaskawa-pairs.json"


def norm_model(name: str) -> str:
    n = re.sub(r'(?i)^motoman\s+', '', name.strip())
    n = re.sub(r'(?i)\s+robot$', '', n)
    return re.sub(r'[^a-z0-9]', '', n.lower())


def is_motoman_named(name: str) -> bool:
    return bool(re.match(r'(?i)^motoman\s+.+\brobot$', name.strip()))


def has_img(r: dict):
    return r.get("image") or r.get("s3_image") or r.get("image_url")


def main() -> int:
    robots = json.loads(DUMP.read_text(encoding="utf-8"))
    motoman = {}
    short = {}
    other = []
    for r in robots:
        name = r.get("name", "")
        key = norm_model(name)
        if is_motoman_named(name):
            motoman.setdefault(key, []).append(r)
        else:
            short.setdefault(key, []).append(r)

    pairs = []
    motoman_only = []
    short_only = []
    keys = set(motoman) | set(short)
    for k in sorted(keys):
        m = motoman.get(k, [])
        s = short.get(k, [])
        if m and s:
            pairs.append((k, m, s))
        elif m:
            motoman_only.append((k, m))
        else:
            short_only.append((k, s))

    print(f"Total robots: {len(robots)}")
    print(f"Motoman-named groups: {len(motoman)} | Short-name groups: {len(short)}")
    print(f"PAIRS (both present): {len(pairs)}")
    print(f"Motoman-only: {len(motoman_only)} | Short-only: {len(short_only)}")
    print("=" * 100)

    report = {"pairs": [], "motoman_only": [], "short_only": []}

    def slim(r):
        return {
            "id": r.get("id"),
            "name": r.get("name"),
            "status": r.get("status"),
            "release_year": r.get("release_year"),
            "url": r.get("url"),
            "has_image": bool(has_img(r)),
            "image": has_img(r),
            "source_locale": r.get("source_locale"),
            "notes": (r.get("notes") or "")[:400],
            "n_info_sources": len(r.get("information_sources") or []),
            "n_photos": len(r.get("photos") or []),
            "n_videos": len(r.get("videos") or r.get("linked_videos") or []),
            "features_len": len((r.get("features") or "").strip()),
            "has_specs": bool(r.get("weight_kg") or r.get("dof") or r.get("payload")),
        }

    for k, m, s in pairs:
        mr = m[0]
        sr = s[0]
        dup_flag = "  <-- MULTI" if (len(m) > 1 or len(s) > 1) else ""
        yr_conflict = mr.get("release_year") != sr.get("release_year")
        print(f"\n[{k}]{dup_flag}")
        print(f"  MOTOMAN id={mr['id']:<5} '{mr['name']}' yr={mr.get('release_year')} img={bool(has_img(mr))} loc={mr.get('source_locale')}")
        print(f"          url={mr.get('url')}")
        print(f"  SHORT   id={sr['id']:<5} '{sr['name']}' yr={sr.get('release_year')} img={bool(has_img(sr))} loc={sr.get('source_locale')}")
        print(f"          url={sr.get('url')}")
        if yr_conflict:
            print(f"  ** YEAR CONFLICT: motoman={mr.get('release_year')} vs short={sr.get('release_year')}")
        report["pairs"].append({
            "key": k,
            "year_conflict": yr_conflict,
            "multi": len(m) > 1 or len(s) > 1,
            "motoman": [slim(x) for x in m],
            "short": [slim(x) for x in s],
        })

    print("\n" + "=" * 100)
    print("MOTOMAN-ONLY (no short-name counterpart):")
    for k, m in motoman_only:
        for r in m:
            print(f"  id={r['id']:<5} '{r['name']}' yr={r.get('release_year')}")
        report["motoman_only"].append([slim(x) for x in m])

    print("\nSHORT-ONLY (no motoman counterpart):")
    for k, s in short_only:
        for r in s:
            print(f"  id={r['id']:<5} '{r['name']}' yr={r.get('release_year')}")
        report["short_only"].append([slim(x) for x in s])

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
