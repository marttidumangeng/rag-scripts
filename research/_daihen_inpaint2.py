"""Precise heavy-banner crops using tuned boxes; stronger label inpaint."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

OUT = Path("staging/reports/daihen_family7")
bgr = cv2.imread(str(OUT / "heavy_banner_full.jpg"))
h, w = bgr.shape[:2]

# Stronger mask: bright whites + mid-bright semi-transparent titles
hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
mask1 = cv2.inRange(hsv, (0, 0, 190), (180, 80, 255))
# pale grey title wash (low sat, mid-high value) in upper band
mask2 = cv2.inRange(hsv, (0, 0, 140), (180, 40, 210))
mask = cv2.bitwise_or(mask1, mask2)
band = np.zeros_like(mask)
band[0 : int(h * 0.55), :] = 255
mask = cv2.bitwise_and(mask, band)
# also mask known small label regions near each robot (white text)
# approx label x positions for 5 robots
for x in (560, 640, 800, 970, 1100):
    cv2.rectangle(mask, (x, 200), (x + 90, 340), 255, -1)
mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
inp = cv2.inpaint(bgr, mask, 5, cv2.INPAINT_TELEA)
cv2.imwrite(str(OUT / "heavy_banner_inpaint2.jpg"), inp, [int(cv2.IMWRITE_JPEG_QUALITY), 94])

rgb = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB)
pil = Image.fromarray(rgb)

BOXES = {
    "v280l": (520, 120, 660, 420),
    "v350": (620, 120, 770, 420),
    "v400l": (760, 100, 960, 420),
    "v600": (960, 120, 1100, 420),
    "v700": (1085, 120, 1198, 420),
}
outdir = OUT / "inpaint2_slices"
outdir.mkdir(exist_ok=True)
for name, box in BOXES.items():
    crop = pil.crop(box)
    crop.save(outdir / f"{name}.jpg", quality=93)
    print(name, crop.size)

# V350 tighter body-only (cut top residual title)
v350b = pil.crop((630, 160, 760, 420))
v350b.save(outdir / "v350_body.jpg", quality=93)
print("v350_body", v350b.size)
