"""Trossen Robotics (company 307) hero scrape from trossenrobotics.com.

Fetches product pages, downloads hero images, searches YouTube,
writes staging/reports/trossen-heroes/scrape-report.json.
"""
from __future__ import annotations

import json
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from web_extract import _resp_text, extract_specs_from_text, extract_youtube_ids, youtube_watch_url
from youtube_metadata import enrich_video_list, fetch_youtube_metadata, is_reject_robot_video_title

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "staging/reports/trossen-heroes"
HERO_DIR = OUT_DIR
DOMAIN = "https://www.trossenrobotics.com"
COMPANY_ID = 307

HEADERS = {"User-Agent": "RobotAIGeek-ResearchAgent/1.0"}
JS_SHELL_CHARS = 800

CHROME_IMG_RE = re.compile(
    r"(logo|favicon|icon|banner|avatar|sprite|qr|wechat|whatsapp|"
    r"footer|header|nav|social|facebook|twitter|linkedin|instagram|"
    r"loading|placeholder|blank|default|ads\.linkedin|collect/\?|"
    r"enc_avif|quality_auto)",
    re.I,
)
WIX_MEDIA_RE = re.compile(
    r"https://static\.wixstatic\.com/media/[^\s\"'<>]+",
    re.I,
)
SPEC_KEYS = re.compile(
    r"\b(payload|reach|weight|dof|degrees?\s*of\s*freedom|working\s*radius|"
    r"net\s*weight|repeatability|arm\s*reach|load\s*capacity|span|price|\$)\b",
    re.I,
)
NAV_NOISE_RE = re.compile(
    r"(?i)^(home|shop|cart|menu|contact|about|blog|support|documentation|"
    r"interbotix|trossen robotics|learn more|buy now|add to cart|subscribe|"
    r"all products|robot arms|mobile robots|kits|accessories)",
)

ROBOTS: list[dict] = [
    {"id": 5266, "name": "ALOHA Solo", "slug": "aloha-solo"},
    {"id": 5267, "name": "ALOHA Stationary V2.0", "slug": "aloha-stationary"},
    {"id": 5268, "name": "Mobile AI", "slug": "mobile-ai"},
    {"id": 5269, "name": "PincherX 100", "slug": "pincherx100"},
    {"id": 5270, "name": "ViperX 300 S", "slug": "viperx-300"},
    {"id": 5271, "name": "ViperX Aloha Follower Arm V2.0", "slug": "viperx-aloha"},
    {"id": 5272, "name": "WidowX 250 S", "slug": "widowx-250"},
    {"id": 5273, "name": "WidowX AI", "slug": "widowx-ai"},
    {"id": 5274, "name": "WidowX Aloha Set", "slug": "widowx-aloha-set"},
]

YT_QUERIES: dict[str, list[str]] = {
    "aloha": [
        "Trossen Robotics ALOHA {model}",
        "Interbotix ALOHA {model} robot",
        "ALOHA bimanual robot Trossen",
    ],
    "mobile": [
        "Trossen Mobile AI robot",
        "Interbotix Mobile AI manipulator",
    ],
    "pincher": [
        "Interbotix PincherX 100 robot arm",
        "Trossen PincherX100 demo",
    ],
    "viper": [
        "Interbotix ViperX 300 robot arm",
        "Trossen ViperX {model}",
    ],
    "widow": [
        "Interbotix WidowX {model}",
        "Trossen WidowX {model} robot arm",
    ],
    "default": [
        "Trossen Robotics {model}",
        "Interbotix {model}",
    ],
}


def product_url(slug: str) -> str:
    return f"{DOMAIN}/{slug}"


def robot_tokens(name: str) -> list[str]:
    n = name.lower()
    tokens: list[str] = []
    for pat in (
        r"aloha\s*solo",
        r"aloha\s*stationary",
        r"mobile\s*ai",
        r"pincherx\s*100|pincherx100",
        r"viperx\s*300|viperx300",
        r"viperx\s*aloha",
        r"widowx\s*250|widowx250",
        r"widowx\s*ai",
        r"widowx\s*aloha",
        r"aloha",
        r"viperx",
        r"widowx",
        r"pincherx",
    ):
        m = re.search(pat, n, re.I)
        if m:
            tokens.append(re.sub(r"\s+", "", m.group(0).lower()))
    for m in re.finditer(r"[a-z0-9]{2,}", n):
        t = m.group(0)
        if t not in ("solo", "set", "arm", "follower", "stationary", "mobile"):
            tokens.append(t)
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:12]


def classify_robot(name: str) -> str:
    n = name.lower()
    if "aloha" in n:
        return "aloha"
    if "mobile ai" in n:
        return "mobile"
    if "pincher" in n:
        return "pincher"
    if "viper" in n:
        return "viper"
    if "widow" in n:
        return "widow"
    return "default"


def wix_media_id(url: str) -> str | None:
    m = re.search(r"/media/([^/~?]+)", url)
    return m.group(1) if m else None


def normalize_wix_url(url: str, *, prefer_jpg: bool = True) -> str:
    """Strip Wix transforms; request large fill/fit variant."""
    url = unescape(url.replace("&amp;", "&"))
    mid = wix_media_id(url)
    if not mid:
        return url
    ext = ".jpg"
    if ".png" in url.lower():
        ext = ".png"
    elif ".webp" in url.lower():
        ext = ".webp"
    base = f"https://static.wixstatic.com/media/{mid}~mv2{ext}"
    if prefer_jpg and ext == ".png":
        # Wix often has jpg twin; keep png if that's what page uses
        pass
    return f"{base}/v1/fill/w_2500,h_1600,al_c,q_90/{mid}~mv2{ext}"


def is_js_shell(html: str) -> bool:
    if not html:
        return True
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if len(text) >= 3000:
        return False
    return len(text) < JS_SHELL_CHARS


def score_trossen_image(url: str, tokens: list[str], page_slug: str) -> int:
    u = url.lower()
    score = 0
    if CHROME_IMG_RE.search(u):
        score -= 100
    if "wixstatic.com/media" not in u:
        score -= 50
    if "w_2500" in u or "w_2000" in u or "fit/w_" in u:
        score += 20
    if "fill/w_" in u:
        # penalize tiny nav thumbs
        m = re.search(r"w_(\d+)", u)
        if m and int(m.group(1)) < 200:
            score -= 30
        elif m and int(m.group(1)) >= 800:
            score += 15
    if page_slug.replace("-", "") in u.replace("-", ""):
        score += 25
    for tok in tokens:
        tok_clean = tok.replace("-", "").replace(" ", "")
        if len(tok_clean) >= 4 and tok_clean in u.replace("-", "").replace("_", ""):
            score += 15
    if u.endswith(".jpg") or ".jpg/" in u:
        score += 5
    return score


def extract_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return unescape(re.sub(r"\s+", " ", soup.title.string.strip()))
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)
    return None


def extract_meta_description(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for m in soup.find_all("meta"):
        key = m.get("name") or m.get("property") or ""
        if key in ("description", "og:description"):
            content = (m.get("content") or "").strip()
            if content and len(content) > 20:
                return unescape(content)
    return None


def extract_og_image(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return normalize_wix_url(og["content"])
    return None


def extract_images(html: str, page_url: str, tokens: list[str], slug: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []

    og = extract_og_image(html)
    if og:
        candidates.append(og)

    for m in WIX_MEDIA_RE.finditer(html):
        candidates.append(normalize_wix_url(m.group(0)))

    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-image", "data-pin-media"):
            src = img.get(attr) or ""
            if src and "wixstatic" in src:
                candidates.append(normalize_wix_url(urljoin(page_url, src)))

    # Dedupe by media id, keep best transform per id
    by_id: dict[str, tuple[int, str]] = {}
    for u in candidates:
        mid = wix_media_id(u)
        if not mid:
            continue
        if CHROME_IMG_RE.search(u):
            continue
        if not re.search(r"\.(jpg|jpeg|png|webp)", u, re.I):
            continue
        sc = score_trossen_image(u, tokens, slug)
        if sc <= 0:
            continue
        prev = by_id.get(mid)
        if not prev or sc > prev[0]:
            by_id[mid] = (sc, u)

    scored = sorted(by_id.values(), key=lambda x: (-x[0], x[1]))
    return [u for _, u in scored][:15]


def extract_features(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    bullets: list[str] = []
    seen: set[str] = set()

    intro = extract_meta_description(html)
    if intro and len(intro) >= 40:
        key = intro.lower()
        if key not in seen:
            seen.add(key)
            bullets.append(intro)

    for h in soup.find_all(["h2", "h3", "h4"]):
        title = h.get_text(" ", strip=True)
        if not title or len(title) > 100 or NAV_NOISE_RE.match(title):
            continue
        sibling = h.find_next_sibling(["p", "div", "span"])
        body = sibling.get_text(" ", strip=True) if sibling else ""
        if body and 25 <= len(body) <= 500:
            line = f"{title}: {body}"
        elif 15 <= len(title) <= 120:
            line = title
        else:
            continue
        key = line.lower()
        if key not in seen:
            seen.add(key)
            bullets.append(line)

    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        if text and 20 <= len(text) <= 300 and not NAV_NOISE_RE.match(text):
            key = text.lower()
            if key not in seen:
                seen.add(key)
                bullets.append(text)

    return bullets[:12]


def extract_spec_table(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    bullets: list[str] = []
    seen: set[str] = set()

    text_blocks = soup.get_text("\n", strip=True).split("\n")
    for i, line in enumerate(text_blocks):
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if SPEC_KEYS.search(line):
            # label: value on same line
            if ":" in line and len(line) < 120:
                key = line.lower()
                if key not in seen:
                    seen.add(key)
                    bullets.append(line)
                continue
            # label then next line value
            if i + 1 < len(text_blocks):
                nxt = re.sub(r"\s+", " ", text_blocks[i + 1]).strip()
                if nxt and re.search(r"[\d$±≤≥]", nxt) and len(nxt) < 80:
                    combined = f"{line}: {nxt}"
                    key = combined.lower()
                    if key not in seen:
                        seen.add(key)
                        bullets.append(combined)

    for tr in soup.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) >= 2:
            line = f"{cells[0]}: {cells[1]}"
            if SPEC_KEYS.search(line) and line.lower() not in seen:
                seen.add(line.lower())
                bullets.append(line)

    # Price patterns in page text
    for m in re.finditer(r"(?:From\s+)?\$\s*[\d,]+(?:\.\d{2})?", html):
        snippet = m.group(0)
        if snippet.lower() not in seen:
            seen.add(snippet.lower())
            bullets.append(f"Price: {snippet}")

    return bullets[:25]


def extract_youtube(html: str) -> list[str]:
    return list(dict.fromkeys(youtube_watch_url(v) for v in extract_youtube_ids(html)))


def youtube_search_ids(query: str, limit: int = 5) -> list[str]:
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


def model_match_tokens(name: str) -> list[str]:
    tokens = robot_tokens(name)
    extra: list[str] = []
    n = name.upper()
    patterns = [
        (r"ALOHA\s*SOLO", "alohasolo"),
        (r"STATIONARY", "alohastationary"),
        (r"MOBILE\s*AI", "mobileai"),
        (r"PINCHERX\s*100", "pincherx100"),
        (r"VIPERX\s*300", "viperx300"),
        (r"VIPERX\s*ALOHA", "viperxaloha"),
        (r"WIDOWX\s*250", "widowx250"),
        (r"WIDOWX\s*AI", "widowxai"),
        (r"WIDOWX\s*ALOHA", "widowxaloha"),
    ]
    for pat, tok in patterns:
        if re.search(pat, n):
            extra.append(tok)
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens + extra:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def accept_youtube_title(
    title: str,
    name: str,
    tokens: list[str],
    description: str = "",
) -> tuple[bool, str]:
    t = (title or "").strip()
    if not t:
        return False, "empty_title_private"
    if is_reject_robot_video_title(t):
        return False, "software_training_reject"
    blob = f"{t} {description}".lower()
    unrelated = re.compile(
        r"(?i)\b(unboxing only|gameplay|minecraft|fortnite|reaction|cover|"
        r"fan\s*made|ur5 only|kuka only|abb robot only|fanuc only|"
        r"how to install ros only|gazebo tutorial only|matlab only|"
        r"lego|3d print files only)\b",
    )
    if unrelated.search(blob):
        return False, "unrelated_content"
    brand_hit = any(
        x in blob
        for x in (
            "trossen",
            "interbotix",
            "trossen robotics",
            "interbotix robotics",
        )
    )
    token_hit = any(
        tok in blob.replace("-", "").replace(" ", "").replace("_", "")
        for tok in tokens
        if len(tok) >= 4
    )
    model_patterns = {
        "ALOHA Solo": r"aloha\s*solo|aloha-solo",
        "ALOHA Stationary": r"aloha\s*stationary|stationary\s*aloha",
        "Mobile AI": r"mobile\s*ai",
        "PincherX 100": r"pincher\s*x\s*100|pincherx\s*100|pincherx100",
        "ViperX 300": r"viper\s*x\s*300|viperx\s*300|viperx300",
        "ViperX Aloha": r"viperx\s*aloha|viper\s*x.*aloha",
        "WidowX 250": r"widow\s*x\s*250|widowx\s*250|widowx250",
        "WidowX AI": r"widow\s*x\s*ai|widowx\s*ai|widowxai",
        "WidowX Aloha": r"widow\s*x\s*aloha|widowx\s*aloha",
    }
    model_hit = False
    for key, pat in model_patterns.items():
        if key.lower().replace(" ", "") in name.lower().replace(" ", "").replace("-", ""):
            if re.search(pat, blob, re.I):
                model_hit = True
                break
        elif key.split()[0].lower() in name.lower() and re.search(pat, blob, re.I):
            model_hit = True
            break
    if "aloha" in name.lower() and re.search(r"\baloha\b", blob, re.I):
        if any(x in name.lower() for x in ("solo", "stationary", "mobile")):
            if re.search(r"solo|stationary|mobile", blob, re.I):
                model_hit = True
        elif "follower" in name.lower() and re.search(r"follower|leader", blob, re.I):
            model_hit = True
    if brand_hit and (token_hit or model_hit):
        return True, "accepted_brand_model"
    if model_hit and brand_hit:
        return True, "accepted_model_brand"
    if brand_hit and re.search(
        r"robotic arm|robot arm|mobile manipulator|bimanual|teleop|teleoperation",
        blob,
        re.I,
    ):
        return True, "accepted_brand_arm_demo"
    if model_hit and re.search(r"interbotix|trossen", blob, re.I):
        return True, "accepted_model_oem"
    return False, "no_model_or_brand_match"


def search_youtube_for_robot(name: str, kind: str, session: requests.Session) -> dict:
    tokens = model_match_tokens(name)
    queries: list[str] = []
    for q in YT_QUERIES.get(kind, YT_QUERIES["default"]):
        queries.append(q.format(model=name))
    queries.append(f"site:youtube.com Trossen {name}")
    queries.append(f"site:youtube.com Interbotix {name}")

    seen: set[str] = set()
    raw_urls: list[str] = []
    for q in queries[:6]:
        for u in youtube_search_ids(q, limit=4):
            if u not in seen:
                seen.add(u)
                raw_urls.append(u)
        time.sleep(0.35)

    accepted: list[dict] = []
    rejected: list[dict] = []
    for url in raw_urls:
        meta = fetch_youtube_metadata(url, session=session)
        title = meta.get("title") or ""
        desc = meta.get("description") or ""
        ok, reason = accept_youtube_title(title, name, tokens, desc)
        entry = {
            "url": url,
            "title": title[:255] if title else "",
            "reason": reason,
        }
        if meta.get("description"):
            entry["description"] = desc[:500]
        if ok:
            accepted.append(entry)
        else:
            rejected.append(entry)

    return {"accepted": accepted[:3], "rejected": rejected[:10], "queries": queries[:6]}


def fetch_page(session: requests.Session, url: str) -> tuple[int | None, str | None, str | None]:
    try:
        r = session.get(url, timeout=90, allow_redirects=True)
        return r.status_code, _resp_text(r) if r.status_code == 200 else None, r.url
    except requests.RequestException as e:
        return None, None, str(e)


def download_hero(session: requests.Session, url: str, dest: Path) -> bool:
    candidates = [url]
    # try without heavy transform
    mid = wix_media_id(url)
    if mid:
        for ext in (".jpg", ".png", ".webp"):
            candidates.append(f"https://static.wixstatic.com/media/{mid}~mv2{ext}")
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
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


def detect_shared_hero(entries: list[dict]) -> None:
    """Flag robots sharing the same Wix media id hero."""
    by_media: dict[str, list[int]] = {}
    for e in entries:
        hero = e.get("hero") or ""
        mid = wix_media_id(hero)
        if mid:
            by_media.setdefault(mid, []).append(e["id"])
    for mid, ids in by_media.items():
        if len(ids) > 1:
            for e in entries:
                if e["id"] in ids:
                    e.setdefault("notes", []).append(
                        f"shared_hero_media_id={mid} with robot ids {ids}"
                    )


def crm_recommendations(entry: dict) -> list[str]:
    recs: list[str] = []
    if not entry.get("hero_file"):
        recs.append("replace_hero_image")
    if any("shared_hero" in n for n in entry.get("notes", [])):
        recs.append("fix_shared_wrong_hero")
    if len(entry.get("features") or []) < 3:
        recs.append("enrich_features_from_oem_page")
    if not entry.get("specs"):
        recs.append("add_specs_if_cited_on_page")
    yt = entry.get("youtube", {})
    if not yt.get("accepted"):
        recs.append("attach_youtube_demo")
    elif any("no_model" in (v.get("reason") or "") for v in yt.get("rejected", [])[:3]):
        recs.append("review_mistagged_videos_in_crm")
    if entry.get("js_shell"):
        recs.append("page_js_shell_verify_manual")
    return recs


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    per_robot: list[dict] = []

    for robot in ROBOTS:
        rid = robot["id"]
        name = robot["name"]
        slug = robot["slug"]
        url = product_url(slug)
        tokens = model_match_tokens(name)
        kind = classify_robot(name)

        entry: dict = {
            "id": rid,
            "name": name,
            "url": url,
            "js_shell": False,
            "http_status": None,
            "title": None,
            "hero_candidates": [],
            "hero": None,
            "hero_file": None,
            "features": [],
            "specs": [],
            "specs_structured": {},
            "youtube_embedded": [],
            "youtube": {"accepted": [], "rejected": [], "queries": []},
            "crm_recommendations": [],
            "notes": [],
        }

        status, html, final_url = fetch_page(session, url)
        entry["http_status"] = status
        entry["url"] = final_url or url

        if status != 200 or not html:
            entry["notes"].append(f"fetch failed http={status}")
            entry["crm_recommendations"] = crm_recommendations(entry)
            per_robot.append(entry)
            time.sleep(0.3)
            continue

        entry["js_shell"] = is_js_shell(html)
        if entry["js_shell"]:
            entry["notes"].append("page appears to be JS shell (<800 chars text)")

        entry["title"] = extract_title(html)
        imgs = extract_images(html, entry["url"], tokens, slug)
        entry["hero_candidates"] = imgs
        entry["features"] = extract_features(html)
        entry["specs"] = extract_spec_table(html)

        text_blob = " ".join(
            [entry["title"] or "", extract_meta_description(html) or "", *entry["specs"], *entry["features"][:3]]
        )
        entry["specs_structured"] = extract_specs_from_text(text_blob)

        embedded = extract_youtube(html)
        entry["youtube_embedded"] = embedded
        if embedded:
            entry["youtube"]["accepted"] = enrich_video_list(embedded, session=session, skip_rejected=True)

        yt_search = search_youtube_for_robot(name, kind, session)
        seen_urls = {v.get("url") for v in entry["youtube"]["accepted"]}
        for v in yt_search["accepted"]:
            if v.get("url") not in seen_urls:
                entry["youtube"]["accepted"].append(v)
                seen_urls.add(v.get("url"))
        entry["youtube"]["rejected"] = yt_search["rejected"]
        entry["youtube"]["queries"] = yt_search["queries"]

        if imgs:
            entry["hero"] = imgs[0]
            dest = HERO_DIR / f"{rid}.jpg"
            if download_hero(session, imgs[0], dest):
                entry["hero_file"] = str(dest.relative_to(BASE)).replace("\\", "/")
            else:
                entry["notes"].append("hero download failed")
        else:
            entry["notes"].append("no product hero image found")

        # Flag short junk features
        short_feats = [f for f in entry["features"] if len(f) < 25]
        if len(short_feats) >= 3:
            entry["notes"].append("short_junk_features_detected")

        per_robot.append(entry)
        time.sleep(0.35)

    detect_shared_hero(per_robot)
    for e in per_robot:
        e["crm_recommendations"] = crm_recommendations(e)

    report = {
        "company_id": COMPANY_ID,
        "company": "Trossen Robotics",
        "storefront": DOMAIN,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "robots_total": len(ROBOTS),
            "pages_ok": sum(1 for e in per_robot if e.get("http_status") == 200),
            "js_shells": sum(1 for e in per_robot if e.get("js_shell")),
            "heroes_downloaded": sum(1 for e in per_robot if e.get("hero_file")),
            "with_youtube": sum(1 for e in per_robot if e.get("youtube", {}).get("accepted")),
            "shared_hero_groups": sum(
                1 for e in per_robot if any("shared_hero" in n for n in e.get("notes", []))
            ),
            "needs_crm_fix": sum(1 for e in per_robot if e.get("crm_recommendations")),
        },
        "robots": per_robot,
    }

    report_path = OUT_DIR / "scrape-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote", report_path)
    print("SUMMARY", json.dumps(report["summary"], indent=2))
    for e in per_robot:
        yt_n = len(e.get("youtube", {}).get("accepted") or [])
        hero = "yes" if e.get("hero_file") else "NO"
        recs = ", ".join(e.get("crm_recommendations") or []) or "ok"
        print(f"  {e['id']} {e['name']}: hero={hero} yt={yt_n} specs={len(e.get('specs') or [])} -> {recs}")


if __name__ == "__main__":
    main()
