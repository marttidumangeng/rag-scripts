"""Media self-audit for the Ecovacs backfill — run BEFORE every --apply.

Enforces the two hard media rules:
  1. Hero must be a real product photo/render — never a dimension/CAD/spec-sheet
     diagram. (This tool surfaces heroes for visual Read; it flags likely
     diagram filenames but a human/agent LOOK is still required.)
  2. No duplicate images — dedupe by URL *and* by content hash (sha256 of the
     bytes), both WITHIN a robot's gallery and ACROSS every robot in the batch.
     Shared marketing assets between BLACK/base colour variants and OMNI
     siblings are the main trap.

Fails closed: exit 1 on any duplicate/dead/suspect image so the caller aborts.

    python audit_ecovacs_media.py                 # audit ROBOT_DATA in fix_ecovacs_robots
    python audit_ecovacs_media.py --ids 4720,4717
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

import fix_ecovacs_robots as F

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.ecovacs.com/"}

# Filename tokens that betray a schematic / spec-sheet / callout graphic rather
# than a product shot. Hero must never match these.
DIAGRAM_TOKENS = (
    "dimension", "size", "spec", "parameter", "drawing", "cad", "schematic",
    "exploded", "diagram", "structure", "chart", "compare", "comparison",
)


def looks_like_diagram(url: str) -> bool:
    tail = url.rsplit("/", 1)[-1].lower()
    return any(tok in tail for tok in DIAGRAM_TOKENS)


# Magic-byte signatures. NEVER validate an image by Content-Type: our own CDN
# serves image objects as `application/octet-stream`, so an `"image" in ctype`
# guard reports a false clean and silently hides broken/HTML-error bodies
# (this is exactly how the 32-robot Comau world-map defect stayed hidden).
def sniff_image(body: bytes) -> str | None:
    if body[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp"
    if body[:2] == b"BM":
        return "bmp"
    if body[4:12] in (b"ftypavif", b"ftypavis"):
        return "avif"
    if body[4:8] == b"ftyp" and b"heic" in body[8:24]:
        return "heic"
    return None


def fetch(url: str) -> tuple[int, bytes, str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=40)
        return r.status_code, r.content, (r.headers.get("Content-Type") or "")
    except requests.RequestException as exc:
        return 0, b"", f"ERR {exc}"


def load_live_media(ids: list[int]) -> dict[int, dict]:
    """Build an audit set from media ALREADY on the robots (company 32).

    Used for records we enrich text-only (replace_media=False): the existing
    CDN gallery still has to pass the diagram/duplicate gate, and our CDN is
    exactly the host that serves images as application/octet-stream.
    """
    from api_client import ResearchApiClient

    client = ResearchApiClient()
    live = {r["id"]: r for r in client.list_robots_for_company(F.COMPANY_ID)}
    out: dict[int, dict] = {}
    for rid in ids:
        r = live.get(rid)
        if r is None:
            print(f"SKIP {rid}: not under company {F.COMPANY_ID}", file=sys.stderr)
            continue
        hero = r.get("s3_image") or r.get("image") or ""
        gallery = [p.get("image") or p.get("url") or "" for p in (r.get("photos") or [])]
        images = [u for u in [hero, *gallery] if u]
        # de-dup the hero when it is also present in photos[] (same object)
        seen: set[str] = set()
        ordered = [u for u in images if not (u in seen or seen.add(u))]
        if not ordered:
            print(f"WARN {rid} {r.get('name')}: no media at all", file=sys.stderr)
            continue
        out[rid] = {"name": r.get("name") or str(rid), "images": ordered}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit Ecovacs robot media for diagrams/duplicates")
    ap.add_argument("--ids", type=str, default="")
    ap.add_argument("--out", type=str, default="")
    ap.add_argument("--live", action="store_true",
                    help="Audit media already on the robots (text-only passes) instead of ROBOT_DATA")
    args = ap.parse_args()

    if args.live:
        want = [int(x) for x in args.ids.split(",") if x.strip().isdigit()]
        if not want:
            print("--live requires --ids", file=sys.stderr)
            return 2
        F.ROBOT_DATA = load_live_media(want)  # type: ignore[assignment]

    ids = list(F.ROBOT_DATA)
    if args.ids.strip() and not args.live:
        want_s = {int(x) for x in args.ids.split(",") if x.strip().isdigit()}
        ids = [i for i in ids if i in want_s]

    by_hash: dict[str, list[tuple[int, str]]] = defaultdict(list)
    problems: list[str] = []
    report: list[dict] = []

    for rid in ids:
        data = F.ROBOT_DATA[rid]
        images = data["images"]
        name = data["name"]

        # URL-level dupes within the robot
        if len(set(images)) != len(images):
            dupes = [u for u in images if images.count(u) > 1]
            problems.append(f"{rid} {name}: duplicate URL in gallery -> {sorted(set(dupes))}")

        hero = images[0]
        if looks_like_diagram(hero):
            problems.append(f"{rid} {name}: HERO looks like a diagram/spec graphic -> {hero}")

        hashes: list[str] = []
        for idx, url in enumerate(images):
            status, body, ctype = fetch(url)
            kind = sniff_image(body)
            if status != 200 or kind is None or len(body) < 10_000:
                problems.append(
                    f"{rid} {name}: bad image [{status} magic={kind or 'NOT-AN-IMAGE'} "
                    f"{len(body)}B ctype={ctype}] {url}"
                )
                continue
            h = hashlib.sha256(body).hexdigest()
            hashes.append(h)
            by_hash[h].append((rid, url))

        # content-level dupes within the robot
        seen: dict[str, int] = {}
        for h in hashes:
            seen[h] = seen.get(h, 0) + 1
        within = {h: c for h, c in seen.items() if c > 1}
        if within:
            problems.append(f"{rid} {name}: {len(within)} duplicate image CONTENT hash(es) within gallery")

        report.append({
            "id": rid,
            "name": name,
            "hero": hero,
            "hero_diagram_suspect": looks_like_diagram(hero),
            "n_urls": len(images),
            "n_distinct_content": len(set(hashes)),
            "hero_sha256": hashes[0][:16] if hashes else None,
        })
        print(f"{rid} {name}: urls={len(images)} distinct_content={len(set(hashes))} "
              f"hero={'DIAGRAM?' if looks_like_diagram(hero) else 'ok'}")

    # cross-robot content reuse
    for h, uses in by_hash.items():
        rids = {rid for rid, _ in uses}
        if len(rids) > 1:
            problems.append(
                f"CROSS-MODEL duplicate image content {h[:16]} shared by robots {sorted(rids)}: "
                f"{[u for _, u in uses][:3]}"
            )

    print("\n=== AUDIT ===")
    if problems:
        for p in problems:
            print("  FAIL:", p)
    else:
        print("  PASS: no diagram heroes, no duplicate content within or across robots")

    out = Path(args.out) if args.out else _RESEARCH_DIR / "staging" / "reports" / "ecovacs-media-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"report": report, "problems": problems}, indent=2), encoding="utf-8")
    print(f"\nReport: {out}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
