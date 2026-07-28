"""Extract Monarch Quest content: press release + hero candidates + YouTube."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

from load_env import load_research_env

load_research_env()
from web_extract import WebFetcher, parse_page
from youtube_metadata import enrich_video_list, fetch_youtube_metadata

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}
OUT = Path("staging/reports/auris-detail.json")
MEDIA = Path("staging/media/auris")
MEDIA.mkdir(parents=True, exist_ok=True)

PAGES = [
    "https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/",
    "https://www.jnjmedtech.com/en-US/news/press-releases/johnson-johnson-medtech-announces-clearance-of-monarch-quest-for-enhanced-robotic-assisted-bronchoscopy/",
    "https://www.jnj.com/media-center/press-releases/johnson-johnson-medtech-announces-clearance-of-monarchtm-quest-for-enhanced-robotic-assisted-bronchoscopy",
    "https://www.jnjmedtech.com/en-US/specialties/interventional-pulmonology/",
    "https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/evidence/",
]

fetcher = WebFetcher(stealth=False)
pages = []
all_imgs: list[str] = []

for url in PAGES:
    try:
        p = parse_page(fetcher, url, rendered=False)
    except Exception as e:
        pages.append({"url": url, "error": str(e)})
        print(f"ERR {url}: {e}", flush=True)
        continue
    if not p:
        pages.append({"url": url, "error": "empty"})
        print(f"EMPTY {url}", flush=True)
        continue
    imgs = []
    for im in p.images or []:
        u = im.get("url") if isinstance(im, dict) else str(im)
        if not u or str(u).startswith("data:"):
            continue
        full = urljoin(url, str(u))
        imgs.append(full)
        all_imgs.append(full)
    pages.append({
        "url": url,
        "title": p.title or "",
        "chars": len(p.text or ""),
        "text": (p.text or "")[:8000],
        "images": imgs[:40],
    })
    print(f"OK {url} chars={len(p.text or '')} imgs={len(imgs)}", flush=True)

# Filter hero candidates
junk = ("logo", "icon", "favicon", "sprite", "svg", "badge", "social", "arrow", "button", "pixel", "tracking", "1x1")
heroes = []
seen = set()
for u in all_imgs:
    low = u.lower()
    if any(j in low for j in junk):
        continue
    if not re.search(r"\.(png|jpe?g|webp)(\?|$)", low):
        continue
    if u in seen:
        continue
    seen.add(u)
    # Prefer monarch/robot/quest/product wording in path
    score = 0
    for tok in ("monarch", "quest", "bronch", "robot", "platform", "lung", "scope"):
        if tok in low:
            score += 2
    if "jnjmedtech" in low or "jnj" in low:
        score += 1
    heroes.append({"url": u, "score": score})

heroes.sort(key=lambda x: -x["score"])

# HEAD/GET verify top candidates and download
verified = []
session = requests.Session()
session.headers.update(HEADERS)
for h in heroes[:25]:
    url = h["url"]
    try:
        r = session.get(url, timeout=40, stream=True)
        ctype = (r.headers.get("content-type") or "").lower()
        raw = r.content
        ok = r.status_code == 200 and "image" in ctype and len(raw) > 20000
        entry = {**h, "status": r.status_code, "bytes": len(raw), "ctype": ctype, "ok": ok}
        if ok:
            ext = ".png" if "png" in url.lower() or "png" in ctype else ".jpg"
            path = MEDIA / f"cand_{len(verified)}{ext}"
            path.write_bytes(raw)
            entry["path"] = str(path)
            verified.append(entry)
            print(f"IMG OK score={h['score']} bytes={len(raw)} {url[:100]}", flush=True)
        else:
            print(f"IMG skip status={r.status_code} bytes={len(raw)} {url[:90]}", flush=True)
        if len(verified) >= 8:
            break
    except Exception as e:
        print(f"IMG ERR {e} {url[:80]}", flush=True)

# YouTube HTML search
def yt_ids(query: str, limit: int = 6) -> list[str]:
    try:
        resp = session.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            timeout=30,
        )
    except requests.RequestException:
        return []
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
    out = []
    for v in ids:
        if v not in out:
            out.append(v)
        if len(out) >= limit:
            break
    return out

yt_urls = []
for q in [
    "Monarch Quest Johnson Johnson bronchoscopy",
    "Monarch Platform Auris bronchoscopy",
    "J&J MONARCH Quest robotic bronchoscopy",
    "Monarch Platform robotic-assisted bronchoscopy",
]:
    for vid in yt_ids(q):
        u = f"https://www.youtube.com/watch?v={vid}"
        if u not in yt_urls:
            yt_urls.append(u)

enriched = enrich_video_list(yt_urls[:12])
yt_meta = []
for item in enriched:
    u = item.get("url") if isinstance(item, dict) else str(item)
    title = (item.get("title") if isinstance(item, dict) else "") or ""
    yt_meta.append({"url": u, "title": title})
    print(f"YT: {title.encode('ascii','replace').decode()} | {u}", flush=True)

OUT.write_text(
    json.dumps(
        {"pages": pages, "verified_images": verified, "youtube": yt_meta},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(f"wrote {OUT} verified={len(verified)} yt={len(yt_meta)}", flush=True)
