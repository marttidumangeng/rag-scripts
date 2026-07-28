"""Validate Huayan image candidates and emit future bulk-import rows.

This tool is deliberately read-only. Production does not yet serialize the
image-rights workflow, so this module has no apply or upload mode.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import socket
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from PIL import Image, UnidentifiedImageError

from load_env import load_research_env

load_research_env()

COMPANY_ID = 1490
COMPANY_SLUG = "huayan-robotics"
COMPANY_NAME = "Huayan Robotics"
RESEARCH_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = (
    RESEARCH_DIR
    / "staging"
    / "robots"
    / COMPANY_SLUG
    / "image-rights-candidates.json"
)
REPORT_PATH = (
    RESEARCH_DIR
    / "staging"
    / "reports"
    / "huayan-image-candidate-validation.json"
)
PRODUCTION_API_BASE = "https://api.robotaigeek.com/api/v1/"
PRODUCTION_API_HOSTS = frozenset(
    {"api.robotaigeek.com", "ragadmin.robotaigeek.com"}
)

CANDIDATE_KEYS = (
    "url",
    "source_page_url",
    "source_publisher",
    "source_tier",
    "media_class",
    "image_scope",
    "confidence_score",
    "match_reason",
    "rights_status",
)
FORBIDDEN_BULK_FIELDS = frozenset(
    {
        "image",
        "replace_media",
        "status",
        "s3_image",
        "copy_media",
        "upload",
        "media_copy",
        "description",
        "features",
        "purpose",
        "payload_kg",
        "reach_mm",
        "weight_kg",
    }
)
EXPECTED_ROBOTS = {
    3670: "E03-Pro",
    3671: "E05-Pro",
    3672: "E05L-Pro",
    3684: "E10F",
    3685: "E10F-L",
    3686: "E12F",
    3687: "E15F",
    5301: "E15",
    5559: "Echo 3",
    5560: "Echo 5",
    5561: "Echo 15",
    5562: "HY 3",
    5563: "HY 7",
    5564: "HY 15",
    5565: "STAR-S",
    5566: "STAR-L",
    5567: "STAR-M",
    5568: "STAR-H",
    5569: "E03Li",
    5570: "E05Li",
    5571: "E05Li-L",
    5572: "E10Li",
    5573: "E12Li",
    5574: "E15Li",
    5575: "S20Li",
    5576: "S30Li",
}
REQUIRED_MANUAL_REVIEW_MODELS = frozenset(
    {
        "E03-Pro",
        "E05-Pro",
        "Echo 3",
        "Echo 5",
        "Echo 15",
        "HY 3",
        "HY 7",
        "HY 15",
        "STAR-S",
        "STAR-L",
        "STAR-M",
        "STAR-H",
        "E12Li",
        "E15Li",
        "S20Li",
        "S30Li",
    }
)
_ALLOWED_IMAGE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})
_MAGIC_BYTES = {
    "PNG": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "JPEG": lambda data: data.startswith(b"\xff\xd8\xff"),
    "WEBP": lambda data: (
        len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    ),
}


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").casefold()


def _is_huayan_host(url: str) -> bool:
    host = _host(url)
    return host in {"huayan-robotics.com", "huayan-robotics.net"} or host.endswith(
        (".huayan-robotics.com", ".huayan-robotics.net")
    )


def normalize_production_endpoint(base_url: str) -> str:
    parsed = urlparse((base_url or "").strip())
    host = (parsed.hostname or "").casefold()
    path = parsed.path.rstrip("/")
    safe = (
        parsed.scheme.casefold() == "https"
        and host in PRODUCTION_API_HOSTS
        and parsed.port in (None, 443)
        and not parsed.username
        and not parsed.password
        and path == "/api/v1"
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )
    if not safe:
        raise ValueError(
            "production API endpoint must be HTTPS on an exact allowlisted "
            "RobotAIGeek production host with path /api/v1/"
        )
    return f"https://{host}/api/v1/"


def _has_media(row: dict[str, Any]) -> bool:
    return any(row.get(field) for field in ("image", "images", "s3_image", "photos"))


def validate_static_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("company_id") != COMPANY_ID:
        errors.append(f"company_id must be {COMPANY_ID}")
    if manifest.get("company_slug") != COMPANY_SLUG:
        errors.append(f"company_slug must be {COMPANY_SLUG}")
    if manifest.get("candidate_only") is not True:
        errors.append("manifest must be candidate_only")
    if manifest.get("production_mutation_allowed") is not False:
        errors.append("production mutation must be explicitly disabled")

    entries = manifest.get("candidates")
    if not isinstance(entries, list):
        return [*errors, "candidates must be a list"]
    if len(entries) != len(EXPECTED_ROBOTS):
        errors.append(f"expected 26 candidates, found {len(entries)}")

    actual_pairs: list[tuple[int, str]] = []
    urls: list[str] = []
    for index, entry in enumerate(entries):
        label = f"candidate[{index}]"
        robot_id = entry.get("robot_id")
        model = entry.get("model")
        if isinstance(robot_id, int) and isinstance(model, str):
            actual_pairs.append((robot_id, model))
            label = f"{robot_id}/{model}"
        candidate = entry.get("candidate")
        if not isinstance(candidate, dict):
            errors.append(f"{label}: candidate must be an object")
            continue
        if set(candidate) != set(CANDIDATE_KEYS):
            errors.append(f"{label}: candidate keys must exactly match backend names")
        url = str(candidate.get("url") or "")
        source_page_url = str(candidate.get("source_page_url") or "")
        urls.append(url)
        for field, expected in (
            ("source_tier", "official_exact"),
            ("media_class", "official_render"),
            ("image_scope", "exact_variant"),
            ("rights_status", "review_required"),
        ):
            if candidate.get(field) != expected:
                errors.append(f"{label}: {field} must be {expected}")
        score = candidate.get("confidence_score")
        if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 69:
            errors.append(
                f"{label}: review_required confidence_score must obey hard cap 0 to 69"
            )
        if not url.startswith("https://"):
            errors.append(f"{label}: image URL must use HTTPS")
        if not source_page_url.startswith("https://"):
            errors.append(f"{label}: source page URL must use HTTPS")
        if not _is_huayan_host(url) or not _is_huayan_host(source_page_url):
            errors.append(f"{label}: source page and image host must be Huayan domains")
        if "robotaigeek.com" in _host(url):
            errors.append(f"{label}: candidate must remain external")
        if not str(candidate.get("source_publisher") or "").strip():
            errors.append(f"{label}: source_publisher is required")
        if not str(candidate.get("match_reason") or "").strip():
            errors.append(f"{label}: match_reason is required")
        if entry.get("image_format") not in _ALLOWED_IMAGE_FORMATS:
            errors.append(f"{label}: unsupported image_format")
        for dimension in ("image_width_px", "image_height_px"):
            if not isinstance(entry.get(dimension), int) or entry[dimension] <= 0:
                errors.append(f"{label}: {dimension} must be a positive integer")

    expected_pairs = set(EXPECTED_ROBOTS.items())
    if set(actual_pairs) != expected_pairs or len(actual_pairs) != len(expected_pairs):
        errors.append("robot IDs/models do not exactly match the expected 26")
    if len({robot_id for robot_id, _ in actual_pairs}) != len(actual_pairs):
        errors.append("duplicate robot ID")
    if len(urls) != len(set(urls)):
        errors.append("duplicate candidate URL")

    caveated = {
        entry.get("model")
        for entry in entries
        if str(entry.get("manual_exactness_review") or "").strip()
    }
    missing_caveats = sorted(REQUIRED_MANUAL_REVIEW_MODELS - caveated)
    if missing_caveats:
        errors.append(
            "missing manual exactness-review caveat: " + ", ".join(missing_caveats)
        )
    return errors


def build_bulk_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": entry["robot_id"],
            "name": entry["model"],
            "company_id": COMPANY_ID,
            "company_slug": COMPANY_SLUG,
            "company_name": manifest.get("company_name") or COMPANY_NAME,
            "images": [dict(entry["candidate"])],
        }
        for entry in manifest["candidates"]
    ]


def validate_production_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    by_id = {
        int(row["id"]): row
        for row in rows
        if str(row.get("id") or "").isdigit()
    }
    for entry in manifest["candidates"]:
        robot_id = entry["robot_id"]
        model = entry["model"]
        row = by_id.get(robot_id)
        if row is None:
            errors.append(f"{robot_id}/{model}: missing from live production")
            continue
        live_model = str(row.get("model_name") or row.get("name") or "")
        if live_model != model:
            errors.append(
                f"{robot_id}/{model}: production identity mismatch ({live_model})"
            )
        if row.get("status") != "pending_review":
            errors.append(
                f"{robot_id}/{model}: production status must be pending_review"
            )
        if _has_media(row):
            errors.append(f"{robot_id}/{model}: production record is not imageless")

    serialized_photos = [
        photo
        for row in rows
        if row.get("status") == "published"
        for photo in row.get("photos") or []
        if isinstance(photo, dict)
    ]
    rights_status_serialized = bool(serialized_photos) and all(
        "rights_status" in photo for photo in serialized_photos
    )
    return {
        "checked_robot_count": len(EXPECTED_ROBOTS),
        "errors": errors,
        "published_photo_count_checked": len(serialized_photos),
        "rights_status_serialized": rights_status_serialized,
        "production_rights_workflow_ready": rights_status_serialized,
    }


def _inspect_image(entry: dict[str, Any], response: Any) -> dict[str, Any]:
    candidate = entry["candidate"]
    url = candidate["url"]
    result: dict[str, Any] = {"robot_id": entry["robot_id"], "url": url}
    status_code = int(getattr(response, "status_code", 0))
    if status_code != 200:
        return {**result, "error": f"HTTP {status_code}"}
    final_url = str(getattr(response, "url", url) or url)
    if urlparse(final_url).scheme.casefold() != "https":
        return {**result, "error": "redirected image URL must use HTTPS"}
    if not _is_huayan_host(final_url):
        return {**result, "error": f"redirected to non-Huayan host: {_host(final_url)}"}
    content = bytes(getattr(response, "content", b""))
    if not content:
        return {**result, "error": "empty response body"}
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            image_format = str(image.format or "").upper()
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        return {**result, "error": f"image decode failed: {exc}"}
    if image_format not in _ALLOWED_IMAGE_FORMATS:
        return {**result, "error": f"unsupported decoded format: {image_format}"}
    if not _MAGIC_BYTES[image_format](content):
        return {**result, "error": f"{image_format} magic bytes mismatch"}
    expected_format = entry["image_format"]
    if image_format != expected_format:
        return {
            **result,
            "error": f"format mismatch: metadata {expected_format}, decoded {image_format}",
        }
    expected_size = (entry["image_width_px"], entry["image_height_px"])
    if (width, height) != expected_size:
        return {
            **result,
            "error": (
                f"dimension mismatch: metadata {expected_size[0]}x{expected_size[1]}, "
                f"decoded {width}x{height}"
            ),
        }
    return {
        **result,
        "status_code": status_code,
        "format": image_format,
        "width_px": width,
        "height_px": height,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def validate_manifest(
    manifest: dict[str, Any],
    production_rows: list[dict[str, Any]],
    *,
    fetch_image: Callable[[str], Any],
    checked_production_endpoint: str | None = None,
) -> dict[str, Any]:
    static_errors = validate_static_manifest(manifest)
    production = validate_production_rows(production_rows, manifest)
    inspections: list[dict[str, Any]] = []
    if not static_errors:
        for entry in manifest["candidates"]:
            try:
                response = fetch_image(entry["candidate"]["url"])
                inspections.append(_inspect_image(entry, response))
            except Exception as exc:
                inspections.append(
                    {
                        "robot_id": entry["robot_id"],
                        "url": entry["candidate"]["url"],
                        "error": str(exc),
                    }
                )
    failed_urls = [row for row in inspections if row.get("error")]
    hash_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in inspections:
        if row.get("sha256"):
            hash_groups[row["sha256"]].append(
                {"robot_id": row["robot_id"], "url": row["url"]}
            )
    hash_collisions = [
        {"sha256": digest, "candidates": candidates}
        for digest, candidates in sorted(hash_groups.items())
        if len(candidates) > 1
    ]
    valid = not (
        static_errors
        or production["errors"]
        or failed_urls
        or hash_collisions
    )
    scores = [
        entry["candidate"]["confidence_score"]
        for entry in manifest.get("candidates") or []
        if isinstance(entry.get("candidate"), dict)
        and isinstance(entry["candidate"].get("confidence_score"), int)
    ]
    staging_ready = valid
    return {
        "company_id": COMPANY_ID,
        "mode": "candidate_only_validation",
        "mutation_free": True,
        "checked_production_endpoint": checked_production_endpoint,
        "production_rights_workflow_ready": production[
            "production_rights_workflow_ready"
        ],
        "valid": valid,
        "staging_ready": staging_ready,
        "candidate_count": len(manifest.get("candidates") or []),
        "hash_count": len(hash_groups),
        "confidence_score_range": {
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
        },
        "static_errors": static_errors,
        "production": production,
        "failed_urls": failed_urls,
        "hash_collisions": hash_collisions,
        "image_validations": inspections,
        "manual_exactness_reviews": [
            {
                "robot_id": entry["robot_id"],
                "model": entry["model"],
                "caveat": entry["manual_exactness_review"],
            }
            for entry in manifest["candidates"]
            if entry.get("manual_exactness_review")
        ],
        "bulk_import_rows": build_bulk_rows(manifest) if staging_ready else [],
    }


def fetch_production_rows(
    *,
    base_url: str = PRODUCTION_API_BASE,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    base_url = normalize_production_endpoint(base_url)
    api_host = _host(base_url)
    headers = {
        "Accept": "application/json",
        "User-Agent": "RobotAIGeek-Huayan-Candidate-Validator/1.0",
    }
    api_key = os.environ.get("IMPORT_SYNC_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    session = requests.Session()
    session.headers.update(headers)
    with _working_dns_for_host(api_host, timeout=timeout):
        response = session.get(
            f"{base_url}robots/robots/",
            params={"company_ref": COMPANY_ID, "page_size": 100},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results", payload if isinstance(payload, list) else [])
        details: list[dict[str, Any]] = []
        for row in rows:
            detail = session.get(
                f"{base_url}robots/robots/{int(row['id'])}/",
                timeout=timeout,
            )
            detail.raise_for_status()
            details.append(detail.json())
    return details


@contextmanager
def _working_dns_for_host(host: str, *, timeout: int):
    """Use DNS-over-HTTPS only when the local resolver cannot resolve the API."""
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        response = requests.get(
            "https://dns.google/resolve",
            params={"name": host, "type": "A"},
            timeout=timeout,
        )
        response.raise_for_status()
        addresses = [
            answer["data"]
            for answer in response.json().get("Answer") or []
            if answer.get("type") == 1
        ]
        if not addresses:
            raise RuntimeError(f"DNS-over-HTTPS returned no A record for {host}")
        original = socket.getaddrinfo

        def resolved(query_host, port, *args, **kwargs):
            if query_host == host:
                return original(addresses[0], port, *args, **kwargs)
            return original(query_host, port, *args, **kwargs)

        socket.getaddrinfo = resolved
        try:
            yield
        finally:
            socket.getaddrinfo = original
    else:
        yield


def _network_fetcher(timeout: int) -> Callable[[str], requests.Response]:
    def fetch(url: str) -> requests.Response:
        return requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "RobotAIGeek-Huayan-Candidate-Validator/1.0"},
        )

    return fetch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Huayan candidate-only image staging (read-only)"
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("IMPORT_SYNC_API_BASE_URL") or PRODUCTION_API_BASE,
    )
    parser.add_argument("--timeout", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_manifest(args.manifest)
    production_error = ""
    checked_endpoint: str | None = None
    try:
        checked_endpoint = normalize_production_endpoint(args.api_base_url)
        production_rows = fetch_production_rows(
            base_url=checked_endpoint,
            timeout=args.timeout,
        )
    except Exception as exc:
        production_rows = []
        production_error = str(exc)
    report = validate_manifest(
        manifest,
        production_rows,
        fetch_image=_network_fetcher(args.timeout),
        checked_production_endpoint=checked_endpoint,
    )
    if production_error:
        report["production"] = {
            "errors": [f"production read failed: {production_error}"],
            "rights_status_serialized": False,
            "production_rights_workflow_ready": False,
        }
        report["production_rights_workflow_ready"] = False
        report["valid"] = False
        report["staging_ready"] = False
        report["bulk_import_rows"] = []
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "valid": report["valid"],
        "staging_ready": report["staging_ready"],
        "candidate_count": report["candidate_count"],
        "hash_count": report["hash_count"],
        "failed_url_count": len(report["failed_urls"]),
        "hash_collision_count": len(report["hash_collisions"]),
        "production_rights_workflow_ready": report[
            "production_rights_workflow_ready"
        ],
        "report": str(args.report),
    }, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
