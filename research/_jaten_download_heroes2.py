"""Retry hero downloads + Wayback check for dead image URL."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = "https://jaten-robotics.com"
OUT_DIR = Path("staging/media/jaten")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEAD = f"{BASE}/upload/20240711/1705307770172342.png"

HEROES = {
    "R2SDM1500-335-MG0": f"{BASE}/upload/20240711/4f174e697112a8527018b5717d4cf960.png",
    "SDM300-339-MGD": f"{BASE}/upload/20240711/6983ebaa9021919cd9ce2cf0a1dd7716.png",
    "MN30-164": f"{BASE}/upload/20220319/9c5b78baba4908f79223c4f36bd467d3.jpg",
    "AGV-31-MC500": f"{BASE}/upload/20220319/c327ab945e3fb989ebccb8790634f1e9.jpg",
    "SDM500-D228": f"{BASE}/upload/20220319/9a320dcb97f746691c3cfd4c2eb4642a.jpg",
    "MN100-164_cdn": "https://cdn.robotaigeek.com/robots/original/robot-2914-mn100-164-v1783651128.jpg",
    "SDM2000-D228_cdn": "https://cdn.robotaigeek.com/robots/original/robot-2918-sdm2000-d228-v1783651129.jpg",
    "SDM1000-D228_cdn": "https://cdn.robotaigeek.com/robots/original/robot-5192-sdm1000-d228-v1783902620.jpg",
    "SDM3000-D228_cdn": "https://cdn.robotaigeek.com/robots/original/robot-5193-sdm3000-d228-v1783902621.jpg",
    "AGV31_cdn": "https://cdn.robotaigeek.com/robots/original/robot-2916-agv-31-mc500-v1783651129.jpg",
    "R2_cdn": "https://cdn.robotaigeek.com/robots/original/robot-2911-r2sdm1500-335-mg0-v1783651126.png",
    "SDM300_339_cdn": "https://cdn.robotaigeek.com/robots/original/robot-5185-sdm300-339-mgd-v1783902619.png",
    "SDM500_D228_cdn": "https://cdn.robotaigeek.com/robots/original/robot-5191-sdm500-d228-v1783902620.jpg",
    "MN30_cdn": "https://cdn.robotaigeek.com/robots/original/robot-5190-mn30-164-v1783902620.jpg",
}

session = requests.Session()
session.headers.update(HEADERS)
meta = {}

for name, url in HEROES.items():
    ok = False
    last_err = ""
    for attempt in range(3):
        try:
            r = session.get(url, timeout=60)
            ctype = (r.headers.get("content-type") or "").lower()
            ok = r.status_code == 200 and ("image" in ctype or url.endswith((".png", ".jpg", ".jpeg")))
            if ok and len(r.content) > 5000:
                ext = ".png" if ".png" in url.lower() else ".jpg"
                path = OUT_DIR / f"{name}{ext}"
                path.write_bytes(r.content)
                meta[name] = {"url": url, "status": r.status_code, "bytes": len(r.content), "path": str(path)}
                print(f"OK {name} bytes={len(r.content)}", flush=True)
                break
            last_err = f"status={r.status_code} ctype={ctype} bytes={len(r.content)}"
        except Exception as e:
            last_err = str(e)
            time.sleep(2)
    else:
        meta[name] = {"url": url, "error": last_err}
        print(f"FAIL {name}: {last_err}", flush=True)

# Wayback for dead shared image
print("--- wayback dead image ---", flush=True)
wb_api = f"https://archive.org/wayback/available?url={DEAD}"
try:
    wb = session.get(wb_api, timeout=30).json()
    closest = (wb.get("archived_snapshots") or {}).get("closest") or {}
    print(json.dumps(closest, indent=2), flush=True)
    if closest.get("available") and closest.get("url"):
        r = session.get(closest["url"], timeout=60)
        path = OUT_DIR / "dead_wayback.png"
        if r.status_code == 200 and len(r.content) > 5000:
            path.write_bytes(r.content)
            meta["dead_wayback"] = {"url": closest["url"], "bytes": len(r.content), "path": str(path)}
            print(f"wayback saved {len(r.content)}", flush=True)
except Exception as e:
    print(f"wayback err {e}", flush=True)

(OUT_DIR / "heroes.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("done", flush=True)
