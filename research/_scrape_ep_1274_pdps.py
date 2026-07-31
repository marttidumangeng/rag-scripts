"""Scrape live EP PDPs for heroes, specs, features."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Live keepers + remaps
PDPS = {
    4943: ("QDD30T/30TS", "https://ep-equipment.com/product/qdd30s/", "maybe_rename_to_QDD30S"),
    4942: ("EPT20-30TW", None, "brochure_only"),
    4941: ("JXO", "https://ep-equipment.com/product/jx0/", "rename_JX0"),
    4940: ("ES12-25WA", None, "brochure"),
    4939: ("ES20-WA", None, "brochure"),
    4938: ("ES12-12ES ES12-25MM", None, "brochure"),
    4937: ("ES10-10ES ES10-22MM", None, "brochure"),
    4936: ("ES18-40WA", None, "brochure"),
    4935: ("ES14-30WA", None, "brochure"),
    4934: ("RPL251/301", "https://ep-equipment.com/product/rpl251/", "family_keep_both_note_rpl301"),
    4933: ("WPL201", "https://ep-equipment.com/product/wpl202/", "maybe_superseded"),
    4932: ("HPL152", None, "overview_only"),
    3568: ("EPT20-RAP", "https://ep-equipment.com/product/ept20-rap/", "live"),
    2752: ("ES15-15ES", "https://ep-equipment.com/product/es15-15es/", "live"),
    2751: ("ESL122", "https://ep-equipment.com/product/esl122/", "live"),
    2750: ("EPT25-WA", "https://ep-equipment.com/product/ept25-wa/", "live"),
    2749: ("EPT20-20WA", "https://ep-equipment.com/product/ept20-20wa/", "live"),
    2748: ("KPL201", "https://ep-equipment.com/product/kpl201/", "live"),
    2747: ("EPL185", "https://ep-equipment.com/product/epl185/", "live"),
    2746: ("EPL154", "https://ep-equipment.com/product/epl154/", "live"),
}

BROCHURES = {
    4940: "https://ep-equipment.com/wp-content/uploads/2021/01/ES12-25WA-EN-Brochure-3.pdf",
    4939: "https://ep-equipment.com/wp-content/uploads/2021/01/ES20-WA-EN-Brochure.pdf",
    4938: "https://ep-equipment.com/wp-content/uploads/2021/01/ES10-10ESES12-12ESDMMM-EN-Brochure-5.pdf",
    4937: "https://ep-equipment.com/wp-content/uploads/2021/01/ES10-10ESES12-12ESDMMM-EN-Brochure-5.pdf",
    4936: "https://ep-equipment.com/wp-content/uploads/2021/09/ES18-40WA-EN-Brochure.pdf",
    4935: "https://ep-equipment.com/wp-content/uploads/2021/01/ES14-30WA-EN-Brochure-1.pdf",
    4934: "https://ep-equipment.com/wp-content/uploads/2021/01/RPL201201H251301-EN-Brochure-4.pdf",
    4941: "https://ep-equipment.com/wp-content/uploads/2022/09/JX0-EN-Brochure.pdf",
    4943: "https://ep-equipment.com/wp-content/uploads/2021/05/EU-Product-Overview-2021.pdf",
}


def fetch(url: str) -> requests.Response:
    r = requests.get(url, timeout=60, headers=HEADERS, allow_redirects=True)
    return r


def extract_page(url: str) -> dict:
    r = fetch(url)
    html = r.text if r.status_code == 200 else ""
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()

    # og:image
    og = ""
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            html,
            re.I,
        )
    if m:
        og = m.group(1)

    # CDN product images
    cdn = sorted(
        set(
            re.findall(
                r'https?://cdn\.ep-portal\.net/[^"\'\s>]+\.(?:jpg|jpeg|png|webp)',
                html,
                re.I,
            )
        )
    )
    # Prefer non-thumbnail, non-300w
    heroes = [
        u
        for u in cdn
        if "thumbnail" not in u.lower()
        and "-300w" not in u.lower()
        and "logo" not in u.lower()
    ]
    # wp-content product images
    wp = sorted(
        set(
            re.findall(
                r'https?://ep-equipment\.com/wp-content/uploads/[^"\'\s>]+\.(?:jpg|jpeg|png|webp)',
                html,
                re.I,
            )
        )
    )
    wp = [
        u
        for u in wp
        if not any(
            x in u.lower()
            for x in ("logo", "icon", "favicon", "banner", "flag", "sprite", "avatar")
        )
    ]

    # Spec tables - look for Load capacity / Rated capacity etc
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Extract likely spec lines
    specs = {}
    patterns = [
        (r"(?:Load\s*capacity|Rated\s*capacity|Capacity)\s*[:\|]?\s*(\d[\d,\.]*)\s*kg", "payload_kg"),
        (r"(?:Service\s*weight|Net\s*weight|Weight)\s*[:\|]?\s*(\d[\d,\.]*)\s*kg", "weight_kg"),
        (r"(?:Lift\s*height|Lifting\s*height|Max\.?\s*lift)\s*[:\|]?\s*(\d[\d,\.]*)\s*mm", "lift_height_mm"),
        (r"(?:Travel\s*speed|Max\.?\s*speed|Driving\s*speed).*?(\d[\d,\.]*)\s*km/?h", "speed_kmh"),
        (r"(?:Battery\s*voltage|Voltage)\s*[:\|]?\s*(\d+)\s*V", "voltage"),
        (r"(?:Overall\s*length|Length)\s*[:\|]?\s*(\d[\d,\.]*)\s*mm", "length_mm"),
        (r"(?:Overall\s*width|Width)\s*[:\|]?\s*(\d[\d,\.]*)\s*mm", "width_mm"),
        (r"(?:Overall\s*height|Height)\s*[:\|]?\s*(\d[\d,\.]*)\s*mm", "height_mm"),
    ]
    for pat, key in patterns:
        m = re.search(pat, text, re.I)
        if m:
            specs[key] = m.group(1).replace(",", "")

    # Description / features from meta or content
    desc = ""
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if m:
        desc = m.group(1)

    # Look for JSON-LD
    jsonld = []
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        try:
            jsonld.append(json.loads(m.group(1)))
        except Exception:
            pass

    return {
        "url": url,
        "status": r.status_code,
        "final": r.url,
        "title": title,
        "og": og,
        "heroes": heroes[:15],
        "cdn_all": cdn[:20],
        "wp": wp[:15],
        "specs": specs,
        "desc_meta": desc,
        "text_sample": text[:2500],
        "jsonld_types": [
            (d.get("@type") if isinstance(d, dict) else type(d).__name__) for d in jsonld
        ],
    }


def head_img(url: str) -> dict:
    try:
        r = requests.get(url, timeout=40, headers=HEADERS)
        data = r.content
        md5 = hashlib.md5(data).hexdigest()
        magic = (
            "png"
            if data[:8] == b"\x89PNG\r\n\x1a\n"
            else "jpg"
            if data[:3] == b"\xff\xd8\xff"
            else "webp"
            if data[:4] == b"RIFF"
            else f"other:{data[:4]!r}"
        )
        return {
            "url": url,
            "status": r.status_code,
            "bytes": len(data),
            "md5": md5,
            "magic": magic,
        }
    except Exception as e:
        return {"url": url, "error": str(e)}


def main() -> None:
    results = {}
    for rid, (name, url, note) in PDPS.items():
        print(f"\n=== {rid} {name} ({note}) ===")
        if not url:
            print("  no live URL")
            results[rid] = {"name": name, "note": note, "url": None}
            continue
        info = extract_page(url)
        print(f"  status={info['status']} title={info['title'][:80]}")
        print(f"  specs={info['specs']}")
        print(f"  heroes={len(info['heroes'])} cdn={len(info['cdn_all'])} wp={len(info['wp'])}")
        if info["heroes"]:
            print(f"  hero0={info['heroes'][0]}")
        elif info["cdn_all"]:
            print(f"  cdn0={info['cdn_all'][0]}")
        if info["og"]:
            print(f"  og={info['og'][:100]}")
        results[rid] = {"name": name, "note": note, **info}

    # Also check rpl301 and wpl202 and qdd30s more carefully
    for extra in [
        "https://ep-equipment.com/product/rpl301/",
        "https://ep-equipment.com/product/wpl202/",
        "https://ep-equipment.com/product/qdd30s/",
        "https://ep-equipment.com/product/es12-12wa/",
        "https://ep-equipment.com/product/es14-14wa/",
        "https://ep-equipment.com/product/jx0/",
    ]:
        print(f"\n=== EXTRA {extra} ===")
        info = extract_page(extra)
        print(f"  status={info['status']} title={info['title'][:80]}")
        print(f"  specs={info['specs']}")
        print(f"  heroes={info['heroes'][:3]}")
        results[extra] = info

    Path("staging/reports/_ep1274_pdp_scrape.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Download candidate heroes for visual verify later
    hero_dir = Path("staging/ep1274_heroes")
    hero_dir.mkdir(parents=True, exist_ok=True)
    hero_meta = {}
    seen_md5 = {}
    for rid, info in results.items():
        if not isinstance(rid, int):
            continue
        cands = (info.get("heroes") or [])[:5]
        if not cands and info.get("cdn_all"):
            # try largest-looking non-thumb
            cands = [u for u in info["cdn_all"] if "thumbnail" not in u.lower()][:5]
        if not cands and info.get("og"):
            cands = [info["og"]]
        metas = []
        for i, u in enumerate(cands):
            meta = head_img(u)
            metas.append(meta)
            md5 = meta.get("md5")
            if md5:
                seen_md5.setdefault(md5, []).append((rid, u))
            if meta.get("status") == 200 and meta.get("bytes", 0) > 8000:
                ext = "webp" if "webp" in (meta.get("magic") or "") else "jpg"
                path = hero_dir / f"{rid}_{i}.{ext}"
                # re-fetch to save
                data = requests.get(u, timeout=40, headers=HEADERS).content
                path.write_bytes(data)
                meta["saved"] = str(path)
                print(f"  saved {path.name} md5={md5} bytes={meta['bytes']}")
        hero_meta[rid] = metas

    # Hash collisions across robots
    print("\n=== HASH COLLISIONS ===")
    for md5, refs in seen_md5.items():
        if len({r for r, _ in refs}) > 1:
            print(f"SHARED {md5}: {refs}")

    Path("staging/reports/_ep1274_hero_meta.json").write_text(
        json.dumps(hero_meta, indent=2), encoding="utf-8"
    )
    print("\nDone.")


if __name__ == "__main__":
    main()
