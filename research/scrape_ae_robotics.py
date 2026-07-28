"""One-off AE Robotics automationar.com scrape for company 1375."""
from __future__ import annotations

import json
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests

from api_client import ResearchApiClient
from load_env import load_research_env
from web_extract import extract_youtube_ids, youtube_watch_url

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "staging/reports/ae-robotics"
HERO_DIR = OUT_DIR / "heroes"
DOMAIN = "https://www.automationar.com"
COMPANY_ID = 1375

REJECT_IMG = re.compile(
    r"(logo|icon|banner|avatar|favicon|sprite|qr|wechat|whatsapp|flag|"
    r"payment|cert|certificate|badge|footer|header|nav|social|facebook|"
    r"twitter|linkedin|instagram|loading|placeholder|blank|default)",
    re.I,
)
SPEC_KEYS = re.compile(
    r"\b(payload|reach|weight|dof|degrees?\s*of\s*freedom|arm\s*reach|"
    r"working\s*radius|load\s*capacity|repeatability)\b",
    re.I,
)
IMG_URL_RE = re.compile(
    r"""(?:https?:)?//[^\s"'<>\\)]+?\.(?:jpg|jpeg|png|webp)(?:\?[^\s"'<>\\)]*)?""",
    re.I,
)
TAG_RE = re.compile(r"<[^>]+>")


def normalize_url(raw: str, page_url: str) -> str:
    raw = unescape(raw.strip().strip("\"'"))
    if raw.startswith("//"):
        raw = "https:" + raw
    elif raw.startswith("/"):
        raw = urljoin(DOMAIN, raw)
    elif not raw.startswith("http"):
        raw = urljoin(page_url, raw)
    return raw


def extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.S)
    if m:
        return unescape(re.sub(r"\s+", " ", m.group(1)).strip())
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if m:
        return unescape(TAG_RE.sub(" ", m.group(1)).strip())
    return None


def score_image(url: str) -> int:
    u = url.lower()
    score = 0
    if "qiniu" in u or "digood" in u:
        score += 50
    if "/upload/" in u or "/image_" in u:
        score += 20
    if REJECT_IMG.search(u):
        score -= 100
    w = re.search(r"[?&/]w[/=](\d+)", u)
    h = re.search(r"h[/=](\d+)", u)
    if w:
        score += min(int(w.group(1)) // 10, 80)
    if h:
        score += min(int(h.group(1)) // 10, 40)
    if "imageview2" in u and "w/170" in u:
        score -= 30
    if u.endswith((".jpg", ".jpeg")):
        score += 5
    return score


def extract_images(html: str, page_url: str) -> list[str]:
    candidates: set[str] = set()
    for attr in ("src", "data-src", "data-original", "data-lazy", "data-url"):
        for m in re.finditer(rf'{attr}\s*=\s*["\']([^"\']+)["\']', html, re.I):
            candidates.add(normalize_url(m.group(1), page_url))
    for m in IMG_URL_RE.finditer(html):
        candidates.add(normalize_url(m.group(0), page_url))

    filtered = []
    for u in candidates:
        pu = urlparse(u)
        if pu.scheme not in ("http", "https"):
            continue
        if not re.search(r"\.(jpg|jpeg|png|webp)(?:\?|$)", u, re.I):
            continue
        if REJECT_IMG.search(u):
            continue
        if "qiniu" not in u.lower() and "digood" not in u.lower() and "/upload/" not in u.lower():
            if not re.search(r"automationar\.com", u, re.I):
                continue
        filtered.append(u)

    ranked = sorted(set(filtered), key=lambda x: (-score_image(x), x))
    return ranked[:20]


def extract_spec_bullets(html: str) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.I | re.S):
        text = unescape(TAG_RE.sub(" ", m.group(1)))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 8 or len(text) > 300:
            continue
        if not SPEC_KEYS.search(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        bullets.append(text)
    if not bullets:
        for m in re.finditer(r"<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S):
            k = unescape(TAG_RE.sub(" ", m.group(1))).strip()
            v = unescape(TAG_RE.sub(" ", m.group(2))).strip()
            line = f"{k}: {v}" if k and v else ""
            if line and SPEC_KEYS.search(line) and line.lower() not in seen:
                seen.add(line.lower())
                bullets.append(line)
    return bullets[:30]


def extract_youtube(html: str) -> list[str]:
    ids = extract_youtube_ids(html)
    urls = [youtube_watch_url(v) for v in ids]
    for m in re.finditer(r'src=["\']([^"\']*youtube[^"\']*)["\']', html, re.I):
        u = normalize_url(m.group(1), DOMAIN)
        if u not in urls:
            urls.append(u)
    return list(dict.fromkeys(urls))


def classify_robot(name: str, url: str, title: str | None) -> str:
    blob = f"{name} {url} {title or ''}".lower()
    if "youibot" in blob or "corgi" in blob and "youibot" in url.lower():
        return "youibot"
    if "fanuc" in blob:
        return "fanuc"
    if "aubo" in blob:
        return "aubo"
    if "jaka" in blob:
        return "jaka"
    if "universal robot" in blob or "universal-robot" in blob or re.search(r"\bur[0-9]+\b", blob):
        return "ur"
    if re.search(r"\bae[\s-]?(air|delta|ae20|ae-25|ae25|scara)\b", blob) or "/ae-" in blob or "ae--robot" in blob:
        return "ae_own"
    if "delta robot ar-" in name.lower() or re.search(r"\bar-\d+d\b", blob):
        return "ae_own"
    if name.strip().upper().startswith("AE ") and "aubo" not in blob and "jaka" not in blob and "fanuc" not in blob:
        if "scara" in blob and "aubo" in url.lower():
            return "aubo"
        if "alibaba" not in url and "made-in-china" not in url:
            return "ae_own"
    if "trans " in name.lower() and "automationar" in url:
        return "other"
    return "other"


def fetch_url(session: requests.Session, url: str) -> tuple[int | None, str | None, str | None]:
    try:
        r = session.get(url, timeout=90, allow_redirects=True)
        return r.status_code, r.text if r.status_code == 200 else None, r.url
    except requests.RequestException as e:
        return None, None, str(e)


def strip_query_for_hero(url: str) -> str:
    """Prefer full-size qiniu image without tiny resize params."""
    u = url.replace("&amp;", "&")
    if "imageView2" in u:
        base = u.split("?", 1)[0]
        return base
    return u


def download_hero(session: requests.Session, url: str, dest: Path) -> bool:
    try:
        u = strip_query_for_hero(url)
        r = session.get(u, timeout=90)
        if r.status_code != 200 or len(r.content) < 5000:
            return False
        dest.write_bytes(r.content)
        return True
    except requests.RequestException:
        return False


def is_highly_gapped(robot: dict) -> bool:
    img = (robot.get("image_url") or robot.get("image") or "").lower()
    if not img or "placeholder" in img:
        return True
    if "w/170/h/150" in img or "w/170" in img:
        return True
    photos = robot.get("photos") or []
    if not photos:
        return True
    feats = (robot.get("features") or "").strip()
    if len(feats) < 40:
        return True
    return False


def main() -> None:
    load_research_env()
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID, page_size=100)
    robots.sort(key=lambda r: r.get("id", 0))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HERO_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "RobotAIGeek-ResearchAgent/1.0"})

    html_cache: dict[str, tuple[int | None, str | None, str | None]] = {}

    crm_list = [
        {
            "id": r["id"],
            "name": r.get("name"),
            "url": r.get("url"),
            "status": r.get("status"),
        }
        for r in robots
    ]

    per_robot = []
    pages_200 = 0
    usable_hero_count = 0
    ae_own_ids: list[int] = []

    for robot in robots:
        rid = robot["id"]
        name = robot.get("name") or ""
        url = (robot.get("url") or "").strip()
        entry = {
            "id": rid,
            "name": name,
            "url": url,
            "status": robot.get("status"),
            "crm_image": robot.get("image_url") or robot.get("image"),
            "highly_gapped": is_highly_gapped(robot),
            "fetch": None,
            "title": None,
            "image_urls": [],
            "spec_bullets": [],
            "youtube_urls": [],
            "brand_class": None,
            "usable_hero": False,
            "heroes_downloaded": [],
        }

        if "automationar.com" not in url.lower():
            entry["brand_class"] = classify_robot(name, url, None)
            entry["fetch"] = {"skipped": True, "reason": "not automationar.com"}
            if entry["brand_class"] == "ae_own":
                ae_own_ids.append(rid)
            per_robot.append(entry)
            continue

        fetch_key = url.split("#", 1)[0]
        if fetch_key not in html_cache:
            html_cache[fetch_key] = fetch_url(session, fetch_key)
            time.sleep(0.3)

        status, html, final_url = html_cache[fetch_key]
        entry["fetch"] = {"http_status": status, "final_url": final_url}

        if status == 200 and html:
            pages_200 += 1
            title = extract_title(html)
            entry["title"] = title
            imgs = extract_images(html, final_url or fetch_key)
            entry["image_urls"] = imgs
            entry["spec_bullets"] = extract_spec_bullets(html)
            entry["youtube_urls"] = extract_youtube(html)
            entry["brand_class"] = classify_robot(name, url, title)
            if imgs and score_image(imgs[0]) > 0:
                entry["usable_hero"] = True
                usable_hero_count += 1
        else:
            entry["brand_class"] = classify_robot(name, url, None)

        if entry["brand_class"] == "ae_own":
            ae_own_ids.append(rid)

        per_robot.append(entry)

    # unique 200 pages count (user asked pages 200)
    unique_200 = sum(1 for s, h, _ in html_cache.values() if s == 200)

    download_targets = [
        e for e in per_robot
        if e.get("brand_class") == "ae_own" or (e.get("highly_gapped") and "automationar.com" in (e.get("url") or ""))
    ]

    for entry in download_targets:
        imgs = entry.get("image_urls") or []
        if not imgs:
            continue
        rid = entry["id"]
        n = 0
        for idx, img_url in enumerate(imgs[:6]):
            if n >= 2:
                break
            if score_image(img_url) <= 0:
                continue
            ext = ".jpg"
            if re.search(r"\.png", img_url, re.I):
                ext = ".png"
            dest = HERO_DIR / f"{rid}-{n + 1}{ext}"
            if download_hero(session, img_url, dest):
                entry["heroes_downloaded"].append(str(dest.relative_to(BASE)).replace("\\", "/"))
                n += 1
            time.sleep(0.2)

    report = {
        "company_id": COMPANY_ID,
        "storefront": DOMAIN,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "robots_total": len(robots),
            "automationar_robots": sum(1 for e in per_robot if "automationar.com" in (e.get("url") or "")),
            "unique_pages_fetched": len(html_cache),
            "pages_http_200": unique_200,
            "robot_rows_with_usable_hero": usable_hero_count,
            "ae_own_robot_ids": sorted(set(ae_own_ids)),
            "ae_own_count": len(set(ae_own_ids)),
        },
        "crm_robots": crm_list,
        "robots": per_robot,
    }

    report_path = OUT_DIR / "scrape-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Wrote", report_path)
    print("SUMMARY", json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
