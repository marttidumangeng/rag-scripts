"""Inpaint text on heavy family banner; extract per-robot crops for V350/V700."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = Path("staging/reports/daihen_family7")
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.daihen-robot.com/"}

url = "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V280L_V350_V400L_V600_V700.jpg"
r = requests.get(url, headers=UA, timeout=45)
banner_path = OUT / "heavy_banner_full.jpg"
banner_path.write_bytes(r.content)
bgr = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
h, w = bgr.shape[:2]
print("banner", w, h)

# White text is bright on blue — mask high-value pixels in upper band + near labels
hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
# bright white-ish
mask = cv2.inRange(hsv, (0, 0, 200), (180, 60, 255))
# only upper 45% where titles live + small label areas
band = np.zeros_like(mask)
band[0 : int(h * 0.48), :] = 255
mask = cv2.bitwise_and(mask, band)
# dilate to cover anti-aliased edges
mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=2)
cv2.imwrite(str(OUT / "heavy_banner_mask.png"), mask)

inp = cv2.inpaint(bgr, mask, 3, cv2.INPAINT_TELEA)
cv2.imwrite(str(OUT / "heavy_banner_inpaint.jpg"), inp, [int(cv2.IMWRITE_JPEG_QUALITY), 93])

# Robot slices — tune from full width: robots sit right half
# Visual: 5 robots roughly from x=480 to 1180 on 1200
left0, right1 = 480, 1195
top = int(h * 0.18)
zone = right1 - left0
names = ["v280l", "v350", "v400l", "v600", "v700"]
outdir = OUT / "inpaint_slices"
outdir.mkdir(exist_ok=True)
rgb = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB)
pil = Image.fromarray(rgb)
for i, name in enumerate(names):
    x0 = left0 + int(zone * i / 5) - 8
    x1 = left0 + int(zone * (i + 1) / 5) + 8
    x0 = max(0, x0)
    x1 = min(w, x1)
    crop = pil.crop((x0, top, x1, h))
    # pad to squarish white? keep as-is
    path = outdir / f"{name}.jpg"
    crop.save(path, quality=93)
    print(name, crop.size)

# Also try lower-only crop for V350 (avoid residual title)
v350 = pil.crop((left0 + int(zone * 1 / 5) - 5, int(h * 0.35), left0 + int(zone * 2 / 5) + 5, h))
v350.save(outdir / "v350_lower.jpg", quality=93)
print("v350_lower", v350.size)
