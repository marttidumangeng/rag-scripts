"""Build contact sheets of Kewei's parameter-table images so they can be read.

Kewei publishes every spec as an image with no text layer, so the numbers have to
be read visually. Each parameter image is ~4440x2315 with the main table on the
LEFT and per-axis range/speed tables on the right; cropping to the left ~53% keeps
the rows that matter legible when several models share one sheet.
"""
import io
import json
import math
import sys

import requests
from PIL import Image, ImageDraw

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"})
SP = ("C:/Users/tramk/AppData/Local/Temp/claude/"
      "C--Github-Personal-robot-ai-geek/9cff51dd-ca8d-479a-8bd9-29d05105ebd3/scratchpad/")
PER_SHEET = 3
CROP_W = 0.53


def main() -> int:
    harvest = json.load(open(SP + "kewei_classified.json", encoding="utf-8"))["models"]
    rows = []
    for code, rec in sorted(harvest.items()):
        if not rec["spec_image"]:
            print(f"  {code}: no spec table published")
            continue
        url = rec["spec_image"]
        try:
            im = Image.open(io.BytesIO(S.get(url, timeout=90).content)).convert("RGB")
        except Exception as exc:                 # noqa: BLE001
            print(f"  {code}: fetch failed {exc}")
            continue
        w, h = im.size
        crop = im.crop((0, 0, int(w * CROP_W), h))
        crop.thumbnail((1350, 1350))
        rows.append((code, crop, f"{w}x{h}"))
        print(f"  {code}: {w}x{h} -> {crop.size}")

    n = math.ceil(len(rows) / PER_SHEET)
    for s in range(n):
        chunk = rows[s * PER_SHEET:(s + 1) * PER_SHEET]
        cw = max(c[1].width for c in chunk)
        ch = sum(c[1].height + 40 for c in chunk)
        sheet = Image.new("RGB", (cw, ch), "white")
        d = ImageDraw.Draw(sheet)
        y = 0
        for code, im, dim in chunk:
            d.rectangle([0, y, cw, y + 36], fill="navy")
            d.text((10, y + 12), f"{code}   ({dim})", fill="white")
            sheet.paste(im, (0, y + 40))
            y += im.height + 40
        out = SP + f"kewei_specs_{s + 1}.png"
        sheet.save(out)
        print(f"sheet {s + 1}: {[c[0] for c in chunk]} -> {sheet.size}")
    print(f"\n{len(rows)} tables across {n} sheets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
