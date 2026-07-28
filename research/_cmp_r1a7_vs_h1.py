#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
QA = Path("staging/unitree_pending_qa")
QA.mkdir(parents=True, exist_ok=True)

r = c._get("robots/robots/5362/")
for p in r.get("photos") or []:
    u = (p.get("s3_image") or p.get("url") or "").strip()
    b = requests.get(u, timeout=60).content
    md5 = hashlib.md5(b).hexdigest()[:12]
    ext = "png" if b.startswith(b"\x89PNG") else "jpg"
    path = QA / f"5362_photo_{p.get('id')}_{md5}.{ext}"
    path.write_bytes(b)
    print(p.get("id"), md5, len(b), path.name)

robots = c.list_robots_for_company(109)
for rob in robots:
    n = rob.get("name") or ""
    if "H1" not in n:
        continue
    if str(rob.get("status") or "").lower() != "published":
        continue
    d = c._get(f"robots/robots/{int(rob['id'])}/")
    hu = (d.get("s3_image") or d.get("image") or "").strip()
    hb = requests.get(hu, timeout=60).content
    print(
        "H1 sample",
        d["id"],
        d["name"],
        hashlib.md5(hb).hexdigest()[:12],
        len(hb),
    )
    (QA / f"h1_{d['id']}.png").write_bytes(hb)
    break

# also G1
for rob in robots:
    n = rob.get("name") or ""
    if "G1" not in n:
        continue
    if str(rob.get("status") or "").lower() != "published":
        continue
    d = c._get(f"robots/robots/{int(rob['id'])}/")
    hu = (d.get("s3_image") or d.get("image") or "").strip()
    hb = requests.get(hu, timeout=60).content
    print(
        "G1 sample",
        d["id"],
        d["name"],
        hashlib.md5(hb).hexdigest()[:12],
        len(hb),
    )
    break
