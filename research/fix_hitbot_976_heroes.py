"""Replace Hitbot (976) illustration/wrong-brand heroes with OEM product renders.

Current failures:
- nav/*.png line icons (1522/1632/2140/6140)
- */drawing.jpg dimensional CAD sheets (1832/2442)
- S922.png is a HIWIN-branded arm (wrong OEM)
- 2442.png / some banners show HIRATA/HIWIN marks

Replacement heroes are official en.hitbot.cc product renders with HITBOT branding.
Leaves status unchanged (pending_review / published).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from PIL import Image

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 976
COMPANY_SLUG = "hitbot-technology-shenzhen-co-ltd"
COMPANY_NAME = "Hitbot Technology (Shenzhen) Co.  Ltd"
REPORT = _HERE / "staging" / "reports" / "hitbot-976-hero-fix.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://en.hitbot.cc/",
}
LIST_URL = "https://en.hitbot.cc/z-arm.html"

# Official HITBOT-branded product renders (not nav icons, not drawings,
# not HIWIN/HIRATA-contaminated assets).
HEROES: dict[int, dict[str, Any]] = {
    5282: {
        "name": "Z-Arm 1522",
        "image": "https://en.hitbot.cc/assets/images/Z-Arm/1522.png",
        "url": LIST_URL,  # model PDP 404s
        "family_key": "hitbot:z-arm",
        "family_name": "Z-Arm",
        "family_url": LIST_URL,
        "model_name": "1522",
        "variant_code": "1522",
        "product_url_scope": "family",
        "note": "Replaced nav line-icon with official HITBOT 1522 product render.",
    },
    5283: {
        "name": "Z-Arm 1632",
        "image": "https://en.hitbot.cc/assets/images/Z-Arm/1632.png",
        "url": LIST_URL,
        "family_key": "hitbot:z-arm",
        "family_name": "Z-Arm",
        "family_url": LIST_URL,
        "model_name": "1632",
        "variant_code": "1632",
        "product_url_scope": "family",
        "note": "Replaced nav line-icon with official HITBOT 1632 product render.",
    },
    5284: {
        "name": "Z-Arm 1832",
        "image": "https://en.hitbot.cc/assets/images/Z-Arm/1832/small.jpg",
        "url": "https://en.hitbot.cc/Z-Arm/1832.html",
        "family_key": "hitbot:z-arm",
        "family_name": "Z-Arm",
        "family_url": LIST_URL,
        "model_name": "1832",
        "variant_code": "1832",
        "product_url_scope": "exact_variant",
        "note": "Replaced dimensional drawing.jpg with HITBOT-labeled 1832 product render.",
    },
    5285: {
        "name": "Z-Arm 2140",
        "image": "https://en.hitbot.cc/assets/images/Z-Arm/2140.png",
        "url": LIST_URL,
        "family_key": "hitbot:z-arm",
        "family_name": "Z-Arm",
        "family_url": LIST_URL,
        "model_name": "2140",
        "variant_code": "2140",
        "product_url_scope": "family",
        "note": "Replaced nav line-icon with official HITBOT 2140 product render.",
    },
    5286: {
        "name": "Z-Arm 2442",
        "image": "https://en.hitbot.cc/assets/images/Z-Arm/2442/small.jpg",
        "url": "https://en.hitbot.cc/Z-Arm/2442.html",
        "family_key": "hitbot:z-arm",
        "family_name": "Z-Arm",
        "family_url": LIST_URL,
        "model_name": "2442",
        "variant_code": "2442",
        "product_url_scope": "exact_variant",
        "note": (
            "Replaced dimensional drawing.jpg; avoided 2442.png/banner assets "
            "that carry HIRATA/HIWIN marks."
        ),
    },
    5287: {
        "name": "Z-Arm 6140",
        "image": "https://en.hitbot.cc/assets/images/Z-Arm/6140.png",
        "url": LIST_URL,
        "family_key": "hitbot:z-arm",
        "family_name": "Z-Arm",
        "family_url": LIST_URL,
        "model_name": "6140",
        "variant_code": "6140",
        "product_url_scope": "family",
        "note": "Replaced nav line-icon with official 6140 product render.",
    },
    5288: {
        "name": "Z-Arm S922",
        "image": "https://en.hitbot.cc/assets/images/Z-Arm/S922/small.jpg",
        "url": "https://en.hitbot.cc/Z-Arm/S922.html",
        "family_key": "hitbot:z-arm-s",
        "family_name": "Z-Arm S",
        "family_url": LIST_URL,
        "model_name": "S922",
        "variant_code": "S922",
        "product_url_scope": "exact_variant",
        "note": (
            "Replaced S922.png which depicted a HIWIN-branded 6-axis arm with "
            "HITBOT-labeled S922 product render."
        ),
        "allow_published": True,
    },
}


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace(
        "/api/v1", ""
    )


def _internal_headers() -> dict[str, str]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        raise RuntimeError("INTERNAL_API_SECRET missing")
    return {"X-Internal-Secret": secret}


def fetch_bytes(url: str) -> bytes:
    resp = requests.get(url, headers=HEADERS, timeout=90)
    resp.raise_for_status()
    if len(resp.content) < 8_000:
        raise RuntimeError(f"image too small ({len(resp.content)}b): {url}")
    magic = resp.content[:4]
    if not (
        resp.content[:3] == b"\xff\xd8\xff"
        or magic == b"\x89PNG"
        or magic == b"RIFF"
    ):
        raise RuntimeError(f"non-image magic {magic.hex()}: {url}")
    return resp.content


def preflight_heroes() -> dict[str, Any]:
    hashes: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for rid, data in HEROES.items():
        content = fetch_bytes(data["image"])
        digest = hashlib.sha256(content).hexdigest()
        if digest in hashes:
            raise RuntimeError(
                f"hero hash collision {rid} vs {hashes[digest]}: {data['image']}"
            )
        hashes[digest] = rid
        image = Image.open(io.BytesIO(content))
        rows.append(
            {
                "id": rid,
                "name": data["name"],
                "url": data["image"],
                "bytes": len(content),
                "sha256": digest,
                "size": list(image.size),
            }
        )
    return {"heroes": rows, "unique_hashes": len(hashes)}


def import_row(rid: int, data: dict[str, Any], *, status: str) -> dict[str, Any]:
    detail = ResearchApiClient()._get(f"robots/robots/{rid}/")
    notes = str(detail.get("notes") or "")
    marker = f"[HERO FIX 2026-07-22] {data['note']}"
    if marker not in notes:
        notes = f"{marker}\n{notes}".strip()
    row = {
        "id": rid,
        "name": data["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "url": data["url"],
        "image": data["image"],
        "images": [data["image"]],
        "s3_image": None,
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": data["family_url"],
        "model_name": data["model_name"],
        "variant_code": data["variant_code"],
        "product_url_scope": data["product_url_scope"],
        "notes": notes,
        "manufacturer_country_code": "CN",
        "manufacturer_country_codes": "CN",
    }
    client = ResearchApiClient()
    result = client.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        status=status,
        skip_company_update=True,
        replace_media=True,
    )
    # Re-assert family + url + clear stale owned CDN pointer before copy-media.
    client._patch(
        f"robots/robots/{rid}/",
        {
            "url": data["url"],
            "image": data["image"],
            "s3_image": None,
            "family_key": data["family_key"],
            "family_name": data["family_name"],
            "family_url": data["family_url"],
            "model_name": data["model_name"],
            "variant_code": data["variant_code"],
            "product_url_scope": data["product_url_scope"],
            "notes": notes,
            "status": status,
        },
    )
    return result


def copy_media(rid: int) -> dict[str, Any]:
    response = requests.post(
        f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/"
        f"{rid}/copy-media/?force=1",
        headers=_internal_headers(),
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def verify(client: ResearchApiClient) -> dict[str, Any]:
    hashes: dict[str, int] = {}
    media: list[dict[str, Any]] = []
    for rid, data in HEROES.items():
        robot = client._get(f"robots/robots/{rid}/")
        url = str(robot.get("s3_image") or robot.get("image") or "")
        if "cdn.robotaigeek.com" not in url:
            raise RuntimeError(f"{rid} missing owned CDN: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=90)
        if resp.status_code != 200 or len(resp.content) < 8_000:
            raise RuntimeError(
                f"{rid} CDN bad: {resp.status_code} {len(resp.content)}b"
            )
        magic = resp.content[:4]
        if not (
            resp.content[:3] == b"\xff\xd8\xff"
            or magic == b"\x89PNG"
            or magic == b"RIFF"
        ):
            raise RuntimeError(f"{rid} non-image magic {magic.hex()}")
        digest = hashlib.sha256(resp.content).hexdigest()
        if digest in hashes:
            raise RuntimeError(f"{rid} CDN hash collides with {hashes[digest]}")
        hashes[digest] = rid
        # Reject known-bad HIWIN S922 asset if it somehow returned
        if digest.startswith("5aba11e102"):
            raise RuntimeError(f"{rid} still has HIWIN S922.png hash")
        image = Image.open(io.BytesIO(resp.content))
        media.append(
            {
                "id": rid,
                "name": robot.get("name"),
                "status": robot.get("status"),
                "cdn": url,
                "bytes": len(resp.content),
                "size": list(image.size),
                "sha256": digest,
                "family_key": robot.get("family_key"),
                "source_image": data["image"],
            }
        )
    return {"ok": True, "media": media, "unique_hashes": len(hashes)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    live = {int(r["id"]): r for r in client.list_robots_for_company(COMPANY_ID)}
    missing = sorted(set(HEROES) - set(live))
    if missing:
        raise RuntimeError(f"missing robots: {missing}")

    preflight = preflight_heroes()
    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "mode": "apply" if args.apply else "dry-run",
        "preflight": preflight,
        "targets": {
            rid: {
                "name": data["name"],
                "image": data["image"],
                "url": data["url"],
                "live_status": live[rid].get("status"),
                "live_primary": live[rid].get("s3_image") or live[rid].get("image"),
            }
            for rid, data in HEROES.items()
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if not args.apply:
        REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    results: dict[int, Any] = {}
    copies: dict[int, Any] = {}
    for rid, data in HEROES.items():
        status = str(live[rid].get("status") or "pending_review")
        if status == "published" and not data.get("allow_published"):
            raise RuntimeError(f"refusing to overwrite published {rid}")
        print(f"import {rid} {data['name']} status={status}...", flush=True)
        results[rid] = import_row(rid, data, status=status)
        if results[rid].get("error_count"):
            raise RuntimeError(f"import failed {rid}: {results[rid]}")
        print(f"copy-media {rid}...", flush=True)
        copies[rid] = copy_media(rid)

    verified = verify(client)
    report.update(
        {
            "applied": True,
            "import_results": results,
            "copy_media": copies,
            "verified": verified,
        }
    )
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"verified": verified}, indent=2, ensure_ascii=False))
    print(
        f"apply OK: {len(HEROES)} heroes replaced, "
        f"{verified['unique_hashes']} distinct CDN hashes",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
