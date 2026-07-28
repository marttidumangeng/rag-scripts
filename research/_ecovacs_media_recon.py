"""Recon: scrape every mapped Ecovacs PDP, download candidates, hash + measure.

Output: staging/reports/ecovacs_media_recon.json — one entry per robot with
ranked image candidates (md5, w, h, bytes, kind). Nothing is applied here.

Selection policy encoded:
  * hero must be a real product shot of THAT model
  * `id-<model>-920x920.png` listing image is the best hero (per lessons)
  * Chinese render names: 单地宝 = robot alone, 地宝基站 = robot + station,
    白色材质 = white colourway, 黑色材质 = black colourway  -> real renders
  * numbered `-N.jpg` page sections are long-form feature infographics -> reject
  * banners (aspect >= 2.2) are never product shots
  * validate by MAGIC BYTES, never Content-Type (our CDN + OSS serve octet-stream)
"""
from __future__ import annotations
import hashlib, io, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

_D = Path(__file__).resolve().parent
sys.path.insert(0, str(_D))
from PIL import Image

H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.ecovacs.com/"}
OUT = _D / "staging" / "reports" / "ecovacs_media_recon.json"
CACHE = _D / "staging" / "ecovacs_media_cache"
CACHE.mkdir(parents=True, exist_ok=True)

# robot id -> (model label, PDP url)  [resolved by _ecovacs_probe_pdps/_legacy]
PDP: dict[int, tuple[str, str]] = {
    1937: ("DEEBOT X5 OMNI", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-x5-omni-white"),
    1939: ("DEEBOT X9 PRO OMNI", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-x9-pro-omni-black"),
    1941: ("DEEBOT T50 MAX PRO OMNI", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/t50-max-pro-omni-white"),
    1943: ("DEEBOT T50 OMNI", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/t50-omni-white"),
    1945: ("WINBOT W2 OMNI", "https://www.ecovacs.com/global/winbot-window-cleaning-robot/winbot-w2-omni-white"),
    1947: ("WINBOT W2S", "https://www.ecovacs.com/us/shop/winbot-window-cleaning-robot/winbot-w2s"),
    1949: ("WINBOT W3 OMNI", "https://www.ecovacs.com/global/winbot-window-cleaning-robot/winbot-w3"),
    1951: ("GOAT A3000 LiDAR", "https://www.ecovacs.com/us/shop/goat-robotic-lawn-mower/goat-a3000-lidar"),
    1954: ("GOAT O800 RTK", "https://www.ecovacs.com/global/goat-robotic-lawn-mower/goat-o800-rtk-white"),
    1955: ("DEEBOT T30 PRO OMNI", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-t30-pro-omni-white"),
    1956: ("DEEBOT T30 OMNI", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-t30-omni-black"),
    1957: ("DEEBOT X5 PRO OMNI", "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-x5-pro-omni"),
    1958: ("DEEBOT X2 OMNI", "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-x2-omni"),
    1959: ("DEEBOT N30 PRO OMNI", "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-n30pro-omni-white"),
    1960: ("DEEBOT T20 OMNI", "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-t20-omni"),
    1961: ("WINBOT W2 PRO OMNI", "https://www.ecovacs.com/us/shop/winbot-window-cleaning-robot/winbot-w2-pro-omni"),
    1962: ("WINBOT W1 PRO", "https://www.ecovacs.com/us/shop/winbot-window-cleaning-robot/winbot-w1-pro"),
    1963: ("GOAT G1", "https://www.ecovacs.com/au/shop/goat-robotic-lawn-mower/goat-g1"),
    2473: ("DEEBOT mini 2", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-mini-2-white"),
    2474: ("DEEBOT N20 PLUS", "https://www.ecovacs.com/us/shop/deebot-robotic-vacuum-cleaner/deebot-n20-plus"),
    2475: ("DEEBOT N30 PLUS", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-n30-plus-white"),
    2476: ("DEEBOT T30C", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-t30cwhite"),
    2477: ("DEEBOT T80 OMNI", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-t80-omni-white"),
    # T90 OMNI: the /us/shop/deebot-t90-omni page is the BLACK colourway, whose
    # assets already belong to robot 4716 "DEEBOT T90 OMNI BLACK" (byte-identical).
    # The un-suffixed record takes the default/white colourway — same convention
    # as 1937 X5 OMNI (white) vs 2517 X5 OMNI BLACK. /de serves the white PDP.
    2478: ("DEEBOT T90 OMNI", "https://www.ecovacs.com/de/shop/deebot-robotic-vacuum-cleaner/deebot-t90-omni-white"),
    # AIRBOT Z1: discontinued — the PDP is gone from every live region, but the
    # official ECOVACS CDN objects it referenced are STILL LIVE (HTTP 200, valid
    # JPEG). We scrape the Wayback snapshot only to recover the ORIGINAL
    # site-static.ecovacs.com URLs, then fetch the images from ECOVACS directly.
    # Live PDP path was /global/airbot-air-purifier-robot/airbot-z1 (note "-robot").
    1965: ("AIRBOT Z1", "https://web.archive.org/web/20250722195557/"
                        "https://www.ecovacs.com/global/airbot-air-purifier-robot/airbot-z1"),
    2517: ("DEEBOT X5 OMNI BLACK", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-x5-omni-black"),
    2518: ("DEEBOT T30C BLACK", "https://www.ecovacs.com/global/deebot-robotic-vacuum-cleaner/deebot-t30c-black"),
}

RENDER_TOKENS = ("单地宝", "地宝基站", "白色材质", "黑色材质", "精修")
DIAGRAM_TOKENS = ("dimension", "size", "spec", "parameter", "drawing", "cad", "schematic",
                  "exploded", "diagram", "structure", "chart", "compare", "comparison",
                  "banner", "kv", "logo", "icon")


def sniff(body: bytes) -> str | None:
    if body[:3] == b"\xff\xd8\xff": return "jpeg"
    if body[:8] == b"\x89PNG\r\n\x1a\n": return "png"
    if body[:6] in (b"GIF87a", b"GIF89a"): return "gif"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP": return "webp"
    if body[4:12] in (b"ftypavif", b"ftypavis"): return "avif"
    return None


def scrape(url: str) -> list[str]:
    r = requests.get(url, headers=H, timeout=40)
    if r.status_code != 200:
        return []
    raw = re.findall(r"https://site-static\.ecovacs\.com/upload[^\"'\s\\)<>]+", r.text)
    out, seen = [], set()
    for u in raw:
        u = u.split("?")[0]
        u = u.replace("\\u002F", "/").replace("\\/", "/")
        if u.lower().endswith((".pdf", ".mp4", ".svg", ".webm")):
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def fetch(url: str) -> dict | None:
    key = hashlib.md5(url.encode()).hexdigest()
    fp = CACHE / key
    if fp.exists():
        body = fp.read_bytes()
    else:
        try:
            r = requests.get(url, headers=H, timeout=45)
        except Exception:
            return {"url": url, "error": "fetch_fail"}
        if r.status_code != 200:
            return {"url": url, "error": f"http_{r.status_code}"}
        body = r.content
        fp.write_bytes(body)
    kind = sniff(body)          # magic bytes ONLY — never Content-Type
    if not kind:
        return {"url": url, "error": "not_an_image"}
    try:
        im = Image.open(io.BytesIO(body))
        w, h = im.size
    except Exception:
        return {"url": url, "error": "undecodable"}
    return {"url": url, "md5": hashlib.md5(body).hexdigest(), "w": w, "h": h,
            "bytes": len(body), "kind": kind}


def classify(rec: dict) -> str:
    u = rec["url"]
    tail = u.rsplit("/", 1)[-1].lower()
    w, h = rec["w"], rec["h"]
    ar = w / h if h else 0
    if any(t in tail for t in DIAGRAM_TOKENS):
        return "reject_diagram_or_banner_name"
    if ar >= 2.2 or ar <= 0.42:
        return "reject_banner_aspect"
    if rec["bytes"] < 10_000:
        return "reject_tiny"
    if "920x920" in tail and tail.startswith("id-"):
        return "hero_listing"          # best hero per lessons
    if any(t in u for t in RENDER_TOKENS):
        return "render"                # real product render
    if re.match(r"^\d{6}_\d+-\d+\.(jpg|png|jpeg)$", tail):
        return "page_section"          # long-form infographic
    return "other"


def main():
    report = {}
    for rid, (label, url) in PDP.items():
        urls = scrape(url)
        print(f"{rid} {label:<26} {len(urls):>3} imgs  {url.replace('https://www.ecovacs.com','')}")
        with ThreadPoolExecutor(max_workers=8) as ex:
            recs = [r for r in ex.map(fetch, urls) if r]
        good = []
        for r in recs:
            if r.get("error"):
                continue
            r["kind_class"] = classify(r)
            good.append(r)
        report[rid] = {"label": label, "pdp": url, "images": good,
                       "errors": [r for r in recs if r.get("error")]}
        time.sleep(0.4)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT}")

    # cross-model duplicate scan on the raw candidate pool
    from collections import defaultdict
    by_hash = defaultdict(set)
    for rid, e in report.items():
        for im in e["images"]:
            by_hash[im["md5"]].add(rid)
    shared = {h: rs for h, rs in by_hash.items() if len(rs) > 1}
    print(f"candidate pool: {sum(len(e['images']) for e in report.values())} imgs, "
          f"{len(by_hash)} distinct, {len(shared)} shared across models")


if __name__ == "__main__":
    main()
