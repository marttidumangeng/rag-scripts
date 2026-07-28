"""Post-apply verification: did copy-media land EVERY image, byte-intact?

This company is the first real exercise of the server fix that made copy-media
sniff magic bytes instead of trusting Content-Type (WebP sources served as
application/octet-stream previously never reached S3, and the ext fallback saved
WebP bytes under .jpg names). So we check, per robot:

  * landed photo count == intended count (no silent drops)
  * every landed CDN URL returns HTTP 200 AND valid image magic bytes
  * the landed extension matches the actual sniffed format (catches the old
    "WebP bytes saved as .jpg" mislabel)
  * no duplicate bytes within a robot or across the company
"""
from __future__ import annotations
import hashlib, json, sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

_D = Path(__file__).resolve().parent
sys.path.insert(0, str(_D))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
import fix_ecovacs_media as F


def sniff(b: bytes) -> str | None:
    if b[:3] == b"\xff\xd8\xff": return "jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n": return "png"
    if b[:6] in (b"GIF87a", b"GIF89a"): return "gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP": return "webp"
    if b[4:12] in (b"ftypavif", b"ftypavis"): return "avif"
    return None


EXT_OK = {"jpeg": {".jpg", ".jpeg"}, "png": {".png"}, "webp": {".webp"},
          "gif": {".gif"}, "avif": {".avif"}}


def grab(url: str):
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    except Exception as e:
        return {"url": url, "error": e.__class__.__name__}
    if r.status_code != 200:
        return {"url": url, "error": f"http_{r.status_code}"}
    k = sniff(r.content)
    if not k:
        return {"url": url, "error": "not_an_image", "ctype": r.headers.get("Content-Type")}
    return {"url": url, "md5": hashlib.md5(r.content).hexdigest(), "kind": k,
            "bytes": len(r.content), "ctype": r.headers.get("Content-Type") or ""}


def main():
    intended = {rid: len(v) for rid, v in F.build_media().items()}
    c = ResearchApiClient()
    robots = {r["id"]: r for r in c.list_robots_for_company(32)}

    jobs, meta = [], {}
    for rid in intended:
        r = robots[rid]
        urls = []
        for p in (r.get("photos") or []):
            u = (p.get("s3_image") or p.get("image") or "").strip()
            if u:
                urls.append(u)
        meta[rid] = {"name": r["name"], "urls": urls}
        jobs += [(rid, u) for u in urls]

    with ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(lambda j: (j[0], grab(j[1])), jobs))
    got = defaultdict(list)
    for rid, rec in res:
        got[rid].append(rec)

    all_hash = defaultdict(list)
    drops, badext, bad = [], [], []
    print(f"{'id':<6}{'name':<34}{'want':>5}{'got':>5}  status")
    for rid in sorted(intended):
        recs = got[rid]
        ok = [r for r in recs if r.get("md5")]
        errs = [r for r in recs if not r.get("md5")]
        want = intended[rid]
        if len(recs) < want:
            drops.append((rid, want, len(recs)))
        for r in ok:
            all_hash[r["md5"]].append(rid)
            ext = "." + r["url"].rsplit(".", 1)[-1].lower() if "." in r["url"].rsplit("/", 1)[-1] else ""
            if ext and ext not in EXT_OK.get(r["kind"], set()):
                badext.append((rid, r["kind"], ext, r["url"]))
        bad += [(rid, e) for e in errs]
        flag = "OK" if len(recs) == want and not errs else "!!"
        print(f"{rid:<6}{meta[rid]['name'][:33]:<34}{want:>5}{len(ok):>5}  {flag}")

    print("\n--- copy-media drops (landed < intended) ---")
    print("  none" if not drops else "\n".join(f"  {r} want={w} got={g}" for r, w, g in drops))
    print("--- dead / non-image landed objects ---")
    print("  none" if not bad else "\n".join(f"  {r} {e.get('error')} ctype={e.get('ctype')} {e['url'][:70]}" for r, e in bad))
    print("--- extension != sniffed format (old WebP-as-.jpg mislabel) ---")
    print("  none" if not badext else "\n".join(f"  {r} sniffed={k} ext={e} {u[:66]}" for r, k, e, u in badext))
    dupes = {h: rs for h, rs in all_hash.items() if len(rs) > 1}
    print("--- duplicate bytes within/across robots ---")
    print("  none" if not dupes else "\n".join(f"  {rs} {h[:12]}" for h, rs in dupes.items()))

    kinds = defaultdict(int)
    ctypes = defaultdict(int)
    for _, r in res:
        if r.get("md5"):
            kinds[r["kind"]] += 1
            ctypes[r["ctype"]] += 1
    print(f"\nlanded images: {sum(kinds.values())} | formats: {dict(kinds)}")
    print(f"content-types served by CDN: {dict(ctypes)}")
    return 0 if not (drops or bad or badext or dupes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
