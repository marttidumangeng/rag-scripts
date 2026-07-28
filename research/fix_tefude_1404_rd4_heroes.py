"""Rebuild 4 distinct robot-dominant TFD-RD4 heroes and re-attach to keepers."""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.tefude.com/",
}
OUT = Path(__file__).resolve().parent / "staging" / "reports" / "tefude-1404-rd4-fix"
CAND = Path(__file__).resolve().parent / "staging" / "reports" / "tefude-1404-rd4-candidates"
OUT.mkdir(parents=True, exist_ok=True)

# Keeper order: 600A, 800A, 1200A, 1600A
KEEP_RD4 = [2503, 1972, 2504, 1973]

OEM_CELL = "https://www.tefude.com/uploads/43607/delta-robotic-armcf0c3.jpg"
OEM_CELL2 = "https://www.tefude.com/uploads/43607/4-axis-robotic-armd5003.jpg"


def _pad_square(crop: Image.Image, fill=(245, 250, 255)) -> Image.Image:
    side = max(crop.size)
    canvas = Image.new("RGB", (side, side), fill)
    canvas.paste(crop, ((side - crop.size[0]) // 2, (side - crop.size[1]) // 2))
    return canvas


def _save_jpeg(img: Image.Image, path: Path, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    data = buf.getvalue()
    path.write_bytes(data)
    return data


def _upscale_min(img: Image.Image, min_side: int = 800) -> Image.Image:
    w, h = img.size
    side = max(w, h)
    if side >= min_side:
        return img
    scale = min_side / side
    return img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)


def build_heroes() -> list[dict[str, Any]]:
    detail = Image.open(CAND / "cand_007_715b839f.jpg").convert("RGB")
    w, h = detail.size
    # Left perspective (robot-dominant, TEFUDE on housing)
    left = _pad_square(detail.crop((0, int(h * 0.12), int(w * 0.58), h)))
    # Top-down inset (bottom-right of DETAIL DISPLAY), upscaled
    top = _upscale_min(
        _pad_square(detail.crop((int(w * 0.42), int(h * 0.38), w, h)))
    )

    cell_src = Image.open(CAND / "cand_009_0144e75a.jpg").convert("RGB")
    ww, hh = cell_src.size
    cell = _pad_square(
        cell_src.crop((int(ww * 0.12), int(hh * 0.05), int(ww * 0.88), int(hh * 0.78))),
        fill=(240, 245, 250),
    )

    # Second DETAIL DISPLAY source — crop below header text, favor left robot
    detail_b = Image.open(CAND / "cand_010_40dcbd6f.jpg").convert("RGB")
    wb, hb = detail_b.size
    left_b = _pad_square(
        detail_b.crop((0, int(hb * 0.18), int(wb * 0.60), int(hb * 0.98)))
    )

    paths = [
        OUT / "hero_rd4_600a_detail.jpg",
        OUT / "hero_rd4_800a_topdown.jpg",
        OUT / "hero_rd4_1200a_cell.jpg",
        OUT / "hero_rd4_1600a_detail_b.jpg",
    ]
    images = [left, top, cell, left_b]
    rows = []
    hashes: set[str] = set()
    for rid, path, img in zip(KEEP_RD4, paths, images, strict=True):
        data = _save_jpeg(img, path)
        digest = hashlib.md5(data).hexdigest()
        if digest in hashes:
            raise RuntimeError(f"hero hash collision for {rid}")
        hashes.add(digest)
        rows.append(
            {
                "id": rid,
                "path": str(path),
                "md5": digest,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "size": list(img.size),
            }
        )
        print(f"built {rid} {img.size} {len(data)}b {digest}")
    return rows


def upload_primary(client: ResearchApiClient, rid: int, path: Path) -> str:
    headers = {
        key: value
        for key, value in client._session.headers.items()
        if key.lower() != "content-type"
    }
    with path.open("rb") as handle:
        response = requests.post(
            client._url(f"robots/robots/{rid}/images/"),
            headers=headers,
            files={"images": (path.name, handle, "image/jpeg")},
            data={
                "title": path.stem,
                "description": (
                    "TEFUDE TFD-RD4 official product visual — robot-dominant "
                    "(cropped DETAIL DISPLAY / OEM cell; no packing-line banner text)."
                ),
            },
            timeout=120,
        )
    response.raise_for_status()
    data = response.json()
    photos = data.get("photos") or [data.get("photo") or {}]
    url = str((photos[0] or {}).get("url") or "")
    if not url:
        raise RuntimeError(f"{rid} upload returned no URL: {data}")
    # Force primary via patch clearing sticky s3 then setting image
    client._patch(
        f"robots/robots/{rid}/",
        {
            "image": url,
            "images": [url],
            "s3_image": None,
            "status": "pending_review",
        },
    )
    return url


def copy_media(rid: int) -> dict[str, Any]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        raise RuntimeError("INTERNAL_API_SECRET missing")
    base = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace(
        "/api/v1", ""
    )
    response = requests.post(
        f"{base}/admin/robots/robot/content-queue/api/robot/"
        f"{rid}/copy-media/?force=1",
        headers={"X-Internal-Secret": secret},
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def verify(client: ResearchApiClient) -> dict[str, Any]:
    hashes: dict[str, int] = {}
    media = []
    issues = []
    for rid in KEEP_RD4:
        robot = client._get(f"robots/robots/{rid}/")
        url = str(robot.get("s3_image") or robot.get("image") or "")
        if "cdn.robotaigeek.com" not in url:
            issues.append(f"{rid} not owned CDN: {url}")
            continue
        resp = requests.get(url, headers=HEADERS, timeout=90)
        if resp.status_code != 200 or len(resp.content) < 8000:
            issues.append(f"{rid} CDN bad")
            continue
        digest = hashlib.sha256(resp.content).hexdigest()
        md5 = hashlib.md5(resp.content).hexdigest()
        if md5 == "728e8af02af165f75a8bce8a57a8c889":
            issues.append(f"{rid} shared banner")
        if digest in hashes:
            issues.append(f"{rid} collides {hashes[digest]}")
        hashes[digest] = rid
        img = Image.open(io.BytesIO(resp.content))
        media.append(
            {
                "id": rid,
                "cdn": url,
                "size": list(img.size),
                "sha256": digest,
                "md5": md5,
            }
        )
        # Persist for visual QA
        (OUT / f"cdn_{rid}.jpg").write_bytes(resp.content)
    return {
        "ok": not issues,
        "issues": issues,
        "media": media,
        "unique": len(hashes),
    }


def main() -> int:
    apply = "--apply" in sys.argv
    heroes = build_heroes()
    report = {"mode": "apply" if apply else "dry-run", "heroes": heroes}
    if not apply:
        print(json.dumps(report, indent=2))
        return 0

    client = ResearchApiClient()
    uploads = {}
    copies = {}
    for row in heroes:
        rid = row["id"]
        path = Path(row["path"])
        print(f"upload {rid}...", flush=True)
        uploads[rid] = upload_primary(client, rid, path)
        print(f"copy-media {rid}...", flush=True)
        copies[rid] = copy_media(rid)
    verified = verify(client)
    report.update({"uploads": uploads, "copies": copies, "verify": verified})
    (OUT / "rd4-hero-fix-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({"verify": verified}, indent=2))
    if not verified["ok"]:
        raise SystemExit(f"verify failed: {verified['issues']}")
    print(f"RD4 hero fix OK: {verified['unique']}/4 distinct CDN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
