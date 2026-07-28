"""Restore Briggo (406) and Formic (1450) heroes from current OEM pages.

Usage:
  python fix_briggo_formic_images.py
  python fix_briggo_formic_images.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

SERVER = _RESEARCH.parents[1] / "robotaigeek-server"

HEROES = {
    4419: (
        "https://cdn.sanity.io/images/w82rk2si/production/"
        "535214333afd1c3fd629ae2fc169578c50f778eb-512x696.webp"
        "?w=640&fit=max&auto=format"
    ),
    5168: "https://formic.co/Formic-Humanoid.webp",
    5167: "https://formic.co/Formic-KUKA-Machine-Tending.webp",
    5166: "https://formic.co/Formic-F50-Palletizer.jpg",
    2874: "https://formic.co/AMR-Reach-Truck.jpg",
    2872: "https://formic.co/Formic-Pallet-Wrap-Product.jpg",
    2870: "https://formic.co/Formic-Talos-Casepacker.jpg",
    2868: "https://formic.co/Formic-Casepacker-Plant.jpg",
    2867: "https://formic.co/Cameron-Cobot-Palletizing.jpg",
}

IMAGE_TODO_RE = re.compile(
    r"\n?\[IMAGE TO-DO — no hero, deliberate\].*?(?:\n---\n?|\Z)",
    flags=re.DOTALL,
)


def validate_sources(
    heroes: dict[int, str],
) -> dict[int, dict[str, Any]]:
    """Download candidate bytes, validate image magic, and reject duplicates."""
    results: dict[int, dict[str, Any]] = {}
    seen_hashes: dict[str, int] = {}
    for rid, url in heroes.items():
        response = None
        for attempt in range(3):
            try:
                response = requests.get(
                    url,
                    timeout=180,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
                        ),
                        "Referer": f"https://{url.split('/', 3)[2]}/",
                    },
                )
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(3 + attempt * 2)
        if response is None:
            raise RuntimeError(f"No response for robot {rid}")
        data = response.content
        magic_ok = data.startswith(
            (b"\xff\xd8", b"\x89PNG\r\n\x1a\n", b"GIF8", b"RIFF")
        )
        if not magic_ok or len(data) < 10_000:
            raise RuntimeError(
                f"Invalid or undersized image for robot {rid}: {len(data)} bytes"
            )
        digest = f"md5:{hashlib.md5(data).hexdigest()}"  # noqa: S324 - dedupe only
        if digest in seen_hashes:
            raise RuntimeError(
                f"Duplicate image bytes for robots {seen_hashes[digest]} and {rid}"
            )
        seen_hashes[digest] = rid
        results[rid] = {"url": url, "bytes": len(data), "md5": digest}
        print(f"source OK {rid}: {len(data)} bytes md5={digest}")
    return results


def internal_secret() -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    if not secret:
        raise RuntimeError("INTERNAL_API_SECRET is unavailable")
    return secret


def copy_media(rid: int, secret: str) -> None:
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "")
        .rstrip("/")
        .replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = (
        f"{api}/admin/robots/robot/content-queue/api/robot/"
        f"{rid}/copy-media/?force=1"
    )
    response = requests.post(
        url,
        headers={"X-Internal-Secret": secret},
        timeout=180,
    )
    response.raise_for_status()
    print(f"copy-media OK {rid}: {(response.text or '')[:100]}")


def cleaned_notes(existing: dict[str, Any], source_url: str) -> str:
    notes = IMAGE_TODO_RE.sub("", existing.get("notes") or "").strip()
    media_note = (
        "[AI Research] Hero restored 2026-07-21 from the model-specific OEM "
        f"product page asset: {source_url}"
    )
    if media_note not in notes:
        notes = f"{notes}\n{media_note}".strip()
    return notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ids", type=int, nargs="*")
    args = parser.parse_args()

    wanted = set(args.ids or HEROES)
    unknown = wanted.difference(HEROES)
    if unknown:
        parser.error(f"Unknown robot IDs: {sorted(unknown)}")
    heroes = {rid: url for rid, url in HEROES.items() if rid in wanted}

    validate_sources(heroes)
    if not args.apply:
        print(f"Dry run: {len(heroes)} distinct OEM heroes validated")
        return 0

    client = ResearchApiClient()
    secret = internal_secret()
    for rid, source_url in heroes.items():
        existing = client._get(f"robots/robots/{rid}/")
        client._patch(
            f"robots/robots/{rid}/",
            {
                "image": source_url,
                "images": [source_url],
                "notes": cleaned_notes(existing, source_url),
                "status": "pending_review",
            },
        )
        print(f"patch image OK {rid}")
        copy_media(rid, secret)

    print(f"Applied {len(heroes)} hero repairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
