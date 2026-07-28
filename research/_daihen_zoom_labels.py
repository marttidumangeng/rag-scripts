"""Zoom arm-label regions for OCR/visual ID."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

OUT = Path("staging/reports/daihen_family7/labels")
OUT.mkdir(parents=True, exist_ok=True)

PATHS = {
    "i04": "staging/reports/daihen_family7/page5_imgs/i04_512x748.jpg",
    "i01": "staging/reports/daihen_family7/page5_imgs/i01_536x689.jpg",
    "i00": "staging/reports/daihen_family7/page5_imgs/i00_628x606.jpg",
    "otc600": "staging/reports/daihen_family7/otc_1898_b1dacb82a2_FD-V600_700.png",
    "otc350": "staging/reports/daihen_family7/otc_3054_a5ca76dc41_FD-V350.png",
    "otc400": "staging/reports/daihen_family7/otc_2472_0c5932919b_FD-V400L.png",
    "v80": "staging/reports/daihen_family7/v80alt2_p0_i3_938x2517.jpg",
}

for name, p in PATHS.items():
    im = Image.open(p).convert("RGB")
    w, h = im.size
    boxes = {
        "mid": (int(w * 0.10), int(h * 0.20), int(w * 0.80), int(h * 0.50)),
        "hi": (int(w * 0.05), int(h * 0.10), int(w * 0.90), int(h * 0.40)),
    }
    for cn, box in boxes.items():
        c = im.crop(box)
        c = c.resize((c.width * 3, c.height * 3), Image.Resampling.LANCZOS)
        path = OUT / f"{name}_{cn}.jpg"
        c.save(path, quality=95)
        print(path.name, box)
