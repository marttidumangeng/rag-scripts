"""Zoom label on Europe V350 hero to confirm model text."""
from pathlib import Path
from PIL import Image

im = Image.open("staging/reports/daihen_family7/final/3054-FD-V350-hero.jpg")
w, h = im.size
# OTC oval is on upper arm - mid-left
box = (int(w * 0.25), int(h * 0.20), int(w * 0.70), int(h * 0.45))
c = im.crop(box).resize((900, 600), Image.Resampling.LANCZOS)
out = Path("staging/reports/daihen_family7/labels/eu_v350_label.jpg")
out.parent.mkdir(parents=True, exist_ok=True)
c.save(out, quality=95)
print("saved", out, box)
