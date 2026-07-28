"""Detect shared/duplicate hero images across a company's robots.

Catches the defect class where an automated pass grabs a site-wide graphic
(footer map, OG banner, "about us" image) and pins it as the primary hero on
every robot of a company. URLs give no clue once media is copied to our CDN
(`photo-<robot>-<photo>.webp`), so this hashes the actual image BYTES.

Real case (2026-07-16): 32 Comau robots (company 245) all shipped with Comau's
corporate world-map network graphic as their primary — md5 f9f947f9..., byte
identical. 53 robots shared only 21 distinct heroes. Expensive to find by hand.

Usage:
  python detect_duplicate_heroes.py --company-id 245
  python detect_duplicate_heroes.py --ids 1852 1853 --json-out dupes.json
  python detect_duplicate_heroes.py --company-id 245 --min-shared 3

Exit code: 1 if any shared hero (or known-bad hero) is found, else 0 — so it
can gate an enrichment run before --apply.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

# Hashes of images proven to be site-wide junk, never a valid hero.
# Add to this as new ones are found — it makes the check permanent.
KNOWN_BAD_HASHES: dict[str, str] = {
    "f9f947f91fd616172a68268be1ae7758": "Comau corporate world-map network graphic (site-wide, not a product)",
}


def _hero_url(robot: dict[str, Any]) -> str:
    for key in ("s3_image", "image"):
        u = (robot.get(key) or "").strip()
        if u:
            return u
    return ""


def hash_image(url: str, timeout: float = 30.0) -> tuple[str, str]:
    """Return (md5_hex, error). Downloads fully — hashing needs the whole body."""
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "RobotAIGeekDupeCheck/1.0"})
        if resp.status_code != 200:
            return "", f"HTTP {resp.status_code}"
        body = resp.content
        if not body:
            return "", "empty body"
        return hashlib.md5(body).hexdigest(), ""
    except requests.RequestException as exc:
        return "", str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect shared/duplicate robot hero images by content hash")
    parser.add_argument("--company-id", type=int)
    parser.add_argument("--ids", type=int, nargs="*")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument(
        "--min-shared",
        type=int,
        default=2,
        help="Flag a hero image used by at least this many robots (default 2)",
    )
    args = parser.parse_args()

    if not args.company_id and not args.ids:
        print("Need --company-id or --ids", file=sys.stderr)
        return 2

    client = ResearchApiClient()
    robots: list[dict[str, Any]] = []
    if args.company_id:
        robots.extend(client.list_robots_for_company(args.company_id))
    for rid in args.ids or []:
        try:
            robots.append(client._get(f"robots/robots/{rid}/"))
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {rid}: {exc}", file=sys.stderr)

    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []
    no_hero: list[dict[str, Any]] = []

    for r in robots:
        url = _hero_url(r)
        row = {"id": r.get("id"), "name": r.get("name"), "status": r.get("status"), "url": url}
        if not url:
            no_hero.append(row)
            continue
        digest, err = hash_image(url)
        if err:
            errors.append({**row, "error": err})
            continue
        by_hash[digest].append(row)

    shared = {h: rows for h, rows in by_hash.items() if len(rows) >= args.min_shared}
    known_bad = {h: rows for h, rows in by_hash.items() if h in KNOWN_BAD_HASHES}

    print(f"robots checked: {len(robots)} | with hero: {len(robots) - len(no_hero)} "
          f"| distinct heroes: {len(by_hash)} | errors: {len(errors)}")

    if known_bad:
        print("\n!! KNOWN-BAD hero images (site-wide junk, must be replaced):")
        for h, rows in known_bad.items():
            print(f"   {h[:12]}... — {KNOWN_BAD_HASHES[h]}")
            print(f"   used as hero by {len(rows)} robots: {', '.join(str(x['id']) for x in rows)}")

    if shared:
        print(f"\n!! SHARED heroes (same image on >= {args.min_shared} robots):")
        for h, rows in sorted(shared.items(), key=lambda kv: -len(kv[1])):
            tag = f"  [{KNOWN_BAD_HASHES[h]}]" if h in KNOWN_BAD_HASHES else ""
            print(f"   {h[:12]}... on {len(rows)} robots{tag}")
            for x in rows[:12]:
                print(f"        {x['id']:6} {str(x['name'])[:34]:34} {x['status']}")
            if len(rows) > 12:
                print(f"        ... +{len(rows) - 12} more")
    else:
        print("\nOK: no hero image is shared between robots.")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {
                    "checked": len(robots),
                    "distinct_heroes": len(by_hash),
                    "shared": {h: rows for h, rows in shared.items()},
                    "known_bad": {h: rows for h, rows in known_bad.items()},
                    "errors": errors,
                    "no_hero": no_hero,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nreport: {args.json_out}")

    # Fail closed so this can gate a run before --apply.
    return 1 if (shared or known_bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
