"""Stage Shandong Kewei / KOWELL (company 1604) — harvest every model page.

The site keeps its specification table as an IMAGE (no text layer on the page), so
this collects the page prose plus the image URLs; the spec numbers are read
visually from the parameter image in a second pass.

Production-line pages (/package-palletizing-production-line/ etc.) are systems, not
robot models, and are deliberately not harvested.
"""
import json
import re
import time
import html as htmllib

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"})

DEST = ("C:/Users/tramk/AppData/Local/Temp/claude/"
        "C--Github-Personal-robot-ai-geek/9cff51dd-ca8d-479a-8bd9-29d05105ebd3/"
        "scratchpad/kewei_harvest.json")

# Chrome that appears on every page and must never be staged as a robot photo.
CHROME = re.compile(
    r"logo|fot_logo|bannercon|/static/images/|img\d+\.png|^s\.jpg$|^l\.jpg$"
    r"|production-line|Palletizing-robot-assembly|Stacking|Package-palletizing"
    r"|Bucket-product|Reliable-Production|Advanced-Automated", re.I)


def get(url: str) -> str:
    for attempt in range(4):
        try:
            return S.get(url, timeout=60).text
        except Exception:
            time.sleep(2 * (attempt + 1))
    return ""


# Explicit, because crawling this site is NON-DETERMINISTIC: each model is linked
# only from some other model's related-products strip, so successive runs reach
# different subsets (three runs returned three different 23-page sets). This is the
# union of every page seen, verified 200.
MODEL_SLUGS = [
    "4-axis-robot-arm-kw1030m-1835",
    "arm-robot-6-axis-kw1007b-740",          # titled KW1008B-830 — slug/title disagree
    "cobot-palletizer-kw1030d-1800",
    "kw1015b-1700", "kw1020b-2000", "kw1030b-1850", "kw1035b-1850",
    "kw1050b-2100", "kw1070b-2100", "kw1080b-2200", "kw1080b-2700",
    "kw1170b-2700", "kw1220b-2700", "kw1220b-3200", "kw1280b-2700",
    "mobile-palletizing-workstation-kw1040d-2000",
    "robot-6-axis-arm-kw10010-920",          # titled KW1010B-920
    "robot-palletizer-kw1060m-2100",
    "robot-welding-kw1010b-1440",
    "robotic-palletizer-kw1010m-1500",
    "robotic-palletizing-kw1300m-3200",
    "six-axis-robot-kw1004b-580",            # titled KW1005B-950 — slug/title disagree
    "universal-robot-kw1012b-1550",
    "welding-robot-kw1012b-2010",            # ALREADY IN PROD as robot 6737
    "wood-board-handling-robot-kw1080m-3400",
    "wood-board-loading-robot-kw1080m-3000",
]


def discover() -> list[str]:
    return [f"https://www.keweirobot.com/{s}/" for s in MODEL_SLUGS]


def code_from_url(url: str) -> str:
    """The slug is authoritative. Taking the first KW code out of the page body
    picks up a RELATED product from the recommendations strip — that read
    /six-axis-robot-kw1004b-580/ as KW1005B-950."""
    m = re.search(r"(kw\d{4,5}[a-z]?-\d{3,4})", url, re.I)
    if not m:
        return ""
    raw = m.group(1).upper()
    # slug kw10010-920 is the KW1010B-920 page with a mangled slug; keep the raw
    # form and let the page title correct it below.
    return raw


def harvest(url: str) -> dict:
    b = get(url)
    title = re.search(r"<title>(.*?)</title>", b, re.S)
    title = htmllib.unescape(re.sub("<[^>]+>", "", title.group(1))).split(" - ")[0].strip() if title else ""

    # Prefer the code as the TITLE states it (the vendor's own canonical form),
    # falling back to the slug. Never the page body — that yields a sibling model.
    slug_code = code_from_url(url)
    title_code = re.search(r"\b(KW\d{4,5}[A-Z]?-\d{3,4})\b", title, re.I)
    code = (title_code.group(1).upper() if title_code else slug_code)

    text = re.sub(r"<script.*?</script>", " ", b, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", text)))
    body = ""
    m = re.search(r"Product Description(.*?)(?:◎ Product Application|◎ Product Parameters)", text, re.S)
    if m:
        body = m.group(1).strip()

    imgs, seen = [], set()
    for src in re.findall(
            r'(?:src|data-src|data-original|data-lazy-src)=["\']([^"\']+?\.(?:jpg|jpeg|png|webp))["\']', b, re.I):
        if src.startswith("//"):
            src = "https:" + src
        if src.startswith("/"):
            src = "https://www.keweirobot.com" + src
        if not src.startswith("http") or src in seen:
            continue
        seen.add(src)
        name = src.rsplit("/", 1)[-1]
        if CHROME.search(name) or CHROME.search(src):
            continue
        imgs.append(src)

    # The model's own render is the file named after its code; the two unnamed
    # PNGs right after it are the parameter table and the work-envelope drawing.
    own = [i for i in imgs if code and code.lower() in i.lower()]
    others = [i for i in imgs if i not in own]
    sibling_codes = re.compile(r"KW\d{4,5}[A-Z]?-\d{3,4}", re.I)
    # drop images named for a DIFFERENT model (the page lists related products)
    others = [i for i in others if not sibling_codes.search(i.rsplit("/", 1)[-1])]
    return {
        "url": url, "title": title, "code": code, "body": body[:1200],
        "own_images": own, "diagram_images": others[:2], "all_images": imgs[:12],
    }


def main() -> int:
    urls = discover()
    print(f"{len(urls)} model pages\n")
    out = {}
    for u in urls:
        rec = harvest(u)
        out[rec["code"] or u] = rec
        print(f"  {rec['code']:16s} own={len(rec['own_images'])} diag={len(rec['diagram_images'])} "
              f"| {rec['title'][:46]}")
    with open(DEST, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("\nsaved", DEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
