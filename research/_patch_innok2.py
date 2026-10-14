"""Two defects the import dry-run exposed. DRY RUN unless APPLY=1.

1. WRONG IMAGE SHAPE (mine). The images I attached by hand were bare strings,
   while discovery writes {"url": ..., "source_page_url": ...}, and I never set
   the top-level `image` that becomes the hero. Validation said "Image URL
   missing" on all four INDUROS rows even though each had a picture.

2. INDUROS 1300 SPEED IS OUT BY A FACTOR OF NINE (the extractor's). It staged
   speed_ms=8.0 - 28.8 km/h for a 1,300 kg industrial tugger. Innok's own
   comparison table reads, across the four models in column order:

       6,5 km/h (1,8 m/s)   3,2 km/h (0,9 m/s)   6,5 km/h (1,8 m/s)   3,2 km/h (0,9 m/s)
       350s                 700                  700s                 1300

   so the 1300 runs at 0.9 m/s, the same as the 700. Corrected, and the other
   three are set to the table's exact figures rather than the extractor's
   rounding (0.888).
"""
import glob
import json
import os

STAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "staging", "robots", "innok-robotics")
APPLY = os.environ.get("APPLY") == "1"

# from Innok's own comparison table
SPEED_MS = {
    "INDUROS 350s": 1.8,
    "INDUROS 700": 0.9,
    "INDUROS 700s": 1.8,
    "INDUROS 1300": 0.9,
}
SOURCE = "https://www.innok-robotics.de/en/products/induros"

for f in sorted(glob.glob(os.path.join(STAGE, "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    name = (d.get("name") or "").strip()
    changed = []

    imgs = d.get("images") or []
    fixed = []
    for it in imgs:
        if isinstance(it, str):
            fixed.append({"url": it, "source_page_url": d.get("url") or SOURCE})
            changed.append("image->dict")
        else:
            fixed.append(it)
    if fixed:
        d["images"] = fixed
        if not (d.get("image") or "").strip():
            first = fixed[0].get("url") if isinstance(fixed[0], dict) else fixed[0]
            if first:
                d["image"] = first
                changed.append("hero set")

    if name in SPEED_MS:
        was = d.get("speed_ms")
        if was != SPEED_MS[name]:
            d["speed_ms"] = SPEED_MS[name]
            changed.append(f"speed_ms {was} -> {SPEED_MS[name]}")

    if changed:
        print(f"  {name[:20]:<22} {', '.join(changed)}")
        if APPLY:
            json.dump(d, open(f, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

print("\n(DRY RUN)" if not APPLY else "\n  staging patched")
