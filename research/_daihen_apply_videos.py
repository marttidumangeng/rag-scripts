"""Resolve DAIHEN OEM library movie pages → YouTube; PATCH pending robots."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
BASE = "https://www.daihen-robot.com"
LIB = f"{BASE}/en/library/"
YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})",
    re.I,
)
FD_RE = re.compile(r"\bFD-[A-Z0-9]+(?:L|S)?\b", re.I)

# Prefer model-only (or model+power-source) clips; skip huge multi-model showcases as primary.
SKIP_YT = {
    "bEbUmeklDc4",  # transformer casing — many models listed
}

# Curated extras (OEM channel / USA) when library tags a family
CURATED = {
    # Official OTC DAIHEN FD-series programming tutorial — attach only if no model clip
    "_FD_SERIES_": {
        "url": "https://www.youtube.com/watch?v=tWAYn87uqTk",
        "title": "Welding Robot Programming | FD-series Tutorial (OTC DAIHEN)",
    },
}

# Models that are arc-welding FD series and may take the series tutorial as fallback
WELDING_FALLBACK = {
    "FD-V8",
    "FD-V8L",
    "FD-B6",
    "FD-B6L",
    "FD-B26",
    "FD-H5",
    "FD-V25",
    "FD-V25L",
    "FD-BT6",
    "FD-BT6L",
    "FD-VT8L",
    "FD-A20",
    "FD-B100",
    "FD-V166",
    "FD-V210",
    "FD-VC4",
    "FD-V80",
    "FD-V100",
    "FD-V130",
    "FD-V350",
    "FD-V400L",
    "FD-V600",
    "FD-V700",
}


def normalize_models(text: str) -> set[str]:
    found = {m.upper() for m in FD_RE.findall(text or "")}
    for m in re.finditer(r"\((FD-[A-Z0-9]+(?:L|S)?)\)", text or "", re.I):
        found.add(m.group(1).upper())
    return found


def resolve_movie(href: str, cache: dict[str, str | None]) -> str | None:
    # Direct youtube embed hrefs on the library page
    if "youtube.com" in href or "youtu.be" in href:
        ids = YT_RE.findall(href)
        if ids:
            return f"https://www.youtube.com/watch?v={ids[0]}"
    url = urljoin(BASE, href)
    if url in cache:
        return cache[url]
    try:
        r = requests.get(url, headers=UA, timeout=40)
    except Exception as e:
        print("movie fail", url, e)
        cache[url] = None
        return None
    ids = list(dict.fromkeys(YT_RE.findall(r.text)))
    media = f"https://www.youtube.com/watch?v={ids[0]}" if ids else None
    if not media:
        # html5 <source src="...mp4"> or <video src=...>
        mp4 = re.findall(
            r'(?:src|href)=["\']([^"\']+\.mp4[^"\']*)["\']',
            r.text,
            re.I,
        )
        if mp4:
            media = urljoin(url, mp4[0])
    cache[url] = media
    print(f"  resolve {href} -> {media}")
    return media


def scrape_library_cards() -> list[dict]:
    r = requests.get(LIB, headers=UA, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    cache: dict[str, str | None] = {}
    cards = []
    for li in soup.select("li"):
        a = li.find("a", class_="youtube", href=True)
        if not a:
            continue
        title = " ".join(li.get_text(" ", strip=True).split())
        models = normalize_models(title)
        media = resolve_movie(a["href"], cache)
        if not media:
            continue
        yt_id = None
        m = YT_RE.search(media)
        if m:
            yt_id = m.group(1)
            if yt_id in SKIP_YT:
                continue
        cards.append(
            {
                "title": title[:160],
                "models": sorted(models),
                "url": media,
                "page": urljoin(BASE, a["href"]),
                "yt_id": yt_id,
            }
        )
        time.sleep(0.15)
    return cards


def scrape_tagged_youtube_section(html_path: Path) -> list[dict]:
    """Older library section embeds youtube ids with FD model tags in nearby text."""
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for m in YT_RE.finditer(html):
        vid = m.group(1)
        if vid in SKIP_YT:
            continue
        el = soup.find(href=re.compile(re.escape(vid))) or soup.find(
            attrs={"src": re.compile(re.escape(vid))}
        )
        block = el.find_parent(["li", "article", "div"]) if el else None
        text = block.get_text(" ", strip=True) if block else ""
        if not text:
            start, end = max(0, m.start() - 400), min(len(html), m.end() + 400)
            text = re.sub(r"<[^>]+>", " ", html[start:end])
            text = re.sub(r"\s+", " ", text)
        models = normalize_models(text)
        if not models:
            continue
        out.append(
            {
                "title": text[:160],
                "models": sorted(models),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "page": LIB,
                "yt_id": vid,
            }
        )
    return out


def pick_for_model(cards: list[dict], model: str) -> list[dict]:
    """Prefer clips that name this model and few others."""
    hits = []
    for c in cards:
        if model not in c["models"]:
            continue
        n = len(c["models"])
        hits.append((n, c))
    hits.sort(key=lambda x: (x[0], x[1]["title"]))
    # unique by url, max 2
    seen = set()
    picked = []
    for _, c in hits:
        if c["url"] in seen:
            continue
        seen.add(c["url"])
        picked.append(c)
        if len(picked) >= 2:
            break
    return picked


def main() -> None:
    apply = "--apply" in sys.argv
    html_path = Path("staging/reports/daihen-library.html")
    if not html_path.is_file():
        html_path.write_text(requests.get(LIB, headers=UA, timeout=60).text, encoding="utf-8")

    print("Scraping library movie pages…")
    cards = scrape_library_cards()
    print(f"movie cards resolved: {len(cards)}")
    tagged = scrape_tagged_youtube_section(html_path)
    print(f"tagged yt clips: {len(tagged)}")
    all_cards = cards + tagged

    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(1402)
        if (r.get("status") or "") == "pending_review"
    ]
    print(f"pending robots: {len(robots)}")

    plan = []
    for r in robots:
        rid = r["id"]
        name = (r.get("name") or "").strip()
        model = name.upper()
        picks = pick_for_model(all_cards, model)
        used_fallback = False
        if not picks and model in WELDING_FALLBACK:
            fb = CURATED["_FD_SERIES_"]
            picks = [
                {
                    "title": fb["title"],
                    "models": [model],
                    "url": fb["url"],
                    "page": "https://www.youtube.com/watch?v=tWAYn87uqTk",
                    "yt_id": "tWAYn87uqTk",
                    "fallback": True,
                }
            ]
            used_fallback = True
        video_urls = [
            {"url": p["url"], "title": p["title"][:120], "description": ""}
            for p in picks
        ]
        plan.append(
            {
                "id": rid,
                "name": name,
                "n": len(video_urls),
                "fallback": used_fallback,
                "videos": video_urls,
                "sources": [p.get("page") for p in picks],
            }
        )
        print(f"{rid} {name}: {len(video_urls)}" + (" (series fallback)" if used_fallback else ""))
        for v in video_urls:
            print(f"  {v['url']} | {v['title'][:70]}")

    Path("staging/reports/daihen-video-apply-plan.json").write_text(
        json.dumps({"cards": len(all_cards), "plan": plan}, indent=2),
        encoding="utf-8",
    )

    if not apply:
        print("dry-run; pass --apply to PATCH video_urls")
        return

    ok = fail = 0
    for row in plan:
        if not row["videos"]:
            continue
        try:
            client._patch(
                f"robots/robots/{row['id']}/",
                {"video_urls": row["videos"]},
            )
            ok += 1
            print(f"patched {row['id']} {row['name']}")
        except Exception as e:
            fail += 1
            print(f"FAIL {row['id']}: {e}")
        time.sleep(0.25)
    print(f"done ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
