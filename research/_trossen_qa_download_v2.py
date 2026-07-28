"""Re-download: prefer page-unique Wix media; skip shared chrome; retry CDN."""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urljoin

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

BAD_MEDIA_IDS = {
    "d3716d_cf083398c1ab467495620daf4a9db20b",
    "cf083398c1ab467495620daf4a9db20b",
    "d3716d_556cd1db69194a28affde3e7eef2097c",  # assembly guide thumb
}

# verified shared chrome / cross-nav product cards appearing on nearly every page
SHARED_CHROME_IDS = {
    "d3716d_634838f511dd4a3ca990e9ba55b96ea6",
    "d3716d_2c07131bad0743e9af33e28eb4f26754",
    "4fdcde_3cf2203dc6da49b081a4c49ed741c9ef",
    "d3716d_98dbed0fff574614ac350585e740994a",
    "d3716d_7c5a120850e44a25a3c3f7cbfacf91ed",
    "d3716d_a8da5eaeb6d1425da9f7fc1e8059513e",
    "d3716d_6d34e08f2615421aa3a54ba7e5c49137",
    "d3716d_41adb66fb8294ec38ac4032ed3371365",
    "11062b",  # prefix for nav pack
}

BAD_NAME_RE = re.compile(
    r"(?i)(totl|workstation|assembly.?guide|thumbnail|tutorial|hugging.?face|"
    r"lerobot|mujoco|colab|favicon|logo|instagram|facebook|youtube|twitter)"
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

# known good page heroes from prior curation (prefer these)
PREFERRED = {
    5266: ["d3716d_1546c3eb4aef4d94b1b338d31153e43d", "d3716d_7c5a120850e44a25a3c3f7cbfacf91ed"],
    5267: ["d3716d_6aa60d59cdd84e25943efabb8b0635aa", "d3716d_af935404f33e46c2861450b084477412", "d3716d_98dbed0fff574614ac350585e740994a"],
    5268: ["d3716d_090991aa9dbb47ebba899ac3531621e0", "d3716d_2007487f6a6f4898a6c53943bbd0a0a9", "d3716d_70ee60d93d8d4ac1969f4e9501db2a05", "d3716d_2c07131bad0743e9af33e28eb4f26754"],
    5269: ["d3716d_7f663428876546fc8b32d34928326fdb", "d3716d_142992415ec54ca8ba8bed02a1e1294e"],
    5270: ["d3716d_986635a82b5f4c038332f2f149d60b19", "d3716d_0eafddcd70e94c98ac67a8317615e27d"],
    5271: ["d3716d_2521e70fc40a460cbde6831166a349b2", "d3716d_de84cd09674243fc89880a41d41455b9", "d3716d_0d200047687d42bdb136e44be9f3ce5a"],
    5272: ["d3716d_031418cc38d043228f47778e2c03cf0c", "d3716d_92240307898643d6bda98199fef615b6"],
    5273: ["d3716d_414a7814471d463680e0c49edcd3ab2f", "d3716d_af13820ea2634bc7bc24a229c5304ddd", "d3716d_e65b0915d70141f29293224a47aa7a58"],
    5274: ["d3716d_7d9108b35b194e3c806cc260fcfd7268", "d3716d_3b7f6549e87543c3afaf8ba31c036ba3", "d3716d_c4d104593cc94491aa4b2f2b7e476819"],
}


def media_id_from_url(url: str) -> str | None:
    url = unescape(unquote(url.replace("\\u002F", "/").replace("\\/", "/")))
    m = MEDIA_ID_RE.search(url)
    if not m:
        return None
    mid = m.group(1).split("~")[0]
    mid = re.sub(r"\.(jpe?g|png|webp|gif)$", "", mid, flags=re.I)
    return mid


def ext_from_url(url: str) -> str:
    u = unquote(url).lower()
    if ".png" in u:
        return ".png"
    if ".webp" in u:
        return ".webp"
    return ".jpg"


def normalize_wix(url: str) -> str | None:
    url = unescape(unquote(url.replace("&amp;", "&").replace("\\u002F", "/").replace("\\/", "/")))
    mid = media_id_from_url(url)
    if not mid:
        return None
    ext = ext_from_url(url)
    if "~mv2.png" in url.lower():
        ext = ".png"
    elif "~mv2.jpg" in url.lower():
        ext = ".jpg"
    base = f"https://static.wixstatic.com/media/{mid}~mv2{ext}"
    return f"{base}/v1/fill/w_1400,h_1050,al_c,q_90,enc_auto/{mid}~mv2{ext}"


def is_bad(mid: str, url: str) -> bool:
    if mid in BAD_MEDIA_IDS or mid.replace("d3716d_", "") in BAD_MEDIA_IDS:
        return True
    if any(mid.startswith(p) or p in mid for p in SHARED_CHROME_IDS if len(p) < 20):
        if mid.startswith("11062b"):
            return True
    if BAD_NAME_RE.search(unquote(url)):
        return True
    return False


def extract_wix_urls(html: str) -> list[str]:
    found = []
    for m in WIX_RE.finditer(html):
        found.append(m.group(0).rstrip(").,;'\"\\"))
    for m in re.finditer(r"static\.wixstatic\.com/media/[^\s\"'<>\\]+", html):
        found.append("https://" + m.group(0).replace("\\u002F", "/").replace("\\/", "/"))
    return found


def download(session: requests.Session, url: str, dest: Path, min_bytes: int = 30_000, headers=None) -> dict:
    try:
        r = session.get(url, timeout=60, allow_redirects=True, headers=headers or {})
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


def crm_urls(crm_name: str) -> list[tuple[str, str]]:
    path = STAGING_ROBOTS / crm_name
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    urls = []
    for key in ("image", "images", "gallery"):
        val = data.get(key)
        if isinstance(val, str):
            urls.append(val)
        elif isinstance(val, list):
            urls.extend(u for u in val if isinstance(u, str))
    out = []
    seen = set()
    for u in urls:
        if "wixstatic" not in u:
            continue
        mid = media_id_from_url(u)
        if not mid or is_bad(mid, u):
            continue
        ext = ext_from_url(u)
        fname = unquote(u.split("/")[-1].split("?")[0])
        candidates = [
            normalize_wix(u),
            f"https://static.wixstatic.com/media/{mid}~mv2{ext}/v1/fill/w_1400,h_1050,al_c,q_90,usm_0.66_1.00_0.01,enc_avif,quality_auto/{fname}",
            f"https://static.wixstatic.com/media/{mid}~mv2{ext}",
        ]
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                out.append((mid, c))
    return out


def main() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "*/*"})

    # Pass 1: collect per-page media to find shared vs unique
    page_mids: dict[int, dict[str, str]] = {}
    for robot in ROBOTS:
        rid = robot["id"]
        print(f"FETCH {rid}")
        resp = session.get(robot["url"], timeout=60)
        html = resp.text if resp.status_code == 200 else ""
        by_mid = {}
        for u in extract_wix_urls(html):
            mid = media_id_from_url(u)
            if not mid or is_bad(mid, u):
                continue
            if mid in SHARED_CHROME_IDS:
                continue
            nu = normalize_wix(u)
            if nu and mid not in by_mid:
                by_mid[mid] = nu
        page_mids[rid] = by_mid
        print(f"  candidates after chrome filter: {len(by_mid)}")
        time.sleep(0.4)

    freq = Counter()
    for mids in page_mids.values():
        for mid in mids:
            freq[mid] += 1
    # treat media on 6+ product pages as shared nav chrome
    global_shared = {m for m, c in freq.items() if c >= 6}
    print(f"global_shared ({len(global_shared)}):", sorted(list(global_shared))[:20])

    mapping: dict[int, list[dict]] = {}
    crm_status = []

    for robot in ROBOTS:
        rid = robot["id"]
        page_dir = QA_DIR / f"page-{rid}"
        # clear previous page-* downloads for clean listing
        if page_dir.exists():
            for f in page_dir.glob("*"):
                if f.is_file():
                    f.unlink()
        page_dir.mkdir(parents=True, exist_ok=True)

        preferred = PREFERRED.get(rid, [])
        unique = []
        sharedish = []
        for mid, url in page_mids[rid].items():
            if mid in global_shared and mid not in preferred:
                sharedish.append((mid, url))
            else:
                unique.append((mid, url))

        # order: preferred first, then unique, then sharedish filler
        ordered = []
        seen = set()
        for mid in preferred:
            if mid in page_mids[rid] and mid not in seen:
                ordered.append((mid, page_mids[rid][mid]))
                seen.add(mid)
            else:
                # synthesize preferred even if not on page HTML
                for ext in (".jpg", ".png"):
                    url = f"https://static.wixstatic.com/media/{mid}~mv2{ext}/v1/fill/w_1400,h_1050,al_c,q_90,enc_auto/{mid}~mv2{ext}"
                    ordered.append((mid, url))
                    seen.add(mid)
                    break
        for mid, url in unique + sharedish:
            if mid not in seen:
                ordered.append((mid, url))
                seen.add(mid)

        downloaded = []
        for mid, url in ordered:
            if len(downloaded) >= 8:
                break
            short = mid.split("_")[-1][:12]
            ext = ext_from_url(url)
            dest = page_dir / f"{short}{ext}"
            # try fill then raw
            result = download(session, url, dest)
            if not result["ok"]:
                raw = f"https://static.wixstatic.com/media/{mid}~mv2{ext}"
                result = download(session, raw, dest)
            if not result["ok"] and ext == ".jpg":
                result = download(session, url.replace(".jpg", ".png").replace("~mv2.jpg", "~mv2.png"), page_dir / f"{short}.png")
                if result["ok"]:
                    dest = page_dir / f"{short}.png"
            if result["ok"]:
                downloaded.append({"media_id": mid, "path": result["path"], "bytes": result["bytes"], "source": "page", "url": result["url"]})
                print(f"  {rid} OK {short} {result['bytes']}")
            else:
                print(f"  {rid} FAIL {short} {result['status']}")
            time.sleep(0.2)
        mapping[rid] = downloaded

    print("\n=== CRM quality_auto status")
    for robot in ROBOTS:
        rid = robot["id"]
        if rid not in CRM_QA_IDS:
            continue
        pairs = crm_urls(robot["crm"])
        # dedupe by mid, try one constructed URL set per mid
        by_mid = {}
        for mid, u in pairs:
            by_mid.setdefault(mid, []).append(u)
        existing = {d["media_id"] for d in mapping.get(rid, [])}
        for mid, urls in list(by_mid.items())[:5]:
            statuses = []
            saved = None
            for u in urls:
                # HEAD-ish GET without save first for status report when already have mid
                try:
                    r = session.get(u, timeout=45, stream=True)
                    st = r.status_code
                    size = int(r.headers.get("Content-Length") or 0)
                    # read content if we may save
                    if st == 200 and mid not in existing and saved is None:
                        data = r.content
                        size = len(data)
                        if size >= 30000:
                            short = mid.split("_")[-1][:12]
                            dest = QA_DIR / f"page-{rid}" / f"crm-{short}{ext_from_url(u)}"
                            dest.write_bytes(data)
                            path = str(dest.relative_to(BASE)).replace("\\", "/")
                            saved = {"media_id": mid, "path": path, "bytes": size, "source": "crm_quality_auto", "url": u}
                            existing.add(mid)
                            mapping.setdefault(rid, []).append(saved)
                    else:
                        r.close()
                    statuses.append(f"{st}:{size}")
                except requests.RequestException as e:
                    statuses.append(str(e)[:40])
                time.sleep(0.15)
            crm_status.append({"robot_id": rid, "media_id": mid, "tries": statuses, "saved": bool(saved)})
            print(f"  CRM {rid} {mid.split('_')[-1][:12]} tries={statuses} saved={bool(saved)}")

    print("\n=== CDN")
    for rid, (url, fname) in CDN.items():
        dest = QA_DIR / fname
        attempts = [
            {},
            {"Referer": "https://www.robotaigeek.com/", "Origin": "https://www.robotaigeek.com"},
            {"Referer": "https://cdn.robotaigeek.com/"},
        ]
        ok = False
        for h in attempts:
            result = download(session, url, dest, min_bytes=1000, headers=h)
            print(f"  CDN {rid} headers={list(h)} -> {result['status']} bytes={result['bytes']}")
            if result["ok"]:
                mapping.setdefault(rid, []).append(
                    {"media_id": f"cdn-{rid}", "path": result["path"], "bytes": result["bytes"], "source": "cdn", "url": url}
                )
                ok = True
                break
        if not ok:
            # copy from existing primary/cand if present
            for alt in [QA_DIR / f"primary-{rid}.jpg", QA_DIR / f"cand0-{rid}.jpg", QA_DIR / f"cand0-{rid}.png", QA_DIR / f"primary-{rid}.jpg"]:
                if alt.exists() and alt.stat().st_size > 1000:
                    dest.write_bytes(alt.read_bytes())
                    mapping.setdefault(rid, []).append(
                        {
                            "media_id": f"cdn-{rid}-local-fallback",
                            "path": str(dest.relative_to(BASE)).replace("\\", "/"),
                            "bytes": dest.stat().st_size,
                            "source": "local_primary_copy_cdn_403",
                            "url": url,
                        }
                    )
                    print(f"  CDN {rid} 403 -> copied local {alt.name} ({dest.stat().st_size}B) NOTE: not live CDN")
                    break

    # Docs product images download for X-series
    print("\n=== Docs product photos")
    docs_dir = QA_DIR / "docs-xsarms"
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_files = []
    for name in ("wx250.png", "vx300.png", "px100.png", "wx250_drawing.png", "vx300_drawing.png", "px100_drawing.png"):
        url = f"https://docs.trossenrobotics.com/_images/{name}"
        dest = docs_dir / name
        result = download(session, url, dest, min_bytes=1000)
        print(f"  {name} -> {result['status']} {result['bytes']}")
        if result["ok"]:
            docs_files.append(result)

    print("\n=== MAPPING")
    for rid in sorted(mapping):
        print(f"\nrobot_id={rid}")
        for d in mapping[rid]:
            print(f"  {d['path']}  bytes={d['bytes']}  media_id={d['media_id']}  source={d['source']}")

    print("\n=== DOCS X-SERIES")
    for d in docs_files:
        print(f"  {d['path']}  bytes={d['bytes']}")

    report = {
        "mapping": {str(k): v for k, v in mapping.items()},
        "crm_quality_auto_status": crm_status,
        "global_shared_skipped": sorted(global_shared),
        "docs_xsarms": docs_files,
        "docs_usable_product_photos": True,
        "docs_notes": "docs.trossenrobotics.com/_images has wx250.png, vx300.png, px100.png product renders + drawings. docs.interbotix.com DNS fails.",
    }
    (QA_DIR / "qa-download-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nWrote qa-download-report.json")


if __name__ == "__main__":
    main()
