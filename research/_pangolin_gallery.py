"""Hash every /public/uploads image on unique Pangolin PDPs; skip shared banner."""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ssl._create_default_https_context = ssl._create_unverified_context
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
BASE = "https://www.alpha-robot.com.cn"
SHARED_BANNER = "eee172ad753e9d623e64b52a8053981a"
OUT_DIR = _RESEARCH_DIR / "staging" / "pangolin_gallery"
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT = _RESEARCH_DIR / "staging" / "reports" / "pangolin-gallery.json"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def abs_url(path: str) -> str:
    if path.startswith("http"):
        return path
    return BASE + path


def main() -> None:
    recon = json.loads(
        (_RESEARCH_DIR / "staging" / "reports" / "pangolin-recon.json").read_text(
            encoding="utf-8"
        )
    )
    # unique URLs only — recon is {id: row} or {robots/rows: [...]}
    by_url: dict[str, list] = defaultdict(list)
    rows = []
    if isinstance(recon, dict) and any(
        isinstance(v, dict) and ("url" in v or "id" in v) for v in recon.values()
    ):
        rows = list(recon.values())
    else:
        rows = recon.get("robots") or recon.get("rows") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get("url") or row.get("oem_url") or ""
        rid = row.get("id") or row.get("robot_id")
        name = row.get("name") or row.get("title") or ""
        if url:
            by_url[url].append({"id": rid, "name": name})

    hash_to_pages: dict[str, list] = defaultdict(list)
    page_report = []

    for url, robots in sorted(by_url.items(), key=lambda x: -len(x[1])):
        try:
            html = fetch(url).decode("utf-8", "replace")
        except Exception as e:
            print(f"FAIL {url}: {e}")
            continue
        title_m = re.search(r"<title>([^<]+)", html)
        title = title_m.group(1).strip() if title_m else ""
        uploads = re.findall(
            r'(?:src|data-src|data-original|href)="(/public/uploads/images/[^"]+\.(?:png|jpe?g|webp|gif))"',
            html,
            re.I,
        )
        # also bare in style/background
        uploads += re.findall(
            r"(/public/uploads/images/[0-9a-f/]+\.(?:png|jpe?g|webp))", html, re.I
        )
        seen_paths = []
        for p in uploads:
            if p not in seen_paths:
                seen_paths.append(p)

        candidates = []
        for path in seen_paths:
            if SHARED_BANNER in path:
                continue
            if "/logo" in path.lower() or "static" in path:
                continue
            full = abs_url(path)
            try:
                data = fetch(full)
            except Exception as e:
                candidates.append({"path": path, "error": str(e)})
                continue
            if len(data) < 8000:
                continue
            if data[:3] not in (b"\xff\xd8\xff", b"\x89PN") and data[:4] != b"RIFF":
                # allow png/jpeg/webp
                if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8"):
                    continue
            md5 = hashlib.md5(data).hexdigest()
            fname = f"{md5[:12]}_{Path(path).name}"
            (OUT_DIR / fname).write_bytes(data)
            candidates.append(
                {
                    "path": path,
                    "url": full,
                    "bytes": len(data),
                    "md5": md5,
                    "file": fname,
                }
            )
            hash_to_pages[md5].append(
                {
                    "url": url,
                    "title": title,
                    "robots": robots,
                    "path": path,
                }
            )

        page_report.append(
            {
                "url": url,
                "title": title,
                "robots": robots,
                "n_robots": len(robots),
                "candidates": candidates,
            }
        )
        print(
            f"{len(robots):2d}r | {title[:40]:40s} | {len(candidates):2d} imgs | {url}"
        )

    # images that appear on only one unique URL are likely model-specific
    unique = {h: pages for h, pages in hash_to_pages.items() if len({p["url"] for p in pages}) == 1}
    shared = {h: pages for h, pages in hash_to_pages.items() if len({p["url"] for p in pages}) > 1}

    print("\n=== UNIQUE hashes (1 page only)", len(unique))
    for h, pages in list(unique.items())[:40]:
        p0 = pages[0]
        print(f"  {h[:12]} {p0['title'][:36]} {p0['path']}")

    print("\n=== SHARED hashes (multi-page)", len(shared))
    for h, pages in sorted(shared.items(), key=lambda x: -len({p["url"] for p in x[1]}))[:20]:
        urls = {p["url"] for p in pages}
        print(f"  {h[:12]} on {len(urls)} pages  e.g. {pages[0]['path']}")

    REPORT.write_text(
        json.dumps(
            {
                "pages": page_report,
                "unique_hashes": {h: pages for h, pages in unique.items()},
                "shared_hashes": {
                    h: {"n_pages": len({p["url"] for p in pages}), "pages": pages}
                    for h, pages in shared.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", REPORT)


if __name__ == "__main__":
    main()
