"""Red Dot photo + PDF model scan / page renders."""
from __future__ import annotations

import sys
from pathlib import Path

import requests

OUT = Path("staging/media/jaten")
OUT.mkdir(parents=True, exist_ok=True)
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.red-dot.org/project/agv-31-mc500-34182",
}

u = "https://www.red-dot.org/fileadmin/user_upload/projects_pim/2016/PD/24-05527-2016PD-1.jpg"
r = requests.get(u, headers=HEADERS, timeout=60)
print("reddot", r.status_code, len(r.content), r.headers.get("content-type"), flush=True)
if r.ok and len(r.content) > 10000:
    (OUT / "reddot_agv31.jpg").write_bytes(r.content)

try:
    import fitz
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymupdf", "-q"])
    import fitz

models = [
    "R2SDM1500", "SDM300-335", "SDM100-335", "MN100-164", "MN30-164",
    "AGV-31-MC500", "SDM2000-D228", "SDM300-339", "SDM1000-335", "SDM500-335",
    "SDM200-335", "SDM500-D228", "SDM1000-D228", "SDM3000-D228", "D228", "335-MG0",
    "SDM1000", "SDM2000", "SDM3000", "MN100",
]

for pdf_name in [
    "Jaten%20AGV%20Catolog%20-3m.pdf",
    "7e459a2dee73ff38a530666d1d9f6c58.pdf",
]:
    path = OUT / pdf_name
    if not path.exists():
        print("missing", pdf_name, flush=True)
        continue
    doc = fitz.open(path)
    print("PDF", pdf_name, "pages", doc.page_count, flush=True)
    found = {m: 0 for m in models}
    for i, page in enumerate(doc):
        text = page.get_text() or ""
        for m in models:
            if m in text:
                found[m] += 1
                if found[m] <= 1:
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                    safe = m.replace("/", "-")
                    out = OUT / f"pdf_p{i}_{safe}.png"
                    pix.save(str(out))
                    print(f"  page {i} {m} -> {out.name}", flush=True)
    print(" counts", {k: v for k, v in found.items() if v}, flush=True)
print("done", flush=True)
