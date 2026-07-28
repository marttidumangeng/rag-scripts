"""Batch-regenerate missing image variants for published robots from the audit report.

Usage:
  python repair_missing_variants_batch.py
  python repair_missing_variants_batch.py --ids 17 23 27
  python repair_missing_variants_batch.py --limit 5
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
ROOT = _RESEARCH_DIR.parents[1]  # repo root (…/robot-ai-geek)
SERVER = ROOT / "robotaigeek-server"
sys.path.insert(0, str(SERVER))
sys.path.insert(0, str(_RESEARCH_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from load_env import load_research_env

load_research_env()


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        # Always prefer server .env for AWS credentials / region.
        if k.startswith("AWS_") or k not in os.environ or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


_load_dotenv(SERVER / ".env")
# Prod CDN bucket — do not use the local-dev bucket from .env
os.environ["AWS_STORAGE_BUCKET_NAME"] = "cdn.robotaigeek.com"

import django

django.setup()

import boto3
from PIL import Image, ImageOps
from common.image_variants import get_variant_key, _parse_widths
from api_client import ResearchApiClient

OWNED_HOSTS = ("cdn.robotaigeek.com", "cdn-dev.robotaigeek.com")
BUCKET = "cdn.robotaigeek.com"
WIDTHS = _parse_widths()
REPORT_DEFAULT = _RESEARCH_DIR / "staging" / "reports" / "missing-variants-published.json"


def _is_owned(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    return any(host == h or host.endswith("." + h) for h in OWNED_HOSTS)


def _url_to_key(url: str) -> str:
    return (urlparse(url).path or "").lstrip("/")


def _head_ok(url: str, timeout: float = 20.0) -> bool:
    try:
        r = urlopen(Request(url, method="HEAD"), timeout=timeout)
        return int(getattr(r, "status", 200) or 200) < 400
    except HTTPError as e:
        if e.code in (403, 404):
            return False
        # Some CDNs reject HEAD
        try:
            r = urlopen(Request(url, headers={"Range": "bytes=0-64"}), timeout=timeout)
            return True
        except Exception:
            return False
    except Exception:
        return False


def _collect_source_keys(robot: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        if not url or not _is_owned(url):
            return
        key = _url_to_key(url)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)

    add((robot.get("s3_image") or robot.get("image") or "").strip())
    for p in robot.get("photos") or []:
        if not isinstance(p, dict):
            continue
        add((p.get("s3_image") or p.get("url") or "").strip())
    return keys


def _needs_variants(key: str) -> bool:
    """True when the representative 640w variants are missing."""
    jpg = f"https://cdn.robotaigeek.com/{get_variant_key(key, 640, ext_override='.jpg')}"
    webp = f"https://cdn.robotaigeek.com/{get_variant_key(key, 640, ext_override='.webp')}"
    return not (_head_ok(jpg) or _head_ok(webp))


def _generate_for_key(client, key: str, missing: list[int]) -> tuple[int, list[str]]:
    url = f"https://cdn.robotaigeek.com/{key}"
    errors: list[str] = []
    try:
        raw = urlopen(url, timeout=90).read()
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    except Exception as e:
        return 0, [f"{key}: open failed — {e}"]

    generated = 0
    for width in missing:
        try:
            if width < image.width:
                ratio = width / float(image.width)
                resized = image.resize(
                    (width, max(1, int(image.height * ratio))), Image.LANCZOS
                )
            else:
                resized = image.copy()

            key_jpg = get_variant_key(key, width, ext_override=".jpg")
            key_webp = get_variant_key(key, width, ext_override=".webp")

            out_jpg = io.BytesIO()
            rgb = resized if resized.mode in ("RGB", "L") else resized.convert("RGB")
            rgb.save(out_jpg, format="JPEG", quality=85, optimize=True, progressive=True)
            client.put_object(
                Bucket=BUCKET,
                Key=key_jpg,
                Body=out_jpg.getvalue(),
                ContentType="image/jpeg",
                CacheControl="public, max-age=31536000",
            )

            out_webp = io.BytesIO()
            webp = (
                resized if resized.mode in ("RGB", "RGBA", "L") else resized.convert("RGB")
            )
            webp.save(out_webp, format="WEBP", quality=82, method=6)
            client.put_object(
                Bucket=BUCKET,
                Key=key_webp,
                Body=out_webp.getvalue(),
                ContentType="image/webp",
                CacheControl="public, max-age=31536000",
            )
            generated += 1
        except Exception as e:
            errors.append(f"{key} {width}w: {e}")
    return generated, errors


def _fetch_robot(api: ResearchApiClient, rid: int) -> dict[str, Any] | None:
    for attempt in range(5):
        try:
            return api._get(f"robots/robots/{rid}/")
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    ap.add_argument(
        "--json-out",
        type=Path,
        default=_RESEARCH_DIR / "staging" / "reports" / "missing-variants-repair-result.json",
    )
    args = ap.parse_args()

    if args.ids:
        ids = list(args.ids)
    else:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        ids = [int(r["robot_id"]) for r in report.get("robots") or []]
    if args.limit:
        ids = ids[: args.limit]

    if not ids:
        print("No robot ids to repair", file=sys.stderr)
        return 2

    region = os.environ.get("AWS_S3_REGION_NAME", "ap-southeast-1")
    s3 = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    api = ResearchApiClient()

    results: list[dict[str, Any]] = []
    total_gen = 0
    total_err = 0
    print(f"Repairing variants for {len(ids)} robot(s)…", flush=True)

    for i, rid in enumerate(ids, 1):
        robot = _fetch_robot(api, rid)
        if not robot:
            print(f"[{i}/{len(ids)}] #{rid} FETCH FAILED", flush=True)
            results.append({"robot_id": rid, "ok": False, "error": "fetch failed"})
            total_err += 1
            continue

        name = robot.get("name") or ""
        keys = _collect_source_keys(robot)
        if not keys:
            print(f"[{i}/{len(ids)}] #{rid} {name!r} no owned sources", flush=True)
            results.append({"robot_id": rid, "name": name, "ok": True, "skipped": True})
            continue

        robot_gen = 0
        robot_err: list[str] = []
        sources_fixed = 0
        for key in keys:
            if not _head_ok(f"https://cdn.robotaigeek.com/{key}"):
                robot_err.append(f"{key}: original missing")
                continue
            if not _needs_variants(key):
                continue
            gen, errs = _generate_for_key(s3, key, list(WIDTHS))
            robot_gen += gen
            robot_err.extend(errs)
            if gen:
                sources_fixed += 1

        # Verify primary 640 webp after repair
        primary = keys[0]
        v640 = get_variant_key(primary, 640, ext_override=".webp")
        verified = _head_ok(f"https://cdn.robotaigeek.com/{v640}")
        ok = verified and not robot_err
        total_gen += robot_gen
        total_err += len(robot_err)
        status = "OK" if ok else ("PARTIAL" if robot_gen else "FAIL")
        safe_name = (name or "").encode("ascii", "replace").decode("ascii")
        print(
            f"[{i}/{len(ids)}] #{rid} {safe_name!r} {status} "
            f"sources={len(keys)} fixed={sources_fixed} gen={robot_gen} err={len(robot_err)}",
            flush=True,
        )
        if robot_err:
            for e in robot_err[:3]:
                print(f"    ! {e.encode('ascii', 'replace').decode('ascii')}", flush=True)
        results.append({
            "robot_id": rid,
            "name": name,
            "ok": ok,
            "sources": len(keys),
            "sources_fixed": sources_fixed,
            "generated_width_sets": robot_gen,
            "errors": robot_err[:10],
            "verified_primary_w640": verified,
        })

    summary = {
        "robots": len(ids),
        "ok": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok") and not r.get("skipped")),
        "generated_width_sets": total_gen,
        "error_count": total_err,
        "results": results,
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        f"\nDone. ok={summary['ok']} failed={summary['failed']} "
        f"generated_width_sets={total_gen} report={args.json_out}",
        flush=True,
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
