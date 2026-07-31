"""Download existing CRM heroes + OEM og/attr heroes for visual verify."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

OUT = Path("staging/ep1274_heroes")
OUT.mkdir(parents=True, exist_ok=True)


def save(name: str, url: str) -> dict:
    try:
        r = requests.get(url, timeout=60, headers=HEADERS)
        data = r.content
        md5 = hashlib.md5(data).hexdigest()
        magic = (
            "png"
            if data[:8] == b"\x89PNG\r\n\x1a\n"
            else "jpg"
            if data[:3] == b"\xff\xd8\xff"
            else "webp"
            if data[:4] == b"RIFF"
            else "other"
        )
        ext = "webp" if magic == "webp" else ("png" if magic == "png" else "jpg")
        path = OUT / f"{name}.{ext}"
        path.write_bytes(data)
        print(f"{name}: {r.status_code} {len(data)} md5={md5} {magic} -> {path.name}")
        return {"name": name, "url": url, "status": r.status_code, "bytes": len(data), "md5": md5, "path": str(path)}
    except Exception as e:
        print(f"{name}: ERR {e}")
        return {"name": name, "url": url, "error": str(e)}


def main() -> None:
    c = ResearchApiClient()
    robots = {r["id"]: r for r in c.list_robots_for_company(1274)}
    meta = {}

    # Existing CRM images
    for rid in [2752, 2751, 2750, 2749, 2748, 2747, 2746]:
        r = robots[rid]
        url = r.get("s3_image") or r.get("image") or ""
        if url:
            meta[f"crm_{rid}"] = save(f"crm_{rid}", url)

    # Preferred OEM heroes from scrape
    scrape = json.loads(Path("staging/reports/_ep1274_pdp_scrape.json").read_text(encoding="utf-8"))
    for rid_s, info in scrape.items():
        if not rid_s.isdigit():
            continue
        rid = int(rid_s)
        # Prefer og (usually cleaner product shot) then first attr_11 / non-thumb
        cands = []
        if info.get("og"):
            cands.append(("og", info["og"]))
        for i, u in enumerate((info.get("heroes") or [])[:4]):
            cands.append((f"h{i}", u))
        for i, u in enumerate((info.get("cdn_all") or [])[:3]):
            if "thumbnail" in u.lower():
                continue
            cands.append((f"c{i}", u))
        seen = set()
        for label, u in cands[:6]:
            if u in seen:
                continue
            seen.add(u)
            meta[f"{rid}_{label}"] = save(f"{rid}_{label}", u)

    # Hash uniqueness among preferred
    print("\n=== MD5 INDEX ===")
    by_md5 = {}
    for k, v in meta.items():
        md5 = v.get("md5")
        if md5:
            by_md5.setdefault(md5, []).append(k)
    for md5, keys in by_md5.items():
        if len(keys) > 1:
            print(f"SHARED {md5}: {keys}")

    Path("staging/reports/_ep1274_visual_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
