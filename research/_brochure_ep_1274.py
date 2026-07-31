"""Extract brochure PDF text/specs + raster heroes for discontinued EP models."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

BROCHURES = {
    "ES12-25WA": "https://ep-equipment.com/wp-content/uploads/2021/01/ES12-25WA-EN-Brochure-3.pdf",
    "ES20-WA": "https://ep-equipment.com/wp-content/uploads/2021/01/ES20-WA-EN-Brochure.pdf",
    "ES10-ES12-ES-MM": "https://ep-equipment.com/wp-content/uploads/2021/01/ES10-10ESES12-12ESDMMM-EN-Brochure-5.pdf",
    "ES18-40WA": "https://ep-equipment.com/wp-content/uploads/2021/09/ES18-40WA-EN-Brochure.pdf",
    "ES14-30WA": "https://ep-equipment.com/wp-content/uploads/2021/01/ES14-30WA-EN-Brochure-1.pdf",
    "RPL-family": "https://ep-equipment.com/wp-content/uploads/2021/01/RPL201201H251301-EN-Brochure-4.pdf",
    "JX0": "https://ep-equipment.com/wp-content/uploads/2022/09/JX0-EN-Brochure.pdf",
    "WPL201": "https://ep-equipment.com/wp-content/uploads/2021/01/WPL201-%E8%A5%BF%E7%8F%AD%E7%89%99.pdf",
    "EU2021": "https://ep-equipment.com/wp-content/uploads/2021/05/EU-Product-Overview-2021.pdf",
    "EU2025": "https://ep-equipment.com/wp-content/uploads/2025/11/2025-EU-Product-Overview-EN.pdf",
}

OUT = Path("staging/ep1274_brochures")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("Installing pymupdf...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pymupdf", "-q"])
        import fitz

    summary = {}
    for key, url in BROCHURES.items():
        print(f"\n=== {key} ===")
        path = OUT / f"{key}.pdf"
        if not path.exists() or path.stat().st_size < 1000:
            r = requests.get(url, timeout=120, headers=HEADERS)
            print(f"  download {r.status_code} {len(r.content)} bytes")
            if r.status_code != 200:
                summary[key] = {"error": r.status_code, "url": url}
                continue
            path.write_bytes(r.content)
        else:
            print(f"  cached {path.stat().st_size} bytes")

        doc = fitz.open(path)
        texts = []
        for i, page in enumerate(doc):
            texts.append(page.get_text())
        full = "\n".join(texts)
        text_path = OUT / f"{key}.txt"
        text_path.write_text(full, encoding="utf-8", errors="replace")

        # Spec sniff
        loads = re.findall(
            r"(?:Load\s*capacity|Rated\s*capacity|Capacity|Q)\s*[^\n\d]{0,40}(\d[\d\s,\.]*)\s*kg",
            full,
            re.I,
        )
        weights = re.findall(
            r"(?:Service\s*weight|Net\s*weight|Weight)\s*[^\n\d]{0,40}(\d[\d\s,\.]*)\s*kg",
            full,
            re.I,
        )
        print(f"  pages={doc.page_count} chars={len(full)}")
        print(f"  load hits={[x.strip() for x in loads[:8]]}")
        print(f"  weight hits={[x.strip() for x in weights[:6]]}")
        # Model mentions
        for m in ["QDD30T", "QDD30TS", "QDD30S", "EPT20-30TW", "HPL152", "WPL201", "JXO", "JX0"]:
            if m.lower() in full.lower():
                print(f"  mentions {m}")

        # Raster first page(s) for hero candidates (~170 dpi)
        hero_dir = OUT / "rasters" / key
        hero_dir.mkdir(parents=True, exist_ok=True)
        rasters = []
        for i in range(min(3, doc.page_count)):
            page = doc[i]
            pix = page.get_pixmap(dpi=170)
            img_path = hero_dir / f"page{i}.png"
            pix.save(str(img_path))
            data = img_path.read_bytes()
            md5 = hashlib.md5(data).hexdigest()
            rasters.append({"page": i, "path": str(img_path), "bytes": len(data), "md5": md5})
            print(f"  raster page{i} {len(data)} md5={md5}")

        # Also extract embedded images from page 0-1 (may be black-masked)
        embeds = []
        for i in range(min(2, doc.page_count)):
            for img in doc.get_page_images(i):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n >= 5:  # CMYK
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    if pix.width < 200 or pix.height < 200:
                        continue
                    # skip mostly-black
                    ep = OUT / "embeds" / key
                    ep.mkdir(parents=True, exist_ok=True)
                    ip = ep / f"p{i}_{xref}_{pix.width}x{pix.height}.png"
                    pix.save(str(ip))
                    data = ip.read_bytes()
                    # crude darkness check
                    sample = pix.samples[:: max(1, len(pix.samples)//5000)]
                    avg = sum(sample) / max(1, len(sample))
                    embeds.append(
                        {
                            "page": i,
                            "xref": xref,
                            "w": pix.width,
                            "h": pix.height,
                            "path": str(ip),
                            "md5": hashlib.md5(data).hexdigest(),
                            "avg_brightness": round(avg, 1),
                        }
                    )
                except Exception as e:
                    embeds.append({"page": i, "xref": xref, "error": str(e)})
        print(f"  embeds={len(embeds)}")
        for e in embeds[:8]:
            if "error" not in e:
                print(f"    {e['w']}x{e['h']} bright={e['avg_brightness']} {Path(e['path']).name}")

        summary[key] = {
            "url": url,
            "pages": doc.page_count,
            "chars": len(full),
            "loads": [x.strip() for x in loads[:12]],
            "weights": [x.strip() for x in weights[:8]],
            "rasters": rasters,
            "embeds": embeds[:20],
            "text_preview": full[:2000],
        }
        doc.close()

    # Check EU2025 for which models still listed
    eu = (OUT / "EU2025.txt").read_text(encoding="utf-8", errors="replace") if (OUT / "EU2025.txt").exists() else ""
    check_models = [
        "QDD30T", "QDD30TS", "QDD30S", "EPT20-30TW", "JX0", "JXO",
        "ES12-25WA", "ES20-WA", "ES12-12ES", "ES12-25MM", "ES10-10ES",
        "ES10-22MM", "ES18-40WA", "ES14-30WA", "RPL251", "RPL301",
        "WPL201", "WPL202", "HPL152", "EPT20-RAP", "ES15-15ES", "ESL122",
        "EPT25-WA", "EPT20-20WA", "KPL201", "EPL185", "EPL154",
        "ES12-12WA", "ES14-14WA",
    ]
    print("\n=== EU2025 MODEL PRESENCE ===")
    presence = {}
    for m in check_models:
        present = m.lower() in eu.lower()
        presence[m] = present
        print(f"  {m}: {'YES' if present else 'no'}")
    summary["eu2025_presence"] = presence

    Path("staging/reports/_ep1274_brochures.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nWrote _ep1274_brochures.json")


if __name__ == "__main__":
    main()
