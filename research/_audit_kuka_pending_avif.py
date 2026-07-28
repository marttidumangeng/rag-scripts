#!/usr/bin/env python3
"""Scan KUKA pending_review heroes for AVIF stubs / wrong magic."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

COMPANY_ID = 1396
OUT = Path("staging/reports/kuka-1396-pending-avif.json")


def magic(body: bytes) -> str:
    if body.startswith(b"\x89PNG"):
        return "png"
    if body.startswith(b"\xff\xd8"):
        return "jpeg"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp"
    if len(body) > 12 and body[4:8] == b"ftyp" and body[8:12] in (b"avif", b"avis"):
        return "avif"
    return "other"


def main() -> int:
    c = ResearchApiClient()
    robots = c.list_robots_for_company(COMPANY_ID)
    pending = [r for r in robots if str(r.get("status") or "").lower() == "pending_review"]
    rows = []
    by_magic = Counter()
    for i, r in enumerate(pending):
        rid = int(r["id"])
        url = (r.get("s3_image") or r.get("image") or "").strip()
        if not url:
            rows.append({"id": rid, "name": r.get("name"), "issue": "no_image"})
            continue
        try:
            body = requests.get(url, timeout=45).content
        except requests.RequestException as e:
            rows.append({"id": rid, "name": r.get("name"), "issue": f"fetch:{e}"})
            continue
        m = magic(body)
        by_magic[m] += 1
        md5 = hashlib.md5(body).hexdigest()
        entry = {
            "id": rid,
            "name": r.get("name"),
            "family_key": r.get("family_key"),
            "magic": m,
            "md5": md5,
            "bytes": len(body),
            "url": url[:100],
        }
        if m == "avif" or len(body) < 40000 and m != "jpeg":
            entry["flag"] = "suspect"
            rows.append(entry)
            print(f"SUSPECT {rid} {r.get('name')} {m} {len(body)} {md5[:12]}")
        if (i + 1) % 40 == 0:
            print(f"... scanned {i+1}/{len(pending)}")
        time.sleep(0.05)
    OUT.write_text(
        json.dumps(
            {
                "pending": len(pending),
                "by_magic": dict(by_magic),
                "suspects": rows,
                "suspect_n": len(rows),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"pending={len(pending)} magic={dict(by_magic)} suspects={len(rows)} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
