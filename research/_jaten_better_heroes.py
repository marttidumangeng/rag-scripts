"""Extract exact heroes from url-map cards for our target models + fetch Red Dot."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
OUT = Path("staging/media/jaten")
OUT.mkdir(parents=True, exist_ok=True)

mapa = json.loads(Path("staging/reports/jaten-url-map.json").read_text(encoding="utf-8"))
cards = mapa["cards"]

# Exact name matches we care about + close cousins
wanted = {
    "R2SDM1500-335-MG0",
    "SDM300-339-MGD",
    "MN30-164",
    "AGV-31-MC500",
    "AGV-31-MC500-ZER",
    "SDM500-D228",
    "SLAM500-D228",
    "SDM1000-243",
    "SDM2000-D276-LMGD",
    "AGV-30-MC500",
    "DM1500-335",
}

picked = [c for c in cards if c["name"] in wanted]
print("picked", len(picked), flush=True)
for c in picked:
    print(c["id"], c["name"], c["hero"], flush=True)

session = requests.Session()
session.headers.update(HEADERS)

downloads = {}
for c in picked:
    url = c["hero"]
    name = c["name"].replace("/", "-")
    try:
        r = session.get(url, timeout=60)
        ok = r.status_code == 200 and len(r.content) > 3000
        ext = ".png" if ".png" in url.lower() else ".jpg"
        path = OUT / f"card_{name}{ext}"
        if ok:
            path.write_bytes(r.content)
        downloads[name] = {"url": url, "status": r.status_code, "bytes": len(r.content), "path": str(path) if ok else ""}
        print(f"card {name}: {r.status_code} {len(r.content)}", flush=True)
        time.sleep(0.3)
    except Exception as e:
        downloads[name] = {"url": url, "error": str(e)}
        print(f"card {name}: ERR {e}", flush=True)

# Red Dot official photo for AGV-31-MC500
reddot_pages = [
    "https://www.red-dot.org/project/agv-31-mc500-34182",
]
for page in reddot_pages:
    try:
        html = session.get(page, timeout=40).text
        # rough img extract
        import re
        imgs = re.findall(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', html, re.I)
        imgs = [u for u in imgs if "red-dot" in u.lower() or "cdn" in u.lower() or "project" in u.lower()]
        downloads["reddot_page_imgs"] = imgs[:15]
        print("reddot imgs", len(imgs), flush=True)
        for i, u in enumerate(imgs[:5]):
            if u.startswith("//"):
                u = "https:" + u
            r = session.get(u, timeout=40, headers={**HEADERS, "Referer": page})
            path = OUT / f"reddot_mc500_{i}.jpg"
            if r.status_code == 200 and len(r.content) > 10000:
                path.write_bytes(r.content)
                print(f"  saved {path.name} {len(r.content)} {u[:80]}", flush=True)
    except Exception as e:
        print("reddot err", e, flush=True)

# Hannover catalog PDF page scrape for image? just download PDF note
pdfs = [
    "https://www.hannovermesse.de/apollo/hannover_messe_2021/obs/Binary/A1089092/Jaten%20AGV%20Catolog%20-3m.pdf",
    "https://jaten-robotics.com/upload/20231006/7e459a2dee73ff38a530666d1d9f6c58.pdf",
]
for pdf in pdfs:
    try:
        r = session.get(pdf, timeout=90)
        name = pdf.split("/")[-1].split("?")[0][:60]
        path = OUT / name
        if r.status_code == 200 and len(r.content) > 50000:
            path.write_bytes(r.content)
            print(f"pdf {name} {len(r.content)}", flush=True)
        else:
            print(f"pdf fail {r.status_code} {len(r.content)}", flush=True)
    except Exception as e:
        print(f"pdf err {e}", flush=True)

(OUT / "card_downloads.json").write_text(json.dumps(downloads, indent=2, ensure_ascii=False), encoding="utf-8")
print("done", flush=True)
