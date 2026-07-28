"""AE Robotics (company 1375) hero scrape from automationar.com.

Crawls product URLs, resolves best page per CRM robot, downloads heroes,
searches YouTube, writes staging/reports/ae-heroes/scrape-report.json.
"""
from __future__ import annotations

import json
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, urlunparse

import requests

from api_client import ResearchApiClient
from load_env import load_research_env
from web_extract import (
    WebFetcher,
    discover_sitemap_urls,
    extract_specs_from_text,
    extract_youtube_ids,
    score_url_for_robot,
    youtube_watch_url,
)
from youtube_metadata import enrich_video_list, is_reject_robot_video_title

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "staging/reports/ae-heroes"
HERO_DIR = OUT_DIR
DOMAIN = "https://www.automationar.com"
COMPANY_ID = 1375

HEADERS = {"User-Agent": "RobotAIGeek-ResearchAgent/1.0"}
TAG_RE = re.compile(r"<[^>]+>")

# Site chrome / shared listing images — never product heroes.
CHROME_IMG_RE = re.compile(
    r"(logo|icon|banner|avatar|favicon|sprite|qr|wechat|whatsapp|flag|"
    r"payment|cert|certificate|badge|footer|header|nav|social|facebook|"
    r"twitter|linkedin|instagram|loading|placeholder|blank|default|"
    r"robot-solution|collaborative-robots\.jpg|内页)",
    re.I,
)
SPEC_KEYS = re.compile(
    r"\b(payload|reach|weight|dof|degrees?\s*of\s*freedom|arm\s*reach|"
    r"working\s*radius|load\s*capacity|repeatability|axis|6[\s-]?axis)\b",
    re.I,
)
IMG_URL_RE = re.compile(
    r"""(?:https?:)?//[^\s"'<>\\)]+?\.(?:jpg|jpeg|png|webp)(?:\?[^\s"'<>\\)]*)?""",
    re.I,
)

# Manual overrides when catalog scoring is ambiguous.
URL_OVERRIDES: dict[int, str] = {
    1446: f"{DOMAIN}/product/ae--robot-3kg-payload-560mm-arm-reach---china-one-stop-robot-supplier-industrial-robotic-arm.html",
    1447: f"{DOMAIN}/product/ae-air3-a-robot-arm-industrial-6-axis-payload-3kg-and-arm-reach-560mm-robot-mechanical-arm-claw-166.html",
    1448: f"{DOMAIN}/product/ae-air7l-b-arc-welding-robot-manipulator-intelligent-robotic-arm-pick-and-place-robot.html",
    1449: f"{DOMAIN}/product/ae-industrial-robot-air8-a-6-axis-robot-programmig-8kg-payload-cobot-industrial-robotic-arm-from-sh.html",
    1450: f"{DOMAIN}/product/ae-air10-a-automation-manipulator-industrial-middle-6-axis-robot-arm-like-kuka-robot-arm.html",
    1451: f"{DOMAIN}/product/ae-air3-a-industry-robot-arm-6-axis-payload-3kg-and-arm-reach-560mm-robot-mechanical-arm-claw.html",
    1452: f"{DOMAIN}/product/ae-25-series-6-axis-industrial-robot-arm-palletizer-robot.html",
    1453: f"{DOMAIN}/product/ae20-cobot-6-axis-collaborative-robot-arm.html",
    1454: f"{DOMAIN}/product/china-hotsale-4-axis-scara-robot-5kg-payload-600mm-arm-reach.html",
    1455: f"{DOMAIN}/product/3-4axis-delta-robot-1kg-payload-600mm-working-diameter-for-packing-application.html",
    3534: f"{DOMAIN}/product/ae-air3-a-industry-robot-arm-6-axis-payload-3kg-and-arm-reach-560mm-robot-mechanical-arm-claw.html",
    4831: f"{DOMAIN}/product/ae--robot-3kg-payload-560mm-arm-reach---china-one-stop-robot-supplier-industrial-robotic-arm.html",
    4832: f"{DOMAIN}/product/ae-air7l-b-arc-welding-robot-manipulator-intelligent-robotic-arm-pick-and-place-robot.html",
    4833: f"{DOMAIN}/product/ae-industrial-robot-programmig-air8-a-6-axis-robot-8kg-payload-cobot-industrial-robotic-arm-from-shenzhen.html",
    4834: f"{DOMAIN}/product/ae-air10-a-automation-manipulator-industrial-middle-robot-arm-like-kuka-6-axis-robot-arm.html",
}

NAV_FEATURE_RE = re.compile(
    r"(?i)^(robot solution|cobot |robot flexible|robot arm fanuc|welding robot|welding positioner|"
    r"electric gripper|delta robot|scara|agv|mobile industrial|kuka|yasakawa|estun|efort|adtech|"
    r"collaborative scara|jaka collaborative|ur collaborative|robot tools|other robots|"
    r"robotic tube|#product-description|\.nav-tabs)",
)

YT_QUERIES: dict[str, list[str]] = {
    "ae": ["AE Robotics AIR3", "AE AIR7L automationar", "automationar robot"],
    "fanuc": ["Fanuc R-2000iC robot demo"],
    "jaka": ["JAKA Zu cobot demo"],
    "aubo": ["AUBO i5 collaborative robot"],
    "ur": ["Universal Robots UR5 demo"],
}


def normalize_url(raw: str, page_url: str = DOMAIN) -> str:
    raw = unescape(raw.strip().strip("\"'"))
    if raw.startswith("//"):
        raw = "https:" + raw
    elif raw.startswith("/"):
        raw = urljoin(DOMAIN, raw)
    elif not raw.startswith("http"):
        raw = urljoin(page_url, raw)
    return raw


def robot_tokens(name: str) -> list[str]:
    n = name.lower()
    tokens: list[str] = []
    for m in re.finditer(r"[a-z0-9]{2,}", n):
        t = m.group(0)
        if t not in ("ae", "robot", "cobot", "industrial", "collaborative", "mobile"):
            tokens.append(t)
    for pat in (
        r"air\d+[a-z]?",
        r"ar-\d+d",
        r"ae-?\d+",
        r"ae20",
        r"r-2000ic",
        r"zu\d+",
        r"ur\d+",
        r"i\d+fb?",
        r"i\d+",
        r"scara",
        r"delta",
    ):
        m = re.search(pat, n, re.I)
        if m:
            tokens.append(m.group(0).lower())
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:12]


def classify_robot(name: str, url: str, title: str | None) -> str:
    blob = f"{name} {url} {title or ''}".lower()
    if "youibot" in blob or "corgi" in blob:
        return "youibot"
    if "fanuc" in blob:
        return "fanuc"
    if "aubo" in blob:
        return "aubo"
    if "jaka" in blob:
        return "jaka"
    if "universal robot" in blob or re.search(r"\bur[0-9]+\b", blob):
        return "ur"
    if re.search(r"\bae[\s-]?(air|delta|ae20|ae-25|ae25|scara)\b", blob):
        return "ae_own"
    if re.search(r"\bar-\d+d\b", blob):
        return "ae_own"
    if name.strip().upper().startswith("AE ") and not any(
        x in blob for x in ("aubo", "jaka", "fanuc", "ur", "universal")
    ):
        return "ae_own"
    if "trans " in name.lower():
        return "other"
    return "other"


def is_weak_url(url: str) -> bool:
    u = (url or "").lower()
    if not u or u in ("#", "..."):
        return True
    if any(x in u for x in ("alibaba", "made-in-china", "robot-arm.en.alibaba")):
        return True
    if "/products/" in u:
        return True
    if u.endswith(".html") and "#" in u:
        return True
    return False


def score_ae_image(url: str, tokens: list[str]) -> int:
    u = url.lower()
    score = 0
    if CHROME_IMG_RE.search(u):
        score -= 120
    if "qiniu" in u or "digood" in u:
        score += 30
    if "/upload/" in u or "/image_" in u:
        score += 15
    for tok in tokens:
        if tok in u:
            score += 25
    if "imageview2" in u:
        if re.search(r"w/(?:170|180|160)", u):
            score -= 15
        if re.search(r"w/410", u):
            score += 20
    if u.endswith((".jpg", ".jpeg")):
        score += 3
    return score


def extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.S)
    if m:
        return unescape(re.sub(r"\s+", " ", m.group(1)).strip())
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if m:
        return unescape(TAG_RE.sub(" ", m.group(1)).strip())
    return None


def extract_images(html: str, page_url: str, tokens: list[str]) -> list[str]:
    candidates: set[str] = set()
    for attr in ("src", "data-src", "data-original", "data-lazy", "data-url"):
        for m in re.finditer(rf'{attr}\s*=\s*["\']([^"\']+)["\']', html, re.I):
            candidates.add(normalize_url(m.group(1), page_url))
    for m in IMG_URL_RE.finditer(html):
        candidates.add(normalize_url(m.group(0), page_url))

    filtered: list[tuple[int, str]] = []
    for u in candidates:
        pu = urlparse(u)
        if pu.scheme not in ("http", "https"):
            continue
        if not re.search(r"\.(jpg|jpeg|png|webp)(?:\?|$)", u, re.I):
            continue
        if CHROME_IMG_RE.search(u):
            continue
        if "qiniu" not in u.lower() and "digood" not in u.lower():
            if "automationar.com" not in u.lower():
                continue
        filtered.append((score_ae_image(u, tokens), u))

    filtered.sort(key=lambda x: (-x[0], x[1]))
    return [u for s, u in filtered if s > 0][:20]


def extract_features(html: str) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.I | re.S):
        text = unescape(TAG_RE.sub(" ", m.group(1)))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 12 or len(text) > 400:
            continue
        if not re.search(r"[a-zA-Z]{4,}", text):
            continue
        if NAV_FEATURE_RE.match(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        bullets.append(text)
    if not bullets:
        for m in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.I | re.S):
            text = unescape(TAG_RE.sub(" ", m.group(1)))
            text = re.sub(r"\s+", " ", text).strip()
            if 20 <= len(text) <= 300 and re.search(r"[a-zA-Z]{4,}", text):
                if NAV_FEATURE_RE.match(text):
                    continue
                key = text.lower()
                if key not in seen:
                    seen.add(key)
                    bullets.append(text)
    return bullets[:15]


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
    return list(dict.fromkeys(youtube_watch_url(v) for v in ids))


def parse_catalog_entries(html: str) -> list[dict]:
    """Parse product cards from listing pages (ae-robot-arm.html style)."""
    entries: list[dict] = []
    seen_urls: set[str] = set()
    for m in re.finditer(
        r'<a\s+href="(/product/[^"]+\.html)"[^>]*title="([^"]*)"[^>]*>\s*<img[^>]+src="([^"]+)"',
        html,
        re.I | re.S,
    ):
        url = normalize_url(m.group(1))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        entries.append(
            {
                "url": url,
                "image": normalize_url(m.group(3)),
                "title": unescape(m.group(2).strip()),
                "description": "",
            }
        )
    # Fallback: looser href/img pairing
    if len(entries) < 5:
        for m in re.finditer(r'href="(/product/[^"]+\.html)"', html, re.I):
            url = normalize_url(m.group(1))
            if url in seen_urls:
                continue
            start = max(0, m.start() - 200)
            chunk = html[start : m.end() + 400]
            img_m = re.search(r'<img[^>]+src="([^"]+)"', chunk, re.I)
            title_m = re.search(r'title="([^"]+)"', chunk, re.I)
            if img_m:
                seen_urls.add(url)
                entries.append(
                    {
                        "url": url,
                        "image": normalize_url(img_m.group(1)),
                        "title": unescape(title_m.group(1).strip()) if title_m else "",
                        "description": "",
                    }
                )
    return entries


def discover_site_urls(session: requests.Session) -> list[str]:
    fetcher = WebFetcher(stealth=False)
    seen: set[str] = set()
    urls: list[str] = []

    def add(u: str) -> None:
        u = normalize_url(u)
        if "automationar.com" not in u.lower():
            return
        base = u.split("#")[0]
        if base not in seen:
            seen.add(base)
            urls.append(base)

    for u in discover_sitemap_urls(fetcher, DOMAIN, limit=200):
        add(u)

    for seed in (
        DOMAIN,
        f"{DOMAIN}/products/ae-robot-arm.html",
        f"{DOMAIN}/products/collaborative-aubo-robot-arm.html",
        f"{DOMAIN}/products/industrial-robot-arm.html",
    ):
        try:
            r = session.get(seed, timeout=60)
            if r.status_code != 200:
                continue
            add(r.url)
            for href in re.findall(r'href=["\']([^"\']+)["\']', r.text):
                if "/product" in href or "/products" in href:
                    add(href)
        except requests.RequestException:
            pass
        time.sleep(0.25)

    return urls


def resolve_product_url(
    robot_id: int,
    name: str,
    crm_url: str,
    catalog: list[dict],
    discovered: list[str],
) -> tuple[str, str]:
    if robot_id in URL_OVERRIDES:
        return URL_OVERRIDES[robot_id], "override"

    tokens = robot_tokens(name)
    if crm_url and not is_weak_url(crm_url):
        base = crm_url.split("#")[0]
        if "automationar.com" in base.lower():
            return base, "crm_url"

    # Score catalog entries by title/description/url tokens
    best_cat = ""
    best_score = 0
    for entry in catalog:
        blob = f"{entry.get('url','')} {entry.get('title','')} {entry.get('description','')}".lower()
        score = sum(10 for t in tokens if t in blob)
        if score > best_score:
            best_score = score
            best_cat = entry["url"]

    if best_cat and best_score >= 10:
        return best_cat, "catalog_match"

    ranked = sorted(
        ((score_url_for_robot(u, tokens), u) for u in discovered),
        key=lambda x: (-x[0], x[1]),
    )
    for score, u in ranked:
        if score >= 10 and "/product/" in u:
            return u, "discovered_url"

    if crm_url and "automationar.com" in crm_url.lower():
        return crm_url.split("#")[0], "crm_weak"

    return crm_url or "", "unresolved"


def youtube_search_ids(query: str, limit: int = 3) -> list[str]:
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException:
        return []
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
    out: list[str] = []
    for vid in ids:
        if vid not in out:
            out.append(vid)
        if len(out) >= limit:
            break
    return [f"https://www.youtube.com/watch?v={v}" for v in out]


def search_youtube_for_robot(name: str, brand: str, session: requests.Session) -> list[dict]:
    tokens = robot_tokens(name)
    queries: list[str] = []
    if brand == "ae_own":
        for q in YT_QUERIES["ae"]:
            queries.append(f"{q} {name}")
        queries.append(f"AE Robotics {name}")
    elif brand == "fanuc":
        queries.append(f"Fanuc {name}")
        queries.extend(YT_QUERIES["fanuc"])
    elif brand == "jaka":
        queries.append(f"JAKA {name}")
        queries.extend(YT_QUERIES["jaka"])
    elif brand == "aubo":
        queries.append(f"AUBO {name}")
        queries.extend(YT_QUERIES["aubo"])
    elif brand == "ur":
        queries.append(f"Universal Robots {name}")
        queries.extend(YT_QUERIES["ur"])
    else:
        queries.append(f"automationar {name}")

    seen: set[str] = set()
    raw_urls: list[str] = []
    for q in queries[:4]:
        for u in youtube_search_ids(q, limit=3):
            if u not in seen:
                seen.add(u)
                raw_urls.append(u)
        time.sleep(0.3)

    enriched = enrich_video_list(raw_urls, session=session, skip_rejected=True)
    reject_title_extra = re.compile(
        r"(?i)\b(atomrobot|rbtx|oriental motor|kinematic work|how does a delta)\b",
    )
    filtered: list[dict] = []
    for v in enriched:
        title = (v.get("title") or "").lower()
        desc = (v.get("description") or "").lower()
        blob = f"{title} {desc}"
        if not title or is_reject_robot_video_title(title):
            continue
        if reject_title_extra.search(blob):
            continue
        if brand in ("fanuc", "jaka", "aubo", "ur", "ae_own"):
            if any(t in blob for t in tokens[:5]):
                filtered.append(v)
            elif brand == "ae_own" and any(
                x in blob for x in ("ae robotics", "automationar", " ae ", "air3", "air7", "air8", "air10", "air20")
            ):
                filtered.append(v)
            elif brand == "fanuc" and "fanuc" in blob:
                filtered.append(v)
            elif brand == "jaka" and "jaka" in blob:
                filtered.append(v)
            elif brand == "aubo" and "aubo" in blob:
                filtered.append(v)
            elif brand == "ur" and ("ur5" in blob or "ur3" in blob or "ur10" in blob or "universal robot" in blob):
                filtered.append(v)
        else:
            if "automationar" in blob or any(t in blob for t in tokens[:3]):
                filtered.append(v)
    return filtered[:3]


def fetch_url(session: requests.Session, url: str) -> tuple[int | None, str | None, str | None]:
    if not url:
        return None, None, "empty url"
    try:
        r = session.get(url, timeout=90, allow_redirects=True)
        return r.status_code, r.text if r.status_code == 200 else None, r.url
    except requests.RequestException as e:
        return None, None, str(e)


def strip_query_for_hero(url: str) -> str:
    u = url.replace("&amp;", "&")
    if "imageView2" in u or "imageview2" in u:
        return u.split("?", 1)[0]
    return u


def safe_image_url(url: str) -> str:
    u = strip_query_for_hero(url)
    if "DETTA" in u:
        return "https://qiniu.digood-assets-fallback.work/5/image_1560584527_DETTA-%E7%94%BB%E5%86%8C%E5%9B%BE%E7%89%87.png"
    parsed = urlparse(u)
    path = quote(parsed.path, safe="/%()")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def download_hero(session: requests.Session, url: str, dest: Path) -> bool:
    candidates: list[str] = []
    if "imageView2" in url or "imageview2" in url:
        candidates.append(url.replace("&amp;", "&"))
    candidates.append(safe_image_url(url))
    candidates.append(strip_query_for_hero(url))
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            r = session.get(candidate, timeout=90)
            if r.status_code == 200 and len(r.content) >= 1500:
                dest.write_bytes(r.content)
                return True
        except requests.RequestException:
            continue
    return False


def recommended_tags(name: str, brand: str, features: list[str], specs: dict) -> list[str]:
    tags: list[str] = []
    n = name.lower()
    if brand == "ae_own":
        tags.append("AE Robotics")
        if "air" in n:
            tags.append("industrial robot arm")
        if "delta" in n or "ar-" in n:
            tags.append("delta robot")
        if "cobot" in n or "ae20" in n:
            tags.append("collaborative robot")
        if "pallet" in n or "ae-25" in n or "ae25" in n:
            tags.append("palletizing robot")
        if "welding" in n or "air7l" in n:
            tags.append("welding robot")
    elif brand == "fanuc":
        tags.extend(["Fanuc", "industrial robot", "reseller"])
    elif brand == "aubo":
        tags.extend(["AUBO", "collaborative robot", "reseller"])
    elif brand == "jaka":
        tags.extend(["JAKA", "cobot", "reseller"])
    elif brand == "ur":
        tags.extend(["Universal Robots", "cobot", "reseller"])
    elif brand == "youibot":
        tags.extend(["Youibot", "mobile robot", "AGV", "reseller"])
    if specs.get("payload_kg"):
        tags.append(f"{specs['payload_kg']}kg payload")
    for f in features[:2]:
        if SPEC_KEYS.search(f):
            tags.append(f[:60])
    return list(dict.fromkeys(tags))[:8]


def main() -> None:
    load_research_env()
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID, page_size=100)
    robots.sort(key=lambda r: r.get("id", 0))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    print("Discovering automationar.com product URLs...")
    discovered = discover_site_urls(session)
    print(f"  discovered {len(discovered)} URLs")

    html_cache: dict[str, tuple[int | None, str | None, str | None]] = {}
    catalog: list[dict] = []

    listing_url = f"{DOMAIN}/products/ae-robot-arm.html"
    status, html, _ = fetch_url(session, listing_url)
    if status == 200 and html:
        html_cache[listing_url] = (status, html, listing_url)
        catalog = parse_catalog_entries(html)
        print(f"  catalog entries from listing: {len(catalog)}")

    per_robot: list[dict] = []
    usable_hero_count = 0
    brand_counts: dict[str, int] = {"ae_own": 0, "reseller": 0, "other": 0, "no_hero": 0}

    for robot in robots:
        rid = robot["id"]
        name = robot.get("name") or ""
        crm_url = (robot.get("url") or "").strip()
        tokens = robot_tokens(name)

        resolved_url, resolve_method = resolve_product_url(
            rid, name, crm_url, catalog, discovered
        )

        entry: dict = {
            "id": rid,
            "name": name,
            "crm_url": crm_url,
            "url": resolved_url,
            "resolve_method": resolve_method,
            "title": None,
            "image": None,
            "image_urls": [],
            "features": [],
            "specs": {},
            "spec_bullets": [],
            "youtube": [],
            "brand_class": None,
            "usable_hero": False,
            "hero_file": None,
            "notes": [],
            "recommended_tags": [],
        }

        if not resolved_url or "automationar.com" not in resolved_url.lower():
            entry["brand_class"] = classify_robot(name, crm_url, None)
            entry["notes"].append("no automationar product page resolved")
            if entry["brand_class"] in ("fanuc", "aubo", "jaka", "ur"):
                brand_counts["reseller"] += 0  # no hero yet
            brand_counts["no_hero"] += 1
            per_robot.append(entry)
            continue

        fetch_key = resolved_url.split("#")[0]
        if fetch_key not in html_cache:
            html_cache[fetch_key] = fetch_url(session, fetch_key)
            time.sleep(0.3)

        status, page_html, final_url = html_cache[fetch_key]
        entry["url"] = final_url or fetch_key

        if status == 200 and page_html:
            title = extract_title(page_html)
            entry["title"] = title
            entry["brand_class"] = classify_robot(name, resolved_url, title)

            imgs = extract_images(page_html, entry["url"], tokens)
            entry["image_urls"] = imgs

            # Prefer catalog thumbnail when page images are generic
            if resolve_method == "catalog_match":
                for cat in catalog:
                    if cat["url"].split("#")[0] == fetch_key and cat.get("image"):
                        cat_img = cat["image"]
                        if score_ae_image(cat_img, tokens) > 0:
                            if cat_img not in imgs:
                                imgs.insert(0, cat_img)
                            entry["image_urls"] = imgs

            features = extract_features(page_html)
            spec_bullets = extract_spec_bullets(page_html)
            entry["features"] = [f for f in features if not SPEC_KEYS.search(f)][:8]
            entry["spec_bullets"] = spec_bullets

            text_blob = " ".join([title or "", *spec_bullets, *features[:5]])
            entry["specs"] = extract_specs_from_text(text_blob)

            page_yt = extract_youtube(page_html)
            if page_yt:
                entry["youtube"] = enrich_video_list(page_yt, session=session)

            if imgs and score_ae_image(imgs[0], tokens) > 5:
                entry["image"] = strip_query_for_hero(imgs[0])
                entry["usable_hero"] = True
                usable_hero_count += 1

                ext = ".png" if re.search(r"\.png", entry["image"], re.I) else ".jpg"
                dest = HERO_DIR / f"{rid}{ext}"
                if download_hero(session, entry["image"], dest):
                    entry["hero_file"] = str(dest.relative_to(BASE)).replace("\\", "/")
                else:
                    entry["notes"].append("hero download failed")
            else:
                entry["notes"].append("no model-specific hero image on page")
        else:
            entry["brand_class"] = classify_robot(name, resolved_url, None)
            entry["notes"].append(f"fetch failed http={status}")

        # YouTube search when page has no video or for AE gaps
        if not entry["youtube"] or entry["brand_class"] in ("ae_own", "fanuc", "jaka", "aubo", "ur"):
            yt = search_youtube_for_robot(name, entry.get("brand_class") or "other", session)
            if yt:
                seen = {v.get("url") for v in entry["youtube"]}
                for v in yt:
                    if v.get("url") not in seen:
                        entry["youtube"].append(v)

        entry["recommended_tags"] = recommended_tags(
            name, entry.get("brand_class") or "other", entry["features"], entry["specs"]
        )

        bc = entry.get("brand_class") or "other"
        if entry["usable_hero"]:
            if bc == "ae_own":
                brand_counts["ae_own"] += 1
            elif bc in ("fanuc", "aubo", "jaka", "ur", "youibot"):
                brand_counts["reseller"] += 1
            else:
                brand_counts["other"] += 1
        else:
            brand_counts["no_hero"] += 1

        per_robot.append(entry)

    report = {
        "company_id": COMPANY_ID,
        "storefront": DOMAIN,
        "dead_dns_domain": "aerobot.cc",
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "discovered_urls": discovered[:80],
        "catalog_entries": len(catalog),
        "summary": {
            "robots_total": len(robots),
            "usable_heroes": sum(1 for e in per_robot if e.get("hero_file")),
            "ae_brand_heroes": sum(1 for e in per_robot if e.get("brand_class") == "ae_own" and e.get("hero_file")),
            "reseller_heroes": sum(
                1 for e in per_robot
                if e.get("brand_class") in ("fanuc", "aubo", "jaka", "ur", "youibot") and e.get("hero_file")
            ),
            "other_heroes": sum(
                1 for e in per_robot
                if e.get("brand_class") not in ("ae_own", "fanuc", "aubo", "jaka", "ur", "youibot")
                and e.get("hero_file")
            ),
            "no_hero": sum(1 for e in per_robot if not e.get("hero_file")),
            "unique_pages_fetched": len(html_cache),
        },
        "robots": per_robot,
    }

    report_path = OUT_DIR / "scrape-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote", report_path)
    print("SUMMARY", json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
