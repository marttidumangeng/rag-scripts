"""Convert Lumos OEM webp heroes to JPG for visual QA."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

src = Path("staging/tmp/lumos-oem")
out = Path("staging/tmp/lumos-oem-jpg")
out.mkdir(parents=True, exist_ok=True)
for p in sorted(src.glob("*.webp")):
    im = Image.open(p).convert("RGB")
    dest = out / f"{p.stem}.jpg"
    im.save(dest, quality=90)
    print(p.name, im.size, dest, dest.stat().st_size)
