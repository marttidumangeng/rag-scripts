"""Audit and soft-delete exact duplicate active RobotPhoto records for Mirax Robots."""
from __future__ import annotations
import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
import requests
from load_env import load_research_env
from api_client import ResearchApiClient

COMPANY_ID = 1647

def _photo_key(photo: dict[str, Any]) -> str:
    url = str(photo.get("url") or "").strip().lower()
    s3 = str(photo.get("s3_image") or "").strip().lower()
    if url:
        return f"url:{url}"
    if s3:
        return f"s3:{s3}"
    return ""

def _root_base(api_base: str) -> str:
    base = api_base.rstrip("/") + "/"
    for suffix in ("/api/v1/", "/api/v1"):
        if base.endswith(suffix):
            return base[: -len(suffix)] + "/"
    return base

def _headers(client: ResearchApiClient) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "RobotAIGeek-ResearchAgent/1.0", "X-API-Key": client.api_key}
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if secret:
        headers["X-Internal-Secret"] = secret
    return headers

def _choose_keep(group: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(group, key=lambda p: (bool(p.get("is_primary")), bool(p.get("s3_image")), str(p.get("created_at") or ""), -int(p.get("id") or 0)), reverse=True)[0]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json-out", default="staging/reports/mirax_photo_dedupe.json")
    args = parser.parse_args()
    load_research_env()
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    deletions: list[dict[str, Any]] = []
    groups_report: list[dict[str, Any]] = []
    for robot in robots:
        active = [p for p in (robot.get("photos") or []) if not p.get("deleted")]
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for photo in active:
            key = _photo_key(photo)
            if key:
                groups[key].append(photo)
        for key, group in groups.items():
            if len(group) < 2:
                continue
            keep = _choose_keep(group)
            remove = [p for p in group if p.get("id") != keep.get("id")]
            groups_report.append({"robot_id": robot.get("id"), "robot_name": robot.get("name"), "key": key, "keep_photo_id": keep.get("id"), "remove_photo_ids": [p.get("id") for p in remove], "photo_count": len(group)})
            for photo in remove:
                deletions.append({"robot_id": robot.get("id"), "robot_name": robot.get("name"), "photo_id": photo.get("id"), "keep_photo_id": keep.get("id"), "key": key})
    result: dict[str, Any] = {"company_id": COMPANY_ID, "company_name": "Mirax Robots", "robots_scanned": len(robots), "duplicate_groups": groups_report, "candidate_deletions": deletions, "applied": False, "results": []}
    if args.apply:
        root = _root_base(client.base_url)
        session = requests.Session()
        session.headers.update(_headers(client))
        for item in deletions:
            url = urljoin(root, f"admin/robots/robot/content-queue/api/robot/{item['robot_id']}/photos/{item['photo_id']}/")
            resp = session.delete(url, timeout=120)
            try:
                body: Any = resp.json()
            except Exception:
                body = resp.text[:1000]
            result["results"].append({**item, "status_code": resp.status_code, "response": body})
            if resp.status_code >= 400:
                raise RuntimeError(f"Photo delete failed for {item['robot_id']}/{item['photo_id']}: {resp.status_code} {body}")
        result["applied"] = True
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"robots_scanned": result["robots_scanned"], "duplicate_groups": len(groups_report), "candidate_deletions": len(deletions), "applied": result["applied"], "results": result["results"], "json_out": str(out)}, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
