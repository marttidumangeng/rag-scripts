"""Remove Yamaha LCMR200 catalog-derived images that lack reuse permission.

The exact Yamaha PDF and CADENAS renders are useful for model identification,
but their terms do not permit republication on a public commercial catalog.
This script fails closed: it removes only known uploaded files, preserves
``pending_review``, and records an actionable image note.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

COMPANY_ID = 1484
REPORT = _HERE / "staging" / "reports" / "yamaha-lcmr200-image-rights-cleanup.json"

CADENAS_TERMS_URL = "https://www.cadenas.de/en/legal/partcommunity-b2b/terms-of-use"
YAMAHA_COPYRIGHT_URL = "https://global.yamaha-motor.com/copyright/"

# Deliberately empty. Exactness does not override republication rights.
EXACT_TARGETS: dict[int, dict[str, Any]] = {}

RESTRICTED_MEDIA: dict[int, dict[str, str]] = {
    3325: {"model": "LCMR200-F2", "filename": "lcmr200-f2-exact-cad-render.png"},
    3326: {"model": "LCMR200-B3", "filename": "lcmr200-b3-exact-cad-render.png"},
    4385: {
        "model": "LCMR200-XBOT",
        "filename": "lcmr200-xbot-exact-clean-render.png",
    },
    4386: {"model": "LCMR200-F3", "filename": "lcmr200-f3-exact-cad-render.png"},
    4387: {"model": "LCMR200-F5", "filename": "lcmr200-f5-exact-cad-render.png"},
    4388: {"model": "LCMR200-F10", "filename": "lcmr200-f10-exact-cad-render.png"},
    4389: {"model": "LCMR200-B2", "filename": "lcmr200-b2-exact-cad-render.png"},
    4390: {"model": "LCMR200-B5", "filename": "lcmr200-b5-exact-cad-render.png"},
    4391: {"model": "LCMR200-B10", "filename": "lcmr200-b10-exact-cad-render.png"},
    4392: {
        "model": "LCMR200-JGX16-H",
        "filename": "lcmr200-jgx16-h-exact-clean-render.png",
    },
    4393: {
        "model": "LCMR200-JGX16-V",
        "filename": "lcmr200-jgx16-v-exact-clean-render.png",
    },
}
HELD_NO_EXACT_IMAGE_IDS = set(RESTRICTED_MEDIA)

IMAGE_TODO = """[IMAGE TO-DO — no hero, deliberate]
Removed the exact catalog-derived render because Yamaha/CADENAS terms do not permit public redistribution.
No exact variant-labeled photo with a reusable license was found after checking Yamaha, distributors, publishers, case studies, and user installations.
ACTION FOR TEAM: Obtain written republication permission from Yamaha/CADENAS or a licensed exact-model photograph.
Do NOT substitute a sibling render, family banner, catalog crop, CAD render, or dimensional drawing.
---"""


def is_restricted_media_url(robot_id: int, url: str | None) -> bool:
    target = RESTRICTED_MEDIA.get(robot_id)
    if not target or not url:
        return False
    return urlparse(str(url)).path.rstrip("/").endswith(f"/{target['filename']}")


def restricted_cad_cleanup_payload(
    robot_id: int,
    existing_notes: str | None,
) -> dict[str, Any]:
    if robot_id not in RESTRICTED_MEDIA:
        raise ValueError(f"{robot_id}: not a Yamaha restricted-media target")
    notes = (existing_notes or "").strip()
    if not notes.startswith("[IMAGE TO-DO — no hero, deliberate]"):
        notes = f"{IMAGE_TODO}\n{notes}".rstrip()
    return {
        "image": "",
        "images": [],
        "s3_image": None,
        "status": "pending_review",
        "notes": notes,
    }


def _admin_credentials() -> tuple[str, str]:
    api_base = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "")
        .rstrip("/")
        .removesuffix("/api/v1")
    )
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not api_base or not secret:
        raise RuntimeError("Production admin base URL and INTERNAL_API_SECRET are required")
    return api_base, secret


def _s3_key(url: str) -> str:
    key = urlparse(url).path.lstrip("/")
    if not key.startswith("robots/photos/"):
        raise RuntimeError(f"Refusing to delete unexpected S3 key: {key}")
    return key


def _delete_s3_objects(urls: set[str]) -> list[str]:
    import boto3
    from botocore.config import Config

    bucket = os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip()
    if not bucket:
        raise RuntimeError("AWS_STORAGE_BUCKET_NAME is required")
    client = boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        config=Config(
            retries={"total_max_attempts": 3, "mode": "adaptive"},
            connect_timeout=10,
            read_timeout=30,
        ),
    )
    deleted: list[str] = []
    for url in sorted(urls):
        key = _s3_key(url)
        client.delete_object(Bucket=bucket, Key=key)
        client.get_waiter("object_not_exists").wait(
            Bucket=bucket,
            Key=key,
            WaiterConfig={"Delay": 1, "MaxAttempts": 10},
        )
        deleted.append(key)
    return deleted


def cleanup_restricted_media(
    client: ResearchApiClient,
    *,
    apply: bool,
    detach_only: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "mode": "apply" if apply else "dry-run",
        "rights_sources": [CADENAS_TERMS_URL, YAMAHA_COPYRIGHT_URL],
        "targets": [],
        "cleaned": [],
        "skipped": [],
        "warnings": [],
        "errors": [],
    }
    api_base = secret = ""
    if apply:
        api_base, secret = _admin_credentials()

    for robot_id, target in RESTRICTED_MEDIA.items():
        try:
            current = client._get(f"robots/robots/{robot_id}/")
            photos = [
                photo
                for photo in current.get("photos") or []
                if is_restricted_media_url(robot_id, photo.get("url"))
            ]
            current_urls = {
                str(url)
                for url in [
                    current.get("image"),
                    current.get("s3_image"),
                    *(current.get("images") or []),
                    *(photo.get("url") for photo in photos),
                ]
                if is_restricted_media_url(robot_id, str(url or ""))
            }
            if current.get("status") != "pending_review":
                report["skipped"].append(
                    {
                        "id": robot_id,
                        "model": target["model"],
                        "reason": f"status is {current.get('status')}; published guardrail",
                        "restricted_urls": sorted(current_urls),
                        "restricted_photo_ids": [photo["id"] for photo in photos],
                    }
                )
                continue

            if not current_urls and not photos:
                report["skipped"].append(
                    {
                        "id": robot_id,
                        "model": target["model"],
                        "reason": "known restricted upload is not attached",
                    }
                )
                continue

            candidate = {
                "id": robot_id,
                "model": target["model"],
                "urls": sorted(current_urls),
                "photo_ids": [photo["id"] for photo in photos],
            }
            report["targets"].append(candidate)
            if not apply:
                continue

            deleted_keys: list[str] = []
            retained_keys: list[str] = []
            if detach_only:
                retained_keys = [_s3_key(url) for url in sorted(current_urls)]
            else:
                deleted_keys = _delete_s3_objects(current_urls)
            for photo in photos:
                response = requests.delete(
                    (
                        f"{api_base}/admin/robots/robot/content-queue/api/robot/"
                        f"{robot_id}/photos/{photo['id']}/"
                    ),
                    headers={"X-Internal-Secret": secret},
                    timeout=60,
                )
                response.raise_for_status()

            client._patch(
                f"robots/robots/{robot_id}/",
                restricted_cad_cleanup_payload(robot_id, current.get("notes")),
            )
            refreshed = client._get(f"robots/robots/{robot_id}/")
            remaining = [
                photo
                for photo in refreshed.get("photos") or []
                if is_restricted_media_url(robot_id, photo.get("url"))
            ]
            if is_restricted_media_url(robot_id, refreshed.get("image")) or remaining:
                raise RuntimeError("restricted media remained attached after cleanup")
            if refreshed.get("status") != "pending_review":
                raise RuntimeError(f"status moved to {refreshed.get('status')}")

            if retained_keys:
                report["warnings"].append(
                    {
                        "id": robot_id,
                        "warning": (
                            "S3 delete was skipped after AccessDenied; object is detached "
                            "from the product but requires deletion by an authorized operator"
                        ),
                        "s3_keys": retained_keys,
                    }
                )
            report["cleaned"].append(
                {
                    **candidate,
                    "deleted_s3_keys": deleted_keys,
                    "retained_s3_keys": retained_keys,
                    "status": refreshed.get("status"),
                    "image": refreshed.get("image") or "",
                }
            )
            print(f"cleaned {robot_id} {target['model']}")
        except Exception as exc:
            report["errors"].append(
                {"id": robot_id, "model": target["model"], "error": str(exc)}
            )
            print(f"ERROR {robot_id}: {exc}", file=sys.stderr)

    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove rights-restricted Yamaha LCMR200 catalog images"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--detach-only",
        action="store_true",
        help="Detach DB media when this operator lacks S3 DeleteObject permission",
    )
    args = parser.parse_args(argv)
    if args.detach_only and not args.apply:
        parser.error("--detach-only requires --apply")
    return args


def main() -> int:
    args = parse_args()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = cleanup_restricted_media(
        ResearchApiClient(),
        apply=args.apply,
        detach_only=args.detach_only,
    )
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
