"""Rebuild Mirax gallery media through the local research bulk-import workflow."""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from load_env import load_research_env
from api_client import ResearchApiClient

COMPANY_ID = 1647


def key(photo: dict[str, Any]) -> str:
    url = str(photo.get("url") or "").strip().lower()
    s3 = str(photo.get("s3_image") or "").strip().lower()
    return "url:" + url if url else ("s3:" + s3 if s3 else "")


def image_payload(photo: dict[str, Any]) -> dict[str, Any] | None:
    url = str(photo.get("url") or "").strip()
    if not url:
        url = str(photo.get("s3_image") or "").strip()
    if not url:
        return None
    out: dict[str, Any] = {"url": url}
    for field in (
        "source_page_url", "source_tier", "source_publisher", "source_domain",
        "media_class", "image_scope", "match_reason", "rights_status",
        "content_hash", "retrieved_at", "confidence_score", "confidence_breakdown",
    ):
        if photo.get(field) not in (None, ""):
            out[field] = photo[field]
    return out


def dedup_images(photos: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[int]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    passthrough: list[dict[str, Any]] = []
    for photo in photos:
        k = key(photo)
        if not k:
            passthrough.append(photo)
        else:
            groups[k].append(photo)
    kept: list[dict[str, Any]] = []
    removed: list[int] = []
    for group in groups.values():
        chosen = sorted(
            group,
            key=lambda p: (
                bool(p.get("is_primary")),
                bool(p.get("s3_image")),
                str(p.get("created_at") or ""),
                -int(p.get("id") or 0),
            ),
            reverse=True,
        )[0]
        payload = image_payload(chosen)
        if payload:
            kept.append(payload)
        removed.extend(int(p["id"]) for p in group if p.get("id") != chosen.get("id"))
    for photo in passthrough:
        payload = image_payload(photo)
        if payload:
            kept.append(payload)
    return kept, removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json-out", default="staging/reports/mirax_photo_bulk_dedupe.json")
    args = ap.parse_args()
    load_research_env()
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    rows: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for robot in robots:
        images, removed = dedup_images([p for p in (robot.get("photos") or []) if not p.get("deleted")])
        if not removed:
            continue
        rows.append({"id": int(robot["id"]), "name": robot.get("name") or "", "images": images})
        report.append({"robot_id": robot["id"], "robot_name": robot.get("name"), "images_sent": len(images), "removed_photo_ids": removed})
    result: dict[str, Any] = {"company_id": COMPANY_ID, "company_name": "Mirax Robots", "robots_scanned": len(robots), "robots_with_duplicates": len(rows), "candidate_removed_photo_ids": [x for r in report for x in r["removed_photo_ids"]], "report": report, "applied": False, "api_result": None}
    if args.apply and rows:
        result["api_result"] = client.bulk_import_robots(rows, update_existing=True, patch_existing=True, replace_media=True, skip_company_update=True)
        result["applied"] = True
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"robots_scanned": result["robots_scanned"], "robots_with_duplicates": result["robots_with_duplicates"], "candidate_removed": len(result["candidate_removed_photo_ids"]), "applied": result["applied"], "api_result": result["api_result"], "json_out": str(out)}, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
