"""Hunt model-specific heroes for imageless Universal Robots rows."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

OUT = _RESEARCH_DIR / "staging" / "ur_heroes" / "chase"
OUT.mkdir(parents=True, exist_ok=True)

SESS = requests.Session()
SESS.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Candidate URLs to probe (OEM media + known Storyblok naming patterns + Wayback).
PROBES: dict[str, list[str]] = {
    "UR5e": [
        "https://a.storyblok.com/f/169662/3000x3000/96d3f57b1b/ur5e-2024-warm50-1x1-68pct-01.png",
        "https://a.storyblok.com/f/169662/3000x3000/9104e1d987/ur5e-2024-warm50-1x1-68pct-01.png",
        "https://a.storyblok.com/f/169662/832x624/ur5e_product_image_4-3.png",
        "https://a.storyblok.com/f/169662/1072x1364/ur5e_product_4-3.png",
        "https://a.storyblok.com/f/169662/1125x1500/png-ur5e.png",
        "https://www.universal-robots.com/media/1809444/ur5e.png",
        "https://www.universal-robots.com/media/1809445/ur5e.png",
        "https://www.universal-robots.com/media/1815041/ur5e.png",
        "https://www.universal-robots.com/media/18085/ur5e.png",
        "https://www.universal-robots.com/media/29255/ur5e.jpg",
        "https://www.universal-robots.com/media/1808035/ur5e-robot.png",
        "https://www.universal-robots.com/media/1808036/ur5e.png",
        "https://www.universal-robots.com/media/15555/ur5e.png",
        "https://www.universal-robots.com/media/1809444/ur5e-product.png",
    ],
    "UR10e": [
        "https://a.storyblok.com/f/169662/3000x3000/ur10e-2024-warm50-1x1-68pct-01.png",
        "https://a.storyblok.com/f/169662/832x624/ur10e_product_image_4-3.png",
        "https://a.storyblok.com/f/169662/1072x1364/ur10e_product_4-3.png",
        "https://a.storyblok.com/f/169662/1125x1500/png-ur10e.png",
        "https://www.universal-robots.com/media/1809446/ur10e.png",
        "https://www.universal-robots.com/media/1815042/ur10e.png",
        "https://www.universal-robots.com/media/1808037/ur10e.png",
        "https://www.universal-robots.com/media/29256/ur10e.jpg",
    ],
    "UR3": [
        "https://www.universal-robots.com/media/240742/ur3.png",
        "https://www.universal-robots.com/media/50587/ur3.png",
        "https://www.universal-robots.com/media/18085/ur3.png",
        "https://www.universal-robots.com/media/15554/ur3.png",
        "https://www.universal-robots.com/media/12955/ur3.jpg",
        "https://www.universal-robots.com/media/1808030/ur3.png",
    ],
    "UR5": [
        "https://www.universal-robots.com/media/50588/ur5.png",
        "https://www.universal-robots.com/media/18085/ur5.png",
        "https://www.universal-robots.com/media/15553/ur5.png",
        "https://www.universal-robots.com/media/12954/ur5.jpg",
        "https://www.universal-robots.com/media/1808031/ur5.png",
        "https://www.universal-robots.com/media/1828033/ur5.png",
    ],
    "UR10": [
        "https://www.universal-robots.com/media/50895/ur10.png",
        "https://www.universal-robots.com/media/18085/ur10.png",
        "https://www.universal-robots.com/media/15552/ur10.png",
        "https://www.universal-robots.com/media/12953/ur10.jpg",
        "https://www.universal-robots.com/media/1808032/ur10.png",
        "https://www.universal-robots.com/media/1828035/ur10.png",
    ],
}

PAGES = [
    "https://www.universal-robots.com/products/",
    "https://www.universal-robots.com/products/e-series/",
    "https://www.universal-robots.com/news/",
    "https://www.universal-robots.com/about-universal-robots/news/",
    "https://web.archive.org/web/20230601000000/https://www.universal-robots.com/products/ur5e/",
    "https://web.archive.org/web/20230601000000/https://www.universal-robots.com/products/ur10e/",
    "https://web.archive.org/web/20190101000000/https://www.universal-robots.com/products/ur3-robot/",
    "https://web.archive.org/web/20190101000000/https://www.universal-robots.com/products/ur5-robot/",
    "https://web.archive.org/web/20190101000000/https://www.universal-robots.com/products/ur10-robot/",
    "https://web.archive.org/web/20200101000000/https://www.universal-robots.com/products/ur5e/",
    "https://web.archive.org/web/20210101000000/https://www.universal-robots.com/products/ur5e/",
    "https://web.archive.org/web/20220101000000/https://www.universal-robots.com/products/ur5e/",
    "https://web.archive.org/web/20200101000000/https://www.universal-robots.com/products/ur10e/",
]


def _is_image(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or (
        data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    )


def probe_url(url: str) -> dict | None:
    try:
        r = SESS.get(url, timeout=45, allow_redirects=True)
    except requests.RequestException as e:
        return {"url": url, "ok": False, "err": str(e)}
    if r.status_code != 200:
        return {"url": url, "ok": False, "status": r.status_code}
    data = r.content
    if not _is_image(data) or len(data) < 8000:
        return {
            "url": url,
            "ok": False,
            "status": r.status_code,
            "bytes": len(data),
            "not_image": True,
        }
    return {
        "url": str(r.url),
        "ok": True,
        "status": r.status_code,
        "bytes": len(data),
        "md5": hashlib.md5(data).hexdigest(),
        "data": data,
    }


def scrape_page_images(url: str) -> list[str]:
    try:
        r = SESS.get(url, timeout=60, allow_redirects=True)
    except requests.RequestException:
        return []
    if r.status_code != 200:
        print(f"PAGE {url} -> {r.status_code}")
        return []
    html = r.text
    title_m = re.search(r"<title[^>]*>([^<]+)", html, re.I)
    title = (title_m.group(1).strip() if title_m else "")[:90]
    print(f"PAGE {url} -> {r.status_code} final={r.url} title={title!r}")
    found = set()
    for pat in (
        r"https://a\.storyblok\.com/f/169662/[^\"'\s)>]+",
        r"https://www\.universal-robots\.com/media/\d+/[^\"'\s)>]+\.(?:png|jpg|jpeg|webp)",
        r"/media/\d+/[^\"'\s)>]+\.(?:png|jpg|jpeg|webp)",
        r"https://web\.archive\.org/web/\d+im_/https://[^\"'\s)>]+\.(?:png|jpg|jpeg|webp)",
    ):
        for m in re.findall(pat, html, re.I):
            u = m
            if u.startswith("/media/"):
                u = "https://www.universal-robots.com" + u
            found.add(u.split("?")[0])
    return sorted(found)


def model_tokens(model: str) -> list[str]:
    raw = model.lower().replace(" ", "")
    toks = [raw, model.lower().replace(" ", "-"), model.lower().replace(" ", "_")]
    # avoid UR3 matching UR3e
    return toks


def filename_matches(model: str, url: str) -> bool:
    name = Path(url.split("?")[0]).name.lower()
    # strip extension
    stem = re.sub(r"\.(png|jpg|jpeg|webp)$", "", name)
    stem = re.sub(r"[^a-z0-9]+", "", stem)
    m = model.lower().replace(" ", "")
    if m.endswith("e") and len(m) >= 3:
        # UR5e must contain ur5e, not just ur5
        return m in stem
    # CB series: ur3 / ur5 / ur10 must NOT be followed by e in stem
    if m + "e" in stem:
        return False
    # require model token as contiguous
    if m not in stem:
        return False
    # reject if another e-series sneaks in
    for other in ("ur3e", "ur5e", "ur7e", "ur10e", "ur12e", "ur16e"):
        if other != m and other in stem and m not in other:
            # if stem is ur10e and model is ur10 — reject
            if other.startswith(m):
                return False
    return True


def main() -> int:
    hits: dict[str, list[dict]] = {k: [] for k in PROBES}
    # 1) probe curated guesses
    for model, urls in PROBES.items():
        print(f"\n=== PROBE {model} ({len(urls)} urls) ===")
        for u in urls:
            rec = probe_url(u)
            if not rec:
                continue
            if rec.get("ok"):
                print(f"  HIT {rec['bytes']} md5={rec['md5']} {rec['url']}")
                hits[model].append(rec)
            else:
                print(f"  miss {rec.get('status') or rec.get('err')} {u}")

    # 2) scrape pages + filter by filename token
    print("\n=== SCRAPE PAGES ===")
    page_imgs: list[str] = []
    for page in PAGES:
        page_imgs.extend(scrape_page_images(page))
    page_imgs = sorted(set(page_imgs))
    print(f"unique page images: {len(page_imgs)}")

    for model in PROBES:
        matched = [u for u in page_imgs if filename_matches(model, u)]
        print(f"\n=== PAGE MATCH {model}: {len(matched)} ===")
        for u in matched[:40]:
            print(f"  cand {u}")
            rec = probe_url(u)
            if rec and rec.get("ok"):
                print(f"    HIT {rec['bytes']} md5={rec['md5']}")
                # dedupe by md5
                if not any(h["md5"] == rec["md5"] for h in hits[model]):
                    hits[model].append(rec)

    # 3) save hits
    summary = {}
    for model, recs in hits.items():
        summary[model] = []
        for i, rec in enumerate(recs):
            data = rec.pop("data", b"")
            ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
            path = OUT / f"{model}_{i}.{ext}"
            path.write_bytes(data)
            rec["path"] = str(path)
            summary[model].append({k: v for k, v in rec.items() if k != "data"})
            print(f"SAVED {model} -> {path.name} {rec['url']}")

    out_json = _RESEARCH_DIR / "staging" / "reports" / "ur-image-chase.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote {out_json}")
    for model, recs in summary.items():
        print(f"  {model}: {len(recs)} hits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
