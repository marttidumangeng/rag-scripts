"""Harvest BRINC's real drones (company 1783).

The three rows currently in the queue are NOT products — they are a sales-enquiry
page, a livery configurator and a program/category page. BRINC's actual hardware
is Guardian, Responder, Lemur 2 and Ball (Guardian Station / Responder Station are
docking infrastructure and LiveOps is software, so they are not harvested).

The site LOOKS like a JS app ("You need to enable JavaScript to run this app") but
the product copy is present in the served HTML inside specific WordPress classes —
`js-features-text` for the feature bullets, `js-fly-text` for the headline claim,
`metrics__text` for the spec numbers. A naive text strip returns only the shared
nav, which is what made these pages look empty.
"""
import json
import re
import sys
import html as htmllib

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"})
DEST = ("C:/Users/tramk/AppData/Local/Temp/claude/"
        "C--Github-Personal-robot-ai-geek/9cff51dd-ca8d-479a-8bd9-29d05105ebd3/"
        "scratchpad/brinc_harvest.json")

PRODUCTS = {
    "Guardian":  "guardian",
    "Responder": "responder",
    "LEMUR 2":   "lemur-2",
    "BRINC Ball": "brinc-ball",
}


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def harvest(name: str, slug: str) -> dict:
    url = f"https://brincdrones.com/{slug}/"
    b = S.get(url, timeout=60).text

    # Each product page uses a DIFFERENT template, so several class families are
    # tried: guardian=js-features-text, responder=features-item__value /
    # features-indicator__ttl, lemur-2=specifications-item__ttl|__value,
    # ball=product-specs-item__ttl / specifications-popup__parameters-info.
    FEATURE_CLASSES = (
        "js-features-text", "features-item__value", "features-indicator__ttl",
        "specifications-item__ttl", "specifications-item__value",
        "product-specs-item__ttl", "specifications-popup__parameters-info",
        "connect-text__ttl", "connect-text__dsc", "product-content__text",
    )
    # LEMUR 2 puts specs in label/value BLOCKS — the label span and the value span
    # are siblings, so scraping the classes independently yields "Weight" and "3.3"
    # as two unrelated bullets. Parse the block and pair them.
    specs = []
    for blk in re.findall(r'<div class="specifications-item">(.*?)</div>\s*</div>', b, re.S):
        ttl = re.search(r'specifications-item__ttl"[^>]*>(.*?)</span>', blk, re.S)
        if not ttl:
            continue
        row = clean(re.sub(r'<span class="specifications-item__ttl".*?</span>', " ", blk, flags=re.S))
        label = clean(ttl.group(1))
        if label and row:
            specs.append(f"{label}: {row}")
    SPEC_ONLY = {"specifications-item__ttl", "specifications-item__value"}

    # Responder renders each stat as <h3 class="features-item__value">42<small>min</small></h3>
    # followed by a sibling <p>Flight Time</p>. Scraping the value class alone gives
    # "42 min" with no idea what it measures — pair it with the following <p>.
    for val, lbl in re.findall(
            r'<h3 class="features-item__value">(.*?)</h3>\s*<p>(.*?)</p>', b, re.S):
        v, l = clean(val), clean(lbl)
        if v and l:
            specs.append(f"{l}: {v}")

    feats, seen = list(specs), {x.lower() for x in specs}
    for cls in FEATURE_CLASSES:
        if cls in SPEC_ONLY and specs:
            continue
        for m in re.findall(rf'class="[^"]*{re.escape(cls)}[^"]*"[^>]*>(.*?)</', b, re.S):
            t = clean(m)
            # skip a bare value already emitted as the value-half of a paired spec
            # ("42 min" when "Flight Time: 42 min" is present)
            if any(x.lower().endswith(": " + t.lower()) for x in feats):
                continue
            if t and 2 < len(t) < 220 and t.lower() not in seen:
                seen.add(t.lower())
                feats.append(t)

    headline = [clean(m) for m in re.findall(r'class="[^"]*js-fly-text[^"]*"[^>]*>(.*?)</p>', b, re.S)]
    headline = [h for h in headline if h]

    metrics, mseen = [], set()
    for m in re.findall(r'class="metrics__text"[^>]*>(.*?)</span>', b, re.S):
        t = clean(m)
        if t and t not in mseen:
            mseen.add(t)
            metrics.append(t)

    desc = re.search(r'name="description"\s+content="([^"]+)"', b)
    desc = htmllib.unescape(desc.group(1)) if desc else ""

    # Product imagery is NOT under /wp-content/uploads/ — that path only holds site
    # chrome (Rectangle-230.webp and footer.webp are on all four product pages).
    # The real assets sit in the theme under a per-product folder, which also makes
    # attribution unambiguous: /themes/bdrones/assets/images/product-<slug>/...
    folder = {"guardian": "product-guardian", "responder": "product-responder",
              "lemur-2": "product-lemur-2", "brinc-ball": "product-ball"}.get(slug, f"product-{slug}")
    imgs, iseen = [], set()
    pat = (r'(?:src|data-src|content)="(https://brincdrones\.com/wp-content/themes/bdrones/'
           r'assets/images/' + re.escape(folder) + r'/[^"]+?\.(?:jpg|jpeg|png|webp))"')
    for m in re.findall(pat, b, re.I):
        u = m.split("?")[0]
        if u not in iseen and "/svg/" not in u:
            iseen.add(u)
            imgs.append(u)

    return {"name": name, "url": url, "meta_description": desc,
            "headline": headline[:4], "features": feats, "metrics": metrics,
            "images": imgs[:8]}


def main() -> int:
    out = {}
    for name, slug in PRODUCTS.items():
        rec = harvest(name, slug)
        out[name] = rec
        print("=" * 74)
        print(f"{name}  ({rec['url']})")
        print(f"  meta    : {rec['meta_description'][:150]}")
        print(f"  headline: {rec['headline'][:2]}")
        print(f"  metrics : {rec['metrics'][:10]}")
        print(f"  features: {rec['features'][:10]}")
        print(f"  images  : {len(rec['images'])}")
    with open(DEST, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("\nsaved", DEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
