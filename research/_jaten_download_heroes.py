"""Download hero candidates for visual verification."""
from __future__ import annotations

import json
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = "https://jaten-robotics.com"
OUT_DIR = Path("staging/media/jaten")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# From url-map + detail verify
HEROES = {
    "R2SDM1500-335-MG0": f"{BASE}/upload/20240711/4f174e697112a8527018b5717d4cf960.png",
    "SDM300-339-MGD": f"{BASE}/upload/20240711/6983ebaa9021919cd9ce2cf0a1dd7716.png",
    "MN30-164": f"{BASE}/upload/20220319/9c5b78baba4908f79223c4f36bd467d3.jpg",
    "AGV-31-MC500": f"{BASE}/upload/20220319/c327ab945e3fb989ebccb8790634f1e9.jpg",  # from detail scrape; also list has ecec... for ZER
    "AGV-31-MC500_list": f"{BASE}/upload/20230401/ecec72efb3d65f19d416130135cf31e5.png",  # ZER - check both
    "SDM500-D228": f"{BASE}/upload/20220319/9a320dcb97f746691c3cfd4c2eb4642a.jpg",
    # Existing CDN for robots with OK CDN (to re-verify visually)
    "MN100-164_cdn": "https://cdn.robotaigeek.com/robots/original/robot-2914-mn100-164-v1783651128.jpg",
    "SDM2000-D228_cdn": "https://cdn.robotaigeek.com/robots/original/robot-2918-sdm2000-d228-v1783651129.jpg",
    "SDM1000-D228_cdn": "https://cdn.robotaigeek.com/robots/original/robot-5192-sdm1000-d228-v1783902620.jpg",
    "SDM3000-D228_cdn": "https://cdn.robotaigeek.com/robots/original/robot-5193-sdm3000-d228-v1783902621.jpg",
    "AGV-31-MC500_cdn": "https://cdn.robotaigeek.com/robots/original/robot-2916-agv-31-mc500-v1783651129.jpg",
    "R2SDM1500_cdn": "https://cdn.robotaigeek.com/robots/original/robot-2911-r2sdm1500-335-mg0-v1783651126.png",
}

meta = {}
for name, url in HEROES.items():
    try:
        r = requests.get(url, headers=HEADERS, timeout=40)
        ok = r.status_code == 200 and "image" in (r.headers.get("content-type") or "").lower()
        ext = ".png" if "png" in url.lower() else ".jpg"
        path = OUT_DIR / f"{name}{ext}"
        if ok:
            path.write_bytes(r.content)
        meta[name] = {"url": url, "status": r.status_code, "ok": ok, "bytes": len(r.content), "path": str(path) if ok else ""}
        print(f"{name}: {r.status_code} ok={ok} bytes={len(r.content)}", flush=True)
    except Exception as e:
        meta[name] = {"url": url, "error": str(e)}
        print(f"{name}: ERR {e}", flush=True)

(OUT_DIR / "heroes.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
