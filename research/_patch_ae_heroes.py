"""Re-download failed AE hero images and patch scrape-report.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from scrape_ae_heroes import BASE, HERO_DIR, download_hero, fetch_url, extract_images, extract_spec_bullets, HEADERS, robot_tokens, strip_query_for_hero

REPORT = BASE / "staging/reports/ae-heroes/scrape-report.json"


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update(HEADERS)
    fixed = 0

    for r in report["robots"]:
        # Re-fetch AIR20 pages (CMS mislabel slug)
        if r["id"] in (1451, 3534):
            url = "https://www.automationar.com/product/ae-air3-a-industry-robot-arm-6-axis-payload-3kg-and-arm-reach-560mm-robot-mechanical-arm-claw.html"
            r["url"] = url
            status, html, final = fetch_url(session, url)
            if status == 200 and html:
                tokens = robot_tokens(r["name"])
                imgs = extract_images(html, final or url, tokens)
                specs = extract_spec_bullets(html)
                if imgs:
                    r["image_urls"] = imgs
                    r["image"] = strip_query_for_hero(imgs[0])
                    r["spec_bullets"] = specs
                    r["notes"] = ["CMS slug says AIR3 but page copy references AIR20"]

        if r["id"] in (1452, 1453):
            r.setdefault("notes", []).append(
                "override URL is sparse CMS shell — hero is site sidebar thumb, not model-specific"
            )
            r["usable_hero"] = False

        hero_path = r.get("hero_file")
        if hero_path and (BASE / hero_path).exists():
            continue
        img = r.get("image")
        if not img:
            continue
        # Prefer imageView2 CDN URL when base path has mojibake
        for candidate in r.get("image_urls") or []:
            if "imageView2" in candidate and "w/410" in candidate:
                img = candidate
                break
        ext = ".png" if re.search(r"\.png", img, re.I) else ".jpg"
        dest = HERO_DIR / f"{r['id']}{ext}"
        if download_hero(session, img, dest):
            r["hero_file"] = str(dest.relative_to(BASE)).replace("\\", "/")
            r["notes"] = [n for n in r.get("notes", []) if n != "hero download failed"]
            fixed += 1
            print("fixed", r["id"], dest.name)

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("total fixed", fixed)


if __name__ == "__main__":
    main()
