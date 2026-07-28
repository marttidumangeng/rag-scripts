"""Hash the CURRENT media of company-32 robots that are NOT in the repair batch.

Two jobs:
  1. Collision guard — a proposed image must not equal any image already on a
     robot we are not touching (the curated 4676-4720 greenfield batch, and the
     3 published records 76/265/266 which are off-limits).
  2. Duplicate-record detection — if a batch record's only available source
     images are byte-identical to an out-of-batch robot's, the two records are
     the same product (e.g. 2473 "ECOVACS DEEBOT mini 2" vs 4720 "DEEBOT mini 2").

Magic-byte validation only: our CDN serves .webp as application/octet-stream,
so a Content-Type check reports a false clean.
"""
from __future__ import annotations
import hashlib, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

_D = Path(__file__).resolve().parent
sys.path.insert(0, str(_D))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

OUT = _D / "staging" / "reports" / "ecovacs_existing_hashes.json"
BATCH = {1937, 1939, 1941, 1943, 1945, 1947, 1949, 1951, 1952, 1954, 1955, 1956, 1957,
         1958, 1959, 1960, 1961, 1962, 1963, 1964, 1965, 2473, 2474, 2475, 2476, 2477,
         2478, 2479, 2480, 2517, 2518}


def sniff(b: bytes) -> str | None:
    if b[:3] == b"\xff\xd8\xff": return "jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n": return "png"
    if b[:6] in (b"GIF87a", b"GIF89a"): return "gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP": return "webp"
    if b[4:12] in (b"ftypavif", b"ftypavis"): return "avif"
    return None


def grab(url: str):
    try:
        r = requests.get(url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
    except Exception as e:
        return {"url": url, "error": e.__class__.__name__}
    if r.status_code != 200:
        return {"url": url, "error": f"http_{r.status_code}"}
    k = sniff(r.content)
    if not k:
        return {"url": url, "error": "not_an_image", "ctype": r.headers.get("Content-Type")}
    return {"url": url, "md5": hashlib.md5(r.content).hexdigest(), "kind": k,
            "bytes": len(r.content)}


def main():
    c = ResearchApiClient()
    robots = c.list_robots_for_company(32)
    out = {}
    jobs = []
    for r in robots:
        if r["id"] in BATCH:
            continue
        urls = []
        for k in ("s3_image", "image"):
            if (r.get(k) or "").strip():
                urls.append(r[k].strip())
        for p in (r.get("photos") or []):
            u = (p.get("s3_image") or p.get("image") or "").strip()
            if u:
                urls.append(u)
        urls = list(dict.fromkeys(urls))
        out[r["id"]] = {"name": r["name"], "status": r["status"], "urls": urls, "images": []}
        jobs += [(r["id"], u) for u in urls]

    print(f"hashing {len(jobs)} images across {len(out)} out-of-batch robots...")
    with ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(lambda j: (j[0], grab(j[1])), jobs))
    for rid, rec in res:
        out[rid]["images"].append(rec)

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for _, r in res if r.get("md5"))
    bad = [(rid, r) for rid, r in res if not r.get("md5")]
    print(f"hashed ok: {ok}  errors: {len(bad)}")
    for rid, r in bad:
        print(f"   !! {rid} {r.get('error')} ctype={r.get('ctype')} {r['url'][:80]}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
