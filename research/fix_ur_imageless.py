"""Attach chased OEM heroes to the 5 imageless Universal Robots rows.

Visual QA (2026-07-19):
  UR5e  -> Storyblok ur5e-4-backgroundwarm50 (full-arm studio render)
  UR10e -> Storyblok ur10e-4x3 (full-arm studio render)
  UR3   -> OEM /media/1802342/ur3.png
  UR5   -> OEM /media/1802344/ur5.png
  UR10  -> OEM /media/1802346/ur10.png

Rejected: payload curves, footprint graphics, people/case-study shots,
UR10e joint close-up, MyUR UI art.

Usage:
  python fix_ur_imageless.py            # dry-run
  python fix_ur_imageless.py --apply --copy-media
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from fix_universal_robots import _internal_secret, copy_media

# id -> (model, hero_url)
TARGETS: dict[int, tuple[str, str]] = {
    2535: (
        "UR5e",
        "https://a.storyblok.com/f/169662/5873x4405/3a94f66de5/ur5e-4-backgroundwarm50.png",
    ),
    3543: (
        "UR10e",
        "https://a.storyblok.com/f/169662/5873x4405/a77477d600/ur10e-4x3.png",
    ),
    4882: (
        "UR3",
        "https://www.universal-robots.com/media/1802342/ur3.png",
    ),
    4883: (
        "UR5",
        "https://www.universal-robots.com/media/1802344/ur5.png",
    ),
    3544: (
        "UR10",
        "https://www.universal-robots.com/media/1802346/ur10.png",
    ),
}


def _strip_image_todo(notes: str) -> str:
    text = (notes or "").strip()
    if "[IMAGE TO-DO" not in text:
        return text
    # drop first IMAGE TO-DO block through ---
    parts = text.split("---", 1)
    head = parts[0]
    if "[IMAGE TO-DO" in head:
        rest = parts[1].strip() if len(parts) > 1 else ""
        return rest
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    args = ap.parse_args()

    # download + hash gate
    blobs: dict[int, tuple[str, bytes, str]] = {}
    hashes: dict[str, int] = {}
    for rid, (model, url) in TARGETS.items():
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        data = r.content
        if data[:8] != b"\x89PNG\r\n\x1a\n" and data[:3] != b"\xff\xd8\xff":
            print(f"FAIL {rid} {model}: not an image")
            return 1
        if len(data) < 20000:
            print(f"FAIL {rid} {model}: too small ({len(data)})")
            return 1
        h = hashlib.md5(data).hexdigest()
        if h in hashes:
            print(f"FAIL hash collision {rid} vs {hashes[h]}")
            return 1
        hashes[h] = rid
        blobs[rid] = (model, data, url)
        print(f"OK {rid} {model} bytes={len(data)} md5={h}")
        print(f"   {url}")

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    client = ResearchApiClient()
    secret = _internal_secret() if args.copy_media else ""
    ok = fail = 0
    for rid, (model, _data, url) in blobs.items():
        try:
            full = client._get(f"robots/robots/{rid}/")
            notes = _strip_image_todo(full.get("notes") or "")
            body: dict[str, Any] = {
                "image": url,
                "images": [url],
                "product_url_scope": (
                    "family" if model in {"UR5e", "UR10e", "UR3", "UR5", "UR10"} else "exact_variant"
                ),
            }
            if notes:
                body["notes"] = notes
            else:
                # clear leftover todo if any via empty? leave as-is if already empty after strip
                if full.get("notes") and "[IMAGE TO-DO" in (full.get("notes") or ""):
                    body["notes"] = notes  # may be ""
            patched = client._patch(f"robots/robots/{rid}/", body)
            cm = ""
            if args.copy_media and secret:
                for attempt in range(1, 5):
                    cm = copy_media(rid, secret)
                    if cm == "ok":
                        break
                    time.sleep(2 * attempt)
            img = (patched.get("image") or "")[:70]
            print(f"ok {rid} {model} img={img} copy={cm or '-'}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {rid}: {exc}")
            fail += 1
        time.sleep(0.15)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
