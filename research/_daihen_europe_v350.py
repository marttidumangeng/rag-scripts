"""Download OTC Europe FD-V350 product page images at best available size."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0"}
OUT = Path("staging/reports/daihen_family7/europe")
session = requests.Session()
session.headers.update(UA)

pages = {
    "v350": "https://otc-daihen.com/product-page/23420/",
    "v350mod": "https://otc-daihen.com/product-page/23398/",
}
for key, url in pages.items():
    r = session.get(url, timeout=45)
    print(key, r.status_code, r.url, len(r.content))
    (OUT / f"{key}.html").write_text(r.text, encoding="utf-8")
    imgs = re.findall(
        r'(?:src|data-src|content)=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']',
        r.text,
        re.I,
    )
    for img in sorted(set(imgs)):
        full = urljoin(r.url, img)
        if "productImages" not in full and "Medien" not in full:
            continue
        ir = session.get(full, timeout=30)
        if ir.status_code != 200 or len(ir.content) < 3000:
            continue
        md5 = hashlib.md5(ir.content).hexdigest()[:10]
        path = OUT / f"{key}_{md5}.webp"
        path.write_bytes(ir.content)
        try:
            im = Image.open(path)
            # save jpg for Read tool
            jpg = OUT / f"{key}_{md5}.jpg"
            im.convert("RGB").save(jpg, quality=93)
            print(" ", path.name, im.size, len(ir.content), full[-80:])
        except Exception as e:
            print(" ", path.name, "openfail", e, len(ir.content))
