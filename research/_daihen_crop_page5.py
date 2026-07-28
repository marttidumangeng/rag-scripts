"""Crop V280L/V350/V400L/V600 from heavy_en_page5.png for visual QA."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

src = Path("staging/reports/daihen_family7/heavy_en_page5.png")
im = Image.open(src)
print("size", im.size)
w, h = im.size
out = Path("staging/reports/daihen_family7/page5_crops")
out.mkdir(parents=True, exist_ok=True)

# Two-page spread: left ~0-0.5, right ~0.5-1.0
# Right column heavy-load photos sit left of the diagrams within right half.
# Approximate photo slots (fractions of full spread)
# Based on typical catalog: photo column x~0.52-0.62, 4 rows
slots = {
    "v280l": (0.515, 0.08, 0.62, 0.28),
    "v350": (0.515, 0.30, 0.62, 0.50),
    "v400l": (0.515, 0.52, 0.62, 0.72),
    "v600": (0.515, 0.74, 0.62, 0.94),
    # left column for reference
    "v100": (0.015, 0.08, 0.12, 0.28),
    "v130": (0.015, 0.30, 0.12, 0.50),
}

for name, (l, t, r, b) in slots.items():
    box = (int(l * w), int(t * h), int(r * w), int(b * h))
    crop = im.crop(box)
    path = out / f"{name}.jpg"
    crop.convert("RGB").save(path, quality=92)
    print(name, box, crop.size)
