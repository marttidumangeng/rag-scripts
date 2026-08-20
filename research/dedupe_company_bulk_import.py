from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore


def photo_url(photo: dict[str, Any]) -> str:
    for key in ("url", "image", "s3_image", "photo_url", "source_url", "original_url", "src"):
        value = str(photo.get(key) or "").strip()
        if value:
            return value
    return ""


def photo_key(photo: dict[str, Any]) -> str:
    content_hash = str(photo.get("content_hash") or "").strip().lower()
    return "hash:" + content_hash if content_hash else "url:" + photo_url(photo).lower()


def photo_payload(photo: dict[str, Any]) -> dict[str, Any] | None:
    url = photo_url(photo)
    if not url:
        return None
    out: dict[str, Any] = {"url": url}
    for field in (
        "source_page_url", "source_tier", "source_publisher", "source_domain",
        "media_class", "image_scope", "match_reason", "rights_status", "content_hash",
        "retrieved_at", "confidence_score", "confidence_breakdown",
    ):
        if photo.get(field) not in (None, "", [], {}):
            out[field] = photo[field]
    return out


def dedupe(robot: dict[str, Any]) -> tuple[list[dict[str, Any]], list[int]]:
    photos = robot.get("photos") or []
    if isinstance(photos, dict):
        photos = photos.get("results") or photos.get("items") or []
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    primary_url = str(robot.get("image") or robot.get("image_url") or "").strip()
    primary_key = "url:" + primary_url.lower() if primary_url else ""
    if primary_key:
        groups[primary_key].append({"id": None, "url": primary_url, "is_primary": True, "s3_image": primary_url})
    for photo in photos if isinstance(photos, list) else []:
        if isinstance(photo, dict):
            key = photo_key(photo)
            if key != "url:":
                groups[key].append(photo)
    kept: list[dict[str, Any]] = []
    removed: list[int] = []
    for group in groups.values():
        chosen = sorted(
            group,
            key=lambda p: (
                bool(p.get("is_primary")),
                bool(p.get("s3_image")),
                bool(p.get("confidence_score")),
                str(p.get("retrieved_at") or ""),
                -int(p.get("id") or 0),
            ),
            reverse=True,
        )[0]
        payload = photo_payload(chosen)
        if payload:
            kept.append(payload)
        for photo in group:
            if photo is not chosen and photo.get("id") is not None:
                removed.append(int(photo["id"]))
    return kept, removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-id", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json-out", default="staging/reports/company_photo_dedupe.json")
    args = ap.parse_args()
    client = ResearchApiClient()
    robots = client.list_robots_for_company(args.company_id)
    rows: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for robot in robots:
        kept, removed = dedupe(robot)
        if removed:
            report.append({"robot_id": robot.get("id"), "name": robot.get("name"), "removed_photo_ids": removed, "kept_count": len(kept)})
            rows.append({"id": robot.get("id"), "name": robot.get("name") or "", "photos": kept})
    result: dict[str, Any] = {"company_id": args.company_id, "apply": args.apply, "robots_scanned": len(robots), "robots_with_duplicates": len(report), "removed_records": sum(len(x["removed_photo_ids"]) for x in report), "report": report}
    if args.apply and rows:
        api_results = []
        for start in range(0, len(rows), 25):
            batch = rows[start : start + 25]
            api_results.append(client.bulk_import_robots(batch, update_existing=True, patch_existing=True, skip_company_update=True, replace_media=True, status="pending_review"))
        result["api_results"] = api_results
    out = RESEARCH_DIR / args.json_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("company_id", "apply", "robots_scanned", "robots_with_duplicates", "removed_records", "report") if k != "report"}, ensure_ascii=False, indent=2))
    print("report:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
