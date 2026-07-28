"""Download secondary hero candidates for AE-own robots."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

import requests

BASE = Path(__file__).resolve().parent
HERO_DIR = BASE / "staging/reports/ae-heroes"
REPORT = HERO_DIR / "scrape-report.json"


def safe_url(url: str) -> str:
    u = url.replace("&amp;", "&")
    if "imageView2" in u or "imageview2" in u:
        u = u.split("?", 1)[0]
    p = urlparse(u)
    return urlunparse((p.scheme, p.netloc, quote(p.path, safe="/%()"), "", "", ""))


def download(session: requests.Session, url: str, dest: Path) -> bool:
    for candidate in (url.replace("&amp;", "&"), safe_url(url)):
        try:
            r = session.get(candidate, timeout=90)
            if r.status_code == 200 and len(r.content) >= 1500:
                dest.write_bytes(r.content)
                return True
        except requests.RequestException:
            pass
    return False


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers["User-Agent"] = "RobotAIGeek-ResearchAgent/1.0"
    alt_count = 0

    for rob in report["robots"]:
        if rob.get("brand_class") != "ae_own":
            continue
        urls = rob.get("image_urls") or []
        if len(urls) < 2:
            continue
        alt = urls[1]
        ext = ".png" if re.search(r"\.png", alt, re.I) else ".jpg"
        dest = HERO_DIR / f"{rob['id']}-alt{ext}"
        if dest.exists():
            rob["hero_alt_file"] = f"staging/reports/ae-heroes/{rob['id']}-alt{ext}"
            continue
        if download(session, alt, dest):
            rob["hero_alt_file"] = f"staging/reports/ae-heroes/{rob['id']}-alt{ext}"
            alt_count += 1

    for rob in report["robots"]:
        if "delta" in rob["name"].lower() or "ar-" in rob["name"].lower():
            notes = rob.setdefault("notes", [])
            note = "Delta hero shows Warsonco branding on automationar.com — verify OEM vs white-label"
            if note not in notes:
                notes.append(note)

    report["media_quality_notes"] = {
        "delta_warsonco_branding": (
            "Delta AR-* product pages use Warsonco (华盛控) chassis images — may be white-label/resold"
        ),
        "shared_chrome_rejected": (
            "Site-wide Robot-solution内页.jpg, Collaborative-robots.jpg, AE-4.jpg rejected as heroes"
        ),
        "trans_not_ae_own": "Trans 200/500 classified as other (generic AGV listing) — not AE-branded chassis",
    }

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Downloaded {alt_count} alt heroes")


if __name__ == "__main__":
    main()
