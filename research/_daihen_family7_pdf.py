"""Render catalog PDF pages + extract usable product stills for family-7."""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.daihen-robot.com/"}
OUT = Path("staging/reports/daihen_family7")
OUT.mkdir(parents=True, exist_ok=True)

PDFS = {
    "heavy": "https://www.daihen-robot.com/assets/download/FD_V280L_V350_V400L_V600_V700/FD_V280L_V350_V400L_V600_V700_Catalog.pdf",
    # guess alternate catalog paths for V80 class
    "v80a": "https://www.daihen-robot.com/assets/download/FD_V80_V100_V130/FD_V80_V100_V130_Catalog.pdf",
    "v80b": "https://www.daihen-robot.com/assets/download/FD_V80/FD_V80_Catalog.pdf",
    "v80c": "https://www.daihen-robot.com/assets/img/en/robot/items/FD_V80_V100_V130_Catalog.pdf",
    "otc": "https://www.otc-daihen.com/files/V100-series.pdf",
}


def main() -> None:
    import fitz

    report = []
    for key, url in PDFS.items():
        try:
            r = requests.get(url, headers=UA, timeout=90)
        except Exception as e:
            print("FAIL", key, e)
            continue
        print(key, r.status_code, len(r.content), url.split("/")[-1])
        if r.status_code != 200 or len(r.content) < 20000:
            continue
        (OUT / f"{key}.pdf").write_bytes(r.content)
        doc = fitz.open(stream=r.content, filetype="pdf")
        for pi in range(min(len(doc), 4)):
            page = doc[pi]
            # high-res page render
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            name = f"{key}_page{pi}_{pix.width}x{pix.height}.png"
            path = OUT / name
            pix.save(str(path))
            print(" PAGE", name)
            # also dump large embedded images
            for ii, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                try:
                    ipix = fitz.Pixmap(doc, xref)
                except Exception:
                    continue
                if ipix.n > 4:
                    ipix = fitz.Pixmap(fitz.csRGB, ipix)
                if ipix.width < 400 or ipix.height < 350:
                    continue
                if ipix.width / max(ipix.height, 1) > 2.1:
                    continue
                iname = f"{key}_p{pi}_img{ii}_{ipix.width}x{ipix.height}.png"
                ipath = OUT / iname
                ipix.save(str(ipath))
                md5 = hashlib.md5(ipath.read_bytes()).hexdigest()
                print("  EMB", iname, md5[:10])
                report.append({"key": key, "path": str(ipath), "md5": md5, "page": pi})
    Path("staging/reports/daihen-family7-pdf.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
