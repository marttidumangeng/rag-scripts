from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore

RECENT_COMPANIES = [220, 1490, 1419, 1637, 1422, 1635, 1489, 1630, 1474, 204, 416, 107, 1458, 1421, 883, 1399]
TEXT_FIELDS = ["description", "purpose", "features", "notes", "strengths", "weaknesses", "software", "uses_other", "industries_other"]
MANDATORY_FIELD_MAP = {
    "purpose": ("purpose",),
    "features": ("features",),
    "tags": ("tags", "tag_names"),
    "category": ("category_slugs", "category", "categories"),
    "uses": ("use_keys", "uses", "uses_other"),
    "industries": ("industry_keys", "industries", "industries_other"),
    "description": ("description",),
}
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
BAD_TEXT_PATTERNS = [
    r"502\s+Bad\s+Gateway", r"Bad\s+Gateway", r"Browser\s+Working", r"Host\s+Error",
    r"发生什么事了", r"网站服务无法请求", r"WTS\s+Working", r"Error\s*\d{3}",
    r"404\s+Not\s+Found", r"Internal\s+Server\s+Error", r"Access\s+Denied", r"Just\s+a\s+moment",
    r"captcha", r"cloudflare", r"enable javascript",
]
BAD_URL_PATTERNS = [r"logo", r"favicon", r"banner", r"sprite", r"placeholder", r"default\.(png|jpg|jpeg|webp)", r"avatar", r"qr(code)?", r"/icon", r"technical[-_ ]?drawing", r"blueprint", r"schematic", r"line[-_ ]?art", r"cad"]
PHOTO_FIELDS = ("source_page_url", "source_tier", "source_publisher", "source_domain", "media_class", "image_scope", "match_reason", "rights_status", "content_hash", "retrieved_at", "confidence_score", "confidence_breakdown")


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def bad_text(value: Any) -> bool:
    value = text(value)
    return any(re.search(pattern, value, flags=re.I) for pattern in BAD_TEXT_PATTERNS)


def media_url(photo: dict[str, Any]) -> str:
    for key in ("url", "image", "s3_image", "photo_url", "source_url", "original_url", "src"):
        value = str(photo.get(key) or "").strip()
        if value:
            return value
    return ""


def media_key(photo: dict[str, Any]) -> str:
    content_hash = str(photo.get("content_hash") or "").strip().lower()
    if content_hash:
        return "hash:" + content_hash
    return "url:" + media_url(photo).strip().lower()


def photo_payload(photo: dict[str, Any]) -> dict[str, Any] | None:
    url = media_url(photo)
    if not url:
        return None
    out: dict[str, Any] = {"url": url}
    for field in PHOTO_FIELDS:
        if photo.get(field) not in (None, "", [], {}):
            out[field] = photo[field]
    return out


def dedupe_photos(robot: dict[str, Any]) -> tuple[list[dict[str, Any]], list[int]]:
    photos = robot.get("photos") or []
    if isinstance(photos, dict):
        photos = photos.get("results") or photos.get("items") or []
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for photo in photos if isinstance(photos, list) else []:
        if isinstance(photo, dict) and media_key(photo) != "url:":
            groups[media_key(photo)].append(photo)
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


def clean_company(client: ResearchApiClient, company_id: int, *, apply: bool) -> dict[str, Any]:
    robots = client.list_robots_for_company(company_id)
    report: dict[str, Any] = {
        "company_id": company_id,
        "robots": len(robots),
        "bad_text_records": [],
        "duplicate_photo_records": [],
        "cross_robot_url_groups": [],
        "patched_text_records": 0,
    "media_replace_rows": 0,
    "low_score_records": [],
            "quality_flag_records": [],
        "missing_field_records": [],
        "non_english_records": [],

    "api_results": [],
    }
    cross: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    rows: list[dict[str, Any]] = []
    for robot in robots:
        rid = int(robot.get("id") or 0)
        bad_fields = [field for field in TEXT_FIELDS if bad_text(robot.get(field))]
        missing_fields = []
        for label, candidates in MANDATORY_FIELD_MAP.items():
            if not any(text(robot.get(candidate)).strip() for candidate in candidates):
                missing_fields.append(label)
        non_english_fields = []
        source_locale = text(robot.get("source_locale")).strip().lower()
        if source_locale in {"", "en", "en-us", "en-gb"}:
            for field in TEXT_FIELDS:
                if CJK_PATTERN.search(text(robot.get(field))):
                    non_english_fields.append(field)
        if missing_fields:
            report.setdefault("missing_field_records", []).append({"robot_id": rid, "name": robot.get("name"), "fields": missing_fields})
        if non_english_fields:
            report.setdefault("non_english_records", []).append({"robot_id": rid, "name": robot.get("name"), "fields": non_english_fields})
        verification_confidence = robot.get("verification_confidence")
        score_values = {field: robot.get(field) for field in ("overall_score", "technology_score", "product_maturity_score")}
        low_scores = []
        try:
            if verification_confidence is None or float(verification_confidence) < 70:
                low_scores.append({"field": "verification_confidence", "value": verification_confidence})
            for field, value in score_values.items():
                if value in (None, "") or float(value) <= 0:
                    low_scores.append({"field": field, "value": value})
        except (TypeError, ValueError):
            low_scores.append({"field": "score_parse", "value": score_values})
        if low_scores:
            report["low_score_records"].append({"robot_id": rid, "name": robot.get("name"), "scores": low_scores})
        quality_flags = robot.get("quality_flags") or []
        if quality_flags:
            report["quality_flag_records"].append({"robot_id": rid, "name": robot.get("name"), "quality_flags": quality_flags})
        if bad_fields:
            report["bad_text_records"].append({"robot_id": rid, "name": robot.get("name"), "fields": bad_fields})
            if apply:
                patch = {field: "" for field in bad_fields}
                # Do not let the bad scrape text remain in the record. It will become an explicit gap for re-enrichment.
                try:
                    client._patch(f"robots/robots/{rid}/", patch)
                    report["patched_text_records"] += 1
                except Exception as exc:  # noqa: BLE001
                    report["api_results"].append({"robot_id": rid, "text_patch_error": str(exc)})
        kept, removed = dedupe_photos(robot)
        if removed:
            report["duplicate_photo_records"].append({"robot_id": rid, "name": robot.get("name"), "removed_photo_ids": removed, "kept_count": len(kept)})
        for photo in (robot.get("photos") or []):
            if not isinstance(photo, dict):
                continue
            url = media_url(photo).lower()
            if url:
                cross[url].append({"robot_id": rid, "name": robot.get("name"), "photo_id": photo.get("id")})
        if kept:
            rows.append({"id": rid, "name": robot.get("name") or "", "photos": kept})
    report["cross_robot_url_groups"] = [
        {"url": url, "owners": owners}
        for url, owners in cross.items()
        if len(owners) > 1
    ]
    if apply and rows:
        for start in range(0, len(rows), 25):
            batch = rows[start : start + 25]
            try:
                result = client.bulk_import_robots(
                    batch,
                    update_existing=True,
                    patch_existing=True,
                    skip_company_update=True,
                    replace_media=True,
                    status="pending_review",
                )
                report["api_results"].append(result)
                report["media_replace_rows"] += len(batch)
            except Exception as exc:  # noqa: BLE001
                report["api_results"].append({"media_replace_error": str(exc), "batch_start": start})
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-ids", nargs="+", type=int, default=RECENT_COMPANIES)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json-out", default="staging/reports/recent_quality_gate_cleanup.json")
    args = parser.parse_args()
    client = ResearchApiClient()
    results = [clean_company(client, cid, apply=args.apply) for cid in args.company_ids]
    out = RESEARCH_DIR / args.json_out
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"apply": args.apply, "companies": results}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "apply": args.apply,
        "companies": len(results),
        "robots": sum(r["robots"] for r in results),
        "bad_text_records": sum(len(r["bad_text_records"]) for r in results),
        "patched_text_records": sum(r["patched_text_records"] for r in results),
        "duplicate_photo_records": sum(len(r["duplicate_photo_records"]) for r in results),
        "media_replace_rows": sum(r["media_replace_rows"] for r in results),
        "low_score_records": sum(len(r["low_score_records"]) for r in results),
        "quality_flag_records": sum(len(r["quality_flag_records"]) for r in results),
        "missing_field_records": sum(len(r.get("missing_field_records", [])) for r in results),
        "non_english_records": sum(len(r.get("non_english_records", [])) for r in results),
        "report": str(out),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
