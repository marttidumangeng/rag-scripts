"""Classify every Kewei page image by MEASURING it, not by position on the page.

Two things defeat a positional heuristic on this site:
  * the parameter table is not always the first non-product image;
  * a related-products strip (vfevsdfcsd-1.jpg, gfrewfwe2-1.jpg, fwefd1-1.jpg,
    vfevc-1.jpg, fefwe-1.jpg, gbvef-1.jpg, bgvfregv2-1.jpg ...) repeats on EVERY
    model page and would otherwise be staged as that model's photos.

So: measure each distinct URL once, count how many model pages it appears on, and
treat anything appearing on 3+ pages as site chrome. The parameter table is the
big ~1.9:1 sheet (>=3500px wide); the work envelope is the other large image.
"""
import io
import json
import sys
import time

import requests
from PIL import Image

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"})
SP = ("C:/Users/tramk/AppData/Local/Temp/claude/"
      "C--Github-Personal-robot-ai-geek/9cff51dd-ca8d-479a-8bd9-29d05105ebd3/scratchpad/")
SHARED_PAGE_THRESHOLD = 3


def measure(url: str) -> tuple | None:
    for attempt in range(3):
        try:
            im = Image.open(io.BytesIO(S.get(url, timeout=90).content))
            return im.size
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


def main() -> int:
    harvest = json.load(open(SP + "kewei_harvest.json", encoding="utf-8"))

    pages_per_url: dict[str, set] = {}
    for code, rec in harvest.items():
        for u in rec["all_images"]:
            pages_per_url.setdefault(u, set()).add(code)

    dims: dict[str, tuple] = {}
    for i, u in enumerate(sorted(pages_per_url), 1):
        d = measure(u)
        if d:
            dims[u] = d
        if i % 25 == 0:
            print(f"  measured {i}/{len(pages_per_url)}", flush=True)
    print(f"measured {len(dims)}/{len(pages_per_url)} distinct images")

    chrome = {u for u, pages in pages_per_url.items() if len(pages) >= SHARED_PAGE_THRESHOLD}
    print(f"shared across {SHARED_PAGE_THRESHOLD}+ pages (site chrome): {len(chrome)}")

    out = {}
    for code, rec in sorted(harvest.items()):
        own = [u for u in rec["all_images"] if u not in chrome and u in dims]
        spec = [u for u in own if dims[u][0] >= 3500 and 1.75 <= dims[u][0] / dims[u][1] <= 2.15]
        envelope = [u for u in own if u not in spec and dims[u][0] >= 1500]
        photos = [u for u in own if u not in spec and u not in envelope]
        out[code] = {
            "url": rec["url"], "title": rec["title"], "body": rec["body"],
            "spec_image": spec[0] if spec else "",
            "envelope_images": envelope[:2],
            "photos": photos[:4],
        }
        print(f"  {code:14s} spec={'Y' if spec else 'N'} env={len(envelope)} photos={len(photos)}"
              f"{'   <-- NO SPEC TABLE' if not spec else ''}")

    with open(SP + "kewei_classified.json", "w", encoding="utf-8") as fh:
        json.dump({"dims": {k: list(v) for k, v in dims.items()},
                   "chrome": sorted(chrome), "models": out}, fh, ensure_ascii=False, indent=1)
    print("\nsaved kewei_classified.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
