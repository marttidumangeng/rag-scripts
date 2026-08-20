from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore

COMPANY_ID = 220
BAD_TEXT_PATTERNS = [
    r"502\s+Bad\s+Gateway",
    r"Bad\s+Gateway",
    r"Browser\s+Working",
    r"Host\s+Error",
    r"发生什么事了",
    r"网站服务无法请求",
    r"WTS\s+Working",
    r"Error\s*\d{3}",
    r"404\s+Not\s+Found",
    r"Internal\s+Server\s+Error",
    r"Access\s+Denied",
    r"Just\s+a\s+moment",
    r"captcha",
]
BAD_URL_PATTERNS = [
    r"logo",
    r"favicon",
    r"banner",
    r"sprite",
    r"placeholder",
    r"default\.(png|jpg|jpeg|webp)",
    r"avatar",
    r"qr(code)?",
    r"icon",
]
DRAWING_HINTS = [r"cad", r"drawing", r"line[-_ ]?art", r"schematic", r"blueprint", r"technical[-_ ]?drawing"]
SCORE_KEYS = {"ai_score", "content_score", "quality_score", "image_score", "confidence", "ai_verification", "verification", "scores"}
FIELD_KEYS = [
    "name", "family_name", "family_key", "family_url", "description", "purpose", "features", "notes",
    "tags", "specs", "weight_kg", "weight", "payload_kg", "reach_mm", "speed", "speed_ms", "dof",
    "voltage", "runtime", "runtime_minutes", "dimensions", "video_urls", "image", "photos", "status",
]

def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

def find_bad_text(value: Any) -> list[str]:
    text = text_value(value)
    hits = []
    for pattern in BAD_TEXT_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            hits.append(pattern)
    return hits

def url_risks(url: str) -> list[str]:
    risks = []
    for pattern in BAD_URL_PATTERNS:
        if re.search(pattern, url, flags=re.I):
            risks.append(pattern)
    for pattern in DRAWING_HINTS:
        if re.search(pattern, url, flags=re.I):
            risks.append(pattern)
    return risks

def get_photos(robot: dict[str, Any]) -> list[dict[str, Any]]:
    photos = robot.get("photos") or robot.get("robot_photos") or robot.get("media") or []
    if isinstance(photos, dict):
        photos = photos.get("results") or photos.get("items") or []
    return [p for p in photos if isinstance(p, dict)] if isinstance(photos, list) else []

def get_photo_url(photo: dict[str, Any]) -> str:
    for key in ("image", "url", "photo_url", "source_url", "original_url", "src"):
        value = photo.get(key)
        if value:
            return str(value)
    return ""

def score_fields(robot: dict[str, Any]) -> dict[str, Any]:
    return {k: robot.get(k) for k in sorted(SCORE_KEYS) if k in robot}

def main() -> None:
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "robots": len(robots),
        "field_presence": Counter(),
        "bad_text_hits": [],
        "low_or_missing_score_metadata": [],
        "media_url_risks": [],
        "duplicate_photo_urls": [],
        "robot_samples": [],
        "keys_seen": sorted({key for robot in robots for key in robot.keys()}),
    }
    url_owners: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for robot in robots:
        rid = robot.get("id")
        name = robot.get("name") or f"id={rid}"
        for field in FIELD_KEYS:
            value = robot.get(field)
            if value not in (None, "", [], {}):
                report["field_presence"][field] += 1
        bad_fields = []
        for field in FIELD_KEYS:
            hits = find_bad_text(robot.get(field))
            if hits:
                bad_fields.append({"field": field, "patterns": hits, "sample": text_value(robot.get(field))[:500]})
        if bad_fields:
            report["bad_text_hits"].append({"robot_id": rid, "name": name, "fields": bad_fields})
        scores = score_fields(robot)
        if not scores or any(v in (None, "", 0) for v in scores.values()):
            report["low_or_missing_score_metadata"].append({"robot_id": rid, "name": name, "scores": scores})
        image = str(robot.get("image") or "")
        if image:
            risks = url_risks(image)
            if risks:
                report["media_url_risks"].append({"robot_id": rid, "name": name, "kind": "primary", "url": image, "risks": risks})
            url_owners[image].append({"robot_id": rid, "name": name, "kind": "primary"})
        for photo in get_photos(robot):
            url = get_photo_url(photo)
            if not url:
                continue
            risks = url_risks(url)
            if risks:
                report["media_url_risks"].append({"robot_id": rid, "name": name, "kind": "gallery", "photo_id": photo.get("id"), "url": url, "risks": risks})
            url_owners[url].append({"robot_id": rid, "name": name, "kind": "gallery", "photo_id": photo.get("id")})
        if len(report["robot_samples"]) < 3:
            report["robot_samples"].append({
                "robot_id": rid,
                "name": name,
                "keys": sorted(robot.keys()),
                "scores": scores,
                "field_values": {field: text_value(robot.get(field))[:180] for field in FIELD_KEYS if robot.get(field) not in (None, "", [], {})},
                "photo_count": len(get_photos(robot)),
            })
    report["field_presence"] = dict(report["field_presence"])
    report["duplicate_photo_urls"] = [
        {"url": url, "owners": owners}
        for url, owners in url_owners.items()
        if len(owners) > 1
    ]
    out = RESEARCH_DIR / "staging" / "reports" / "estun_quality_audit_readonly.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "company_id": COMPANY_ID,
        "robots": len(robots),
        "bad_text_robots": len(report["bad_text_hits"]),
        "score_metadata_missing_or_zero": len(report["low_or_missing_score_metadata"]),
        "media_url_risk_records": len(report["media_url_risks"]),
        "duplicate_photo_url_groups": len(report["duplicate_photo_urls"]),
        "report": str(out),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
