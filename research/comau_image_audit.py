"""Image audit for Comau (company 245).

Downloads every candidate image referenced by comau-recon-all.json (plus each
robot's CURRENT primary from the API), hashes the bytes, and clusters identical
images. This is what exposes the defect the URL cannot: Comau's corporate
world-map network graphic is byte-identical across 32 robots yet is served under
per-robot CDN names (photo-<robotid>-<photoid>.webp).

Outputs staging/reports/comau-image-audit.json:
  - clusters: md5 -> {urls, size, dims, robots_referencing, is_banned}
  - current_primary: robot id -> {url, md5, is_banned}

Nothing here writes to the DB.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 245
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}

# Comau corporate world-map network graphic — never a product image.
BANNED_MD5 = {"f9f947f91fd616172a68268be1ae7758"}

CACHE = _RESEARCH_DIR / "staging" / "reports" / "comau-img-cache"


def is_image_bytes(data: bytes) -> bool:
    """Validate by magic bytes, not Content-Type.

    Our CDN serves these objects as `application/octet-stream`, so a
    content-type check silently drops exactly the images we most need to audit
    (that is how the world-map hero evaded an earlier pass).
    """
    return (
        data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"\xff\xd8\xff"
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
        or data[:6] in (b"GIF87a", b"GIF89a")
    )


def fetch(url: str) -> tuple[bytes | None, str]:
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    CACHE.mkdir(parents=True, exist_ok=True)
    blob = CACHE / key
    if blob.is_file():
        return blob.read_bytes(), "cache"
    try:
        r = requests.get(url, headers=HEADERS, timeout=45)
    except requests.RequestException as exc:
        return None, f"error:{exc}"
    if r.status_code != 200:
        return None, f"http:{r.status_code}"
    if not is_image_bytes(r.content):
        return None, "not-an-image"
    blob.write_bytes(r.content)
    return r.content, "fetched"


def dims(data: bytes) -> tuple[int, int] | None:
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit Comau candidate images by content hash")
    ap.add_argument("--recon", type=str, default="staging/reports/comau-recon-all.json")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    recon = json.loads((_RESEARCH_DIR / args.recon).read_text(encoding="utf-8"))
    client = ResearchApiClient()
    robots = {int(r["id"]): r for r in client.list_robots_for_company(COMPANY_ID)}

    clusters: dict[str, dict] = {}
    current_primary: dict[str, dict] = {}
    current_gallery: dict[str, list] = {}

    def record(url: str, rid: int, role: str) -> str | None:
        data, how = fetch(url)
        if data is None:
            return None
        md5 = hashlib.md5(data).hexdigest()
        c = clusters.setdefault(md5, {
            "md5": md5, "urls": [], "bytes": len(data), "dims": dims(data),
            "robots": [], "is_banned": md5 in BANNED_MD5,
        })
        if url not in c["urls"]:
            c["urls"].append(url)
        tag = f"{rid}:{role}"
        if tag not in c["robots"]:
            c["robots"].append(tag)
        return md5

    for rid_s, info in recon.items():
        rid = int(rid_s)
        r = robots.get(rid) or {}
        # current primary as stored today (CDN) — this is where the map lives
        cur = (r.get("s3_image") or r.get("image") or "").strip()
        if cur:
            md5 = record(cur, rid, "current_primary")
            current_primary[rid_s] = {
                "url": cur, "md5": md5, "is_banned": bool(md5 and md5 in BANNED_MD5),
            }
        # Existing gallery (RobotPhoto rows) — where duplicate/sibling reuse hides.
        gallery = []
        for p in (r.get("photos") or []):
            pu = (p.get("s3_image") or p.get("image_url") or p.get("image") or "").strip()
            if not pu:
                continue
            pmd5 = record(pu, rid, "photo_primary" if p.get("is_primary") else "photo")
            gallery.append({
                "url": pu, "md5": pmd5, "is_primary": bool(p.get("is_primary")),
                "is_banned": bool(pmd5 and pmd5 in BANNED_MD5),
            })
        if gallery:
            current_gallery[rid_s] = gallery
        cands = []
        if info.get("og_image"):
            cands.append((info["og_image"], "og"))
        for u in info.get("header_images", []):
            cands.append((u, "header"))
        for u in info.get("render_images", []):
            cands.append((u, "render"))
        for u, role in cands:
            record(u, rid, role)
        print(f"{rid} {info.get('name')}: {len(cands)} candidates", flush=True)

    out = {
        "clusters": clusters,
        "current_primary": current_primary,
        "current_gallery": current_gallery,
        "summary": {
            "unique_images": len(clusters),
            "banned_clusters": [m for m, c in clusters.items() if c["is_banned"]],
            "robots_with_banned_primary": [k for k, v in current_primary.items() if v["is_banned"]],
        },
    }
    dest = _RESEARCH_DIR / "staging" / "reports" / "comau-image-audit.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nunique images: {len(clusters)}")
    print(f"robots with BANNED (world-map) primary: {len(out['summary']['robots_with_banned_primary'])}")
    # shared clusters = same bytes referenced by >1 robot
    shared = {m: c for m, c in clusters.items() if len({t.split(':')[0] for t in c["robots"]}) > 1}
    print(f"clusters shared across >1 robot: {len(shared)}")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
