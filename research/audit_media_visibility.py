from __future__ import annotations
import json
import sys
from pathlib import Path

RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore

COMPANIES = [220, 1490, 1419, 1637, 1422, 1635, 1489, 1630, 1474, 204, 416, 107, 1458, 1421, 883, 1399]
client = ResearchApiClient()
results = []
for company_id in COMPANIES:
    robots = client.list_robots_for_company(company_id)
    missing_primary = []
    no_gallery = []
    for robot in robots:
        rid = int(robot.get("id") or 0)
        photos = robot.get("photos") or []
        if isinstance(photos, dict):
            photos = photos.get("results") or photos.get("items") or []
        photo_count = len(photos) if isinstance(photos, list) else 0
        if not str(robot.get("image") or robot.get("image_url") or robot.get("s3_image") or "").strip():
            missing_primary.append({"robot_id": rid, "name": robot.get("name"), "photo_count": photo_count})
        if photo_count == 0:
            no_gallery.append({"robot_id": rid, "name": robot.get("name"), "image": robot.get("image")})
    results.append({
        "company_id": company_id,
        "robots": len(robots),
        "missing_primary": missing_primary,
        "no_gallery": no_gallery,
    })
out = RESEARCH_DIR / "staging" / "reports" / "recent_media_visibility_audit.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"companies": results}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "companies": len(results),
    "robots": sum(r["robots"] for r in results),
    "missing_primary": sum(len(r["missing_primary"]) for r in results),
    "no_gallery": sum(len(r["no_gallery"]) for r in results),
    "report": str(out),
}, ensure_ascii=False, indent=2))
