"""One-off AE Robotics product page fetch for research summary."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from youtube_metadata import enrich_video_list, fetch_youtube_metadata

session = requests.Session()
session.headers["User-Agent"] = "RobotAIGeek-ResearchAgent/1.0"

URLS = {
    "AIR3-A": "https://www.automationar.com/product/ae-air3-a-robot-arm-industrial-6-axis-payload-3kg-and-arm-reach-560mm-robot-mechanical-arm-claw-166.html",
    "AIR7L-B": "https://www.automationar.com/product/ae-air7l-b-arc-welding-robot-manipulator-intelligent-robotic-arm-pick-and-place-robot.html",
    "AIR8-A": "https://www.automationar.com/product/ae-industrial-robot-air8-a-6-axis-robot-programmig-8kg-payload-cobot-industrial-robotic-arm-from-sh.html",
    "AIR10-A": "https://www.automationar.com/product/ae-air10-a-automation-manipulator-industrial-middle-6-axis-robot-arm-like-kuka-robot-arm.html",
    "AIR20-A": "https://www.automationar.com/product/industry-robot-arm-AE-China-AIR20-A-6-axis-robot-arm-20kg-payload-industrial-robots-from-shenzhen.html",
    "AE-25-Palletizer": "https://www.automationar.com/product/ae-25-series-6-axis-industrial-robot-arm-palletizer-robot.html",
    "AE20-Cobot": "https://www.automationar.com/product/ae20-cobot-6-axis-collaborative-robot-arm.html",
    "SCARA-TS5-600": "https://www.automationar.com/product/china-hotsale-4-axis-scara-robot-5kg-payload-600mm-arm-reach.html",
    "Delta-AR-600D": "https://www.automationar.com/product/3-4axis-delta-robot-1kg-payload-600mm-working-diameter-for-packing-application.html",
    "Delta-AR-500D": "https://www.automationar.com/product/3-4axis-delta-robot-1kg-payload-500mm-working-diameter-for-packing-application.html",
    "Delta-AR-800D": "https://www.automationar.com/product/3-4axis-delta-robot-3kg-payload-800mm-working-diameter-for-packing-application.html",
    "Delta-AR-1000D": "https://www.automationar.com/product/3-4axis-delta-robot-5kg-payload-1000mm-working-diameter-for-packing-application.html",
    "Trans-200": "https://www.automationar.com/product/AGV-china-top-3-mobile-industrial-robots-payload-up-to-200kg.html",
    "Trans-500": "https://www.automationar.com/product/china-top-3-mobile-industrial-robots-payload-up-to-500kg.html",
}

YT_CANDIDATES = [
    "https://www.youtube.com/watch?v=nOCPZ5022gQ",
    "https://www.youtube.com/watch?v=5editor_1657253559",  # placeholder - will filter
]

TAG = re.compile(r"<[^>]+>")


def extract_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in (
        "Payload", "Arm reach", "Reach", "Weight", "AXIS No", "Axes",
        "Repeatability", "Position repeatability", "Rated load", "Freedom",
        "Model", "Type", "Brand",
    ):
        m = re.search(rf"{re.escape(key)}\s*:?\s*([^<\n|]+)", text, re.I)
        if m:
            out[key] = re.sub(r"\s+", " ", m.group(1)).strip()[:80]
    return out


def extract_hero_imgs(html: str) -> list[str]:
    imgs = re.findall(r'(?:src|data-src|data-original)=["\']([^"\']+)["\']', html, re.I)
    heroes = []
    for u in imgs:
        if "qiniu" in u.lower() or "digood" in u.lower():
            if not re.search(r"logo|icon|banner|wechat|cert", u, re.I):
                heroes.append(u.split("?", 1)[0] if "imageView2" in u else u)
    return list(dict.fromkeys(heroes))[:8]


def main() -> None:
    products = {}
    all_yt: set[str] = set()

    for name, url in URLS.items():
        r = session.get(url, timeout=90)
        html = r.text or ""
        yt_ids = re.findall(
            r"(?:youtube\.com/watch\?v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})",
            html,
        )
        yt_urls = [f"https://www.youtube.com/watch?v={v}" for v in yt_ids]
        all_yt.update(yt_urls)
        products[name] = {
            "url": url,
            "http_status": r.status_code,
            "html_len": len(html),
            "title": (re.search(r"<title[^>]*>([^<]+)</title>", html, re.I) or [None, ""])[1][:120],
            "model_line": (re.search(r"Model:\s*([^<\n|]+)", html, re.I) or [None, ""])[1].strip(),
            "specs": extract_kv(html),
            "hero_images": extract_hero_imgs(html),
            "youtube_embedded": yt_urls,
        }

    # Known from product video CDN on AIR3-A page
    extra_yt = [
        "https://www.youtube.com/watch?v=nOCPZ5022gQ",
    ]
    # Search scrape report for embedded yt
    report_path = Path(__file__).parent / "staging/reports/ae-robotics/scrape-report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for row in report.get("robots", []):
            for u in row.get("youtube_urls") or []:
                all_yt.add(u)

    # Manual search via DDG-style: fetch pages that mention youtube
    search_pages = [
        "https://www.automationar.com/products/ae-robot-arm.html",
        "https://www.automationar.com/product/ae-air7l-b-arc-welding-robot-manipulator-intelligent-robotic-arm-pick-and-place-robot.html",
    ]
    for sp in search_pages:
        try:
            h = session.get(sp, timeout=60).text
            for v in re.findall(r"(?:youtube\.com/watch\?v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", h):
                all_yt.add(f"https://www.youtube.com/watch?v={v}")
        except requests.RequestException:
            pass

    # Web search candidates (hardcoded from automationar product pages / qiniu mp4 refs)
    manual_candidates = [
        "https://www.youtube.com/watch?v=nOCPZ5022gQ",
        "https://www.youtube.com/watch?v=Jm8h8f5VqZQ",
        "https://www.youtube.com/watch?v=8xGnSlvKj8Y",
        "https://www.youtube.com/watch?v=0kD2L8yVZ7E",
    ]
    for u in manual_candidates:
        all_yt.add(u)

    yt_enriched = enrich_video_list(sorted(all_yt), skip_rejected=False)
    ae_yt = []
    for v in yt_enriched:
        title = (v.get("title") or "").lower()
        if any(x in title for x in ("ae ", "air", "automationar", "ae robotics", "air3", "air7", "air8", "air10", "air20")):
            ae_yt.append(v)
        elif "robot" in title and "ae" in title:
            ae_yt.append(v)

    out = {"products": products, "youtube_all": yt_enriched, "youtube_ae_filtered": ae_yt}
    out_path = Path(__file__).parent / "staging/reports/ae-robotics/fetch-summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote", out_path)
    print("YT AE filtered:", len(ae_yt))
    for v in ae_yt[:6]:
        print(" ", v.get("url"), "|", v.get("title"))


if __name__ == "__main__":
    main()
