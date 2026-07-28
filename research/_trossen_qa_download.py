"""Download Trossen product-page Wix media into docs/_trossen_qa for visual QA."""
from __future__ import annotations

import json
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import unquote

import requests

BASE = Path(__file__).resolve().parent
QA_DIR = BASE / "docs" / "_trossen_qa"
STAGING_ROBOTS = BASE / "staging" / "robots" / "trossen-robotics"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

ROBOTS = [
    {"id": 5266, "url": "https://www.trossenrobotics.com/aloha-solo", "crm": "aloha-solo.json"},
    {"id": 5267, "url": "https://www.trossenrobotics.com/aloha-stationary", "crm": "aloha-stationary-v20.json"},
    {"id": 5268, "url": "https://www.trossenrobotics.com/mobile-ai", "crm": "mobile-ai.json"},
    {"id": 5269, "url": "https://www.trossenrobotics.com/pincherx100", "crm": "pincherx-100.json"},
    {"id": 5270, "url": "https://www.trossenrobotics.com/viperx-300", "crm": "viperx-300-s.json"},
    {"id": 5271, "url": "https://www.trossenrobotics.com/viperx-aloha", "crm": "viperx-aloha-follower-arm-v20.json"},
    {"id": 5272, "url": "https://www.trossenrobotics.com/widowx-250", "crm": "widowx-250-s.json"},
    {"id": 5273, "url": "https://www.trossenrobotics.com/widowx-ai", "crm": "widowx-ai.json"},
    {"id": 5274, "url": "https://www.trossenrobotics.com/widowx-aloha-set", "crm": "widowx-aloha-set.json"},
]

# Site-wide OG + known tutorial / wrong-product thumbs from prior scrapes
BAD_MEDIA_IDS = {
    "d3716d_cf083398c1ab467495620daf4a9db20b",  # site OG
    "cf083398c1ab467495620daf4a9db20b",
    "d3716d_556cd1db69194a28affde3e7eef2097c",  # Aloha Stationary Hardware Assembly Guide Thumbnail
}

# Filename tokens that indicate skip-worthy assets when present in URL path after media id
BAD_NAME_RE = re.compile(
    r"(?i)(totl|workstation|assembly\s*guide|thumbnail|tutorial|hugging.?face|"
    r"lerobot|mujoco|colab|og.?image|favicon|logo)"
)

WIX_RE = re.compile(r"https://static\.wixstatic\.com/media/[^\s\"'<>\\]+", re.I)
MEDIA_ID_RE = re.compile(r"/media/([^/~%?]+)", re.I)

CRM_QA_IDS = {5266, 5268, 5269, 5270, 5272, 5273, 5274}

CDN = {
    5267: (
        "https://cdn.robotaigeek.com/robots/original/robot-5267-aloha-stationary-v20-v1783946966.jpg",
        "cdn-5267.jpg",
    ),
    5271: (
        "https://cdn.robotaigeek.com/robots/original/robot-5271-viperx-aloha-follower-arm-v20-v1783946967.png",
        "cdn-5271.png",
    ),
}

DOCS_PAGES = [
    "https://docs.trossenrobotics.com/",
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/",
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/specifications/wx250.html",
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/specifications/vx300.html",
    "https://docs.trossenrobotics.com/interbotix_xsarms_docs/specifications/px100.html",
    "https://docs.interbotix.com/",
]


def media_id_from_url(url: str) -> str | None:
    url = unescape(unquote(url.replace("\\u002F", "/").replace("\\/", "/")))
    m = MEDIA_ID_RE.search(url)
    if not m:
        return None
    mid = m.group(1)
    # strip accidental extensions glued without ~
    mid = mid.split("~")[0]
    mid = re.sub(r"\.(jpe?g|png|webp|gif)$", "", mid, flags=re.I)
    return mid


def ext_from_url(url: str) -> str:
    u = unquote(url).lower()
    if ".png" in u:
        return ".png"
    if ".webp" in u:
        return ".webp"
    if ".gif" in u:
        return ".gif"
    return ".jpg"


def normalize_wix(url: str) -> str | None:
    url = unescape(unquote(url.replace("&amp;", "&").replace("\\u002F", "/").replace("\\/", "/")))
    mid = media_id_from_url(url)
    if not mid:
        return None
    # keep filename hint after last /
    name_hint = ""
    tail = url.split("/")[-1]
    if tail and not tail.startswith(mid) and "." in tail:
        name_hint = "/" + tail.split("?")[0]
    ext = ext_from_url(url)
    # prefer original ~mv2 path segment from URL if present
    if "~mv2.png" in url.lower():
        ext = ".png"
    elif "~mv2.jpg" in url.lower() or "~mv2.jpeg" in url.lower():
        ext = ".jpg"
    base = f"https://static.wixstatic.com/media/{mid}~mv2{ext}"
    # fill large; also try scale_auto style as alternate in try list
    return f"{base}/v1/fill/w_1400,h_1050,al_c,q_90,enc_auto/{mid}~mv2{ext}{name_hint}"


def is_bad(mid: str, url: str) -> bool:
    if mid in BAD_MEDIA_IDS:
        return True
    compact = mid.replace("d3716d_", "")
    if compact in BAD_MEDIA_IDS or f"d3716d_{compact}" in BAD_MEDIA_IDS:
        return True
    if BAD_NAME_RE.search(unquote(url)):
        return True
    return False


def extract_wix_urls(html: str) -> list[str]:
    found: list[str] = []
    for m in WIX_RE.finditer(html):
        u = m.group(0).rstrip(").,;'\"\\")
        found.append(u)
    # also escaped JSON forms
    for m in re.finditer(r"static\.wixstatic\.com/media/[^\s\"'<>\\]+", html):
        u = "https://" + m.group(0).replace("\\u002F", "/").replace("\\/", "/")
        found.append(u)
    return found


def download(session: requests.Session, url: str, dest: Path, min_bytes: int = 30_000) -> dict:
    try:
        r = session.get(url, timeout=60, allow_redirects=True)
        status = r.status_code
        data = r.content if status == 200 else b""
    except requests.RequestException as e:
        return {"ok": False, "status": str(e), "bytes": 0, "path": None, "url": url}
    if status != 200:
        return {"ok": False, "status": status, "bytes": 0, "path": None, "url": url}
    if len(data) < min_bytes:
        return {"ok": False, "status": f"too_small_{len(data)}", "bytes": len(data), "path": None, "url": url}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"ok": True, "status": 200, "bytes": len(data), "path": str(dest.relative_to(BASE)).replace("\\", "/"), "url": url}


def crm_quality_auto_urls(crm_name: str) -> list[str]:
    path = STAGING_ROBOTS / crm_name
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    urls: list[str] = []
    for key in ("image", "images", "gallery", "hero", "photo"):
        val = data.get(key)
        if isinstance(val, str):
            urls.append(val)
        elif isinstance(val, list):
            urls.extend(u for u in val if isinstance(u, str))
    # normalize quality_auto to larger fill
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if "quality_auto" not in u and "wixstatic" not in u:
            continue
        mid = media_id_from_url(u)
        if not mid or is_bad(mid, u):
            continue
        # try constructed large quality_auto path from original
        nu = normalize_wix(u)
        # also keep original with scale bumps
        candidates = []
        if nu:
            candidates.append(nu)
        # quality_auto style large
        ext = ext_from_url(u)
        fname = unquote(u.split("/")[-1].split("?")[0])
        qa = (
            f"https://static.wixstatic.com/media/{mid}~mv2{ext}/v1/fill/"
            f"w_1400,h_1050,al_c,q_90,usm_0.66_1.00_0.01,enc_avif,quality_auto/{fname}"
        )
        candidates.append(qa)
        # raw original without transforms
        candidates.append(f"https://static.wixstatic.com/media/{mid}~mv2{ext}")
        for c in candidates:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


def try_urls(session: requests.Session, urls: list[str], dest: Path, min_bytes: int = 30_000) -> dict:
    last = {"ok": False, "status": "no_urls", "bytes": 0, "path": None, "url": None}
    for u in urls:
        last = download(session, u, dest, min_bytes=min_bytes)
        if last["ok"]:
            return last
        # also try scale_auto variant for fill fails
        if u and "/v1/fill/" in u:
            alt = re.sub(r"/v1/fill/[^/]+/", "/v1/fit/w_1400,h_1050,al_c,q_90,enc_auto/", u)
            last = download(session, alt, dest, min_bytes=min_bytes)
            if last["ok"]:
                return last
    return last


def probe_docs(session: requests.Session) -> dict:
    report = {"pages": [], "image_sample": []}
    img_re = re.compile(
        r"(https?://[^\s\"'<>]+\.(?:png|jpe?g|webp|gif)|/_images/[^\s\"'<>]+|/images/[^\s\"'<>]+)",
        re.I,
    )
    product_hint = re.compile(r"(?i)(widowx|viperx|pincherx|wx250|vx300|px100|xsarm)")
    for page in DOCS_PAGES:
        try:
            r = session.get(page, timeout=45)
            status = r.status_code
            html = r.text if status == 200 else ""
        except requests.RequestException as e:
            report["pages"].append({"url": page, "status": str(e), "imgs": 0, "product_like": 0})
            continue
        imgs = []
        for m in img_re.finditer(html):
            u = m.group(1)
            if u.startswith("/"):
                # relative
                from urllib.parse import urljoin

                u = urljoin(page, u)
            imgs.append(u)
        # sphinx often uses _images/
        product_like = [u for u in imgs if product_hint.search(u)]
        report["pages"].append(
            {
                "url": page,
                "status": status,
                "imgs": len(imgs),
                "product_like": len(product_like),
                "sample": product_like[:8] or imgs[:5],
            }
        )
        report["image_sample"].extend(product_like[:5])
        time.sleep(0.4)
    usable = any(p.get("product_like", 0) > 0 for p in report["pages"])
    report["usable_product_photos"] = usable
    return report


def main() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,image/*,*/*"})

    mapping: dict[int, list[dict]] = {}
    crm_status: list[dict] = []

    for robot in ROBOTS:
        rid = robot["id"]
        page_dir = QA_DIR / f"page-{rid}"
        page_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[dict] = []

        print(f"\n=== FETCH {rid} {robot['url']}")
        try:
            resp = session.get(robot["url"], timeout=60)
            html = resp.text if resp.status_code == 200 else ""
            print(f"  HTTP {resp.status_code} len={len(html)}")
        except requests.RequestException as e:
            print(f"  FETCH FAIL {e}")
            html = ""

        raw_urls = extract_wix_urls(html)
        by_mid: dict[str, str] = {}
        skipped_bad = 0
        for u in raw_urls:
            mid = media_id_from_url(u)
            if not mid:
                continue
            if is_bad(mid, u):
                skipped_bad += 1
                continue
            nu = normalize_wix(u)
            if not nu:
                continue
            # first occurrence wins (usually largest / earliest in page)
            if mid not in by_mid:
                by_mid[mid] = nu

        print(f"  unique media={len(by_mid)} skipped_bad={skipped_bad} raw={len(raw_urls)}")

        count = 0
        for mid, url in by_mid.items():
            if count >= 8:
                break
            ext = ext_from_url(url)
            dest = page_dir / f"{mid[:12]}{ext}"
            # avoid clobbering same short prefix from different full ids: use 12 of hex after _
            short = mid.split("_")[-1][:12] if "_" in mid else mid[:12]
            dest = page_dir / f"{short}{ext}"
            result = try_urls(session, [url, f"https://static.wixstatic.com/media/{mid}~mv2{ext}"], dest)
            if result["ok"]:
                downloaded.append(
                    {
                        "media_id": mid,
                        "path": result["path"],
                        "bytes": result["bytes"],
                        "source": "page",
                        "url": result["url"],
                    }
                )
                count += 1
                print(f"  OK {short} {result['bytes']}B")
            else:
                print(f"  FAIL {short} {result['status']}")
            time.sleep(0.25)

        mapping[rid] = downloaded
        time.sleep(0.5)

    # CRM quality_auto constructions
    print("\n=== CRM quality_auto tries")
    for robot in ROBOTS:
        rid = robot["id"]
        if rid not in CRM_QA_IDS:
            continue
        urls = crm_quality_auto_urls(robot["crm"])
        page_dir = QA_DIR / f"page-{rid}"
        page_dir.mkdir(parents=True, exist_ok=True)
        existing_mids = {d["media_id"] for d in mapping.get(rid, [])}
        tried = 0
        for u in urls:
            mid = media_id_from_url(u)
            if not mid or mid in existing_mids:
                continue
            if is_bad(mid, u):
                crm_status.append({"robot_id": rid, "media_id": mid, "status": "skipped_bad", "url": u})
                continue
            # only a few CRM attempts
            if tried >= 3:
                break
            short = mid.split("_")[-1][:12]
            ext = ext_from_url(u)
            dest = page_dir / f"crm-{short}{ext}"
            # try this constructed URL only (report 404s)
            result = download(session, u, dest, min_bytes=30_000)
            crm_status.append(
                {
                    "robot_id": rid,
                    "media_id": mid,
                    "status": result["status"],
                    "bytes": result["bytes"],
                    "path": result["path"],
                    "url": u[:180],
                }
            )
            print(f"  CRM {rid} {short} -> {result['status']} bytes={result['bytes']}")
            if result["ok"]:
                mapping.setdefault(rid, []).append(
                    {
                        "media_id": mid,
                        "path": result["path"],
                        "bytes": result["bytes"],
                        "source": "crm_quality_auto",
                        "url": result["url"],
                    }
                )
                existing_mids.add(mid)
            tried += 1
            time.sleep(0.2)

    # CDN heroes
    print("\n=== CDN heroes")
    for rid, (url, fname) in CDN.items():
        dest = QA_DIR / fname
        result = download(session, url, dest, min_bytes=1000)
        print(f"  CDN {rid} -> {result['status']} bytes={result['bytes']} path={result['path']}")
        if result["ok"]:
            mapping.setdefault(rid, []).append(
                {
                    "media_id": f"cdn-{rid}",
                    "path": result["path"],
                    "bytes": result["bytes"],
                    "source": "cdn",
                    "url": url,
                }
            )

    print("\n=== Interbotix/docs probe")
    docs = probe_docs(session)
    for p in docs["pages"]:
        print(f"  {p['status']} imgs={p['imgs']} product_like={p['product_like']} {p['url']}")
        for s in p.get("sample") or []:
            print(f"      {s[:140]}")
    print(f"  usable_product_photos={docs['usable_product_photos']}")

    print("\n=== MAPPING")
    for rid in sorted(mapping):
        print(f"\nrobot_id={rid}")
        for d in mapping[rid]:
            print(f"  {d['path']}  bytes={d['bytes']}  media_id={d['media_id']}  source={d['source']}")

    out = {
        "mapping": {str(k): v for k, v in mapping.items()},
        "crm_quality_auto_status": crm_status,
        "docs_probe": docs,
    }
    report_path = QA_DIR / "qa-download-report.json"
    report_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {report_path}")


if __name__ == "__main__":
    main()
