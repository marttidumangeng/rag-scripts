from __future__ import annotations
import json, sys
from pathlib import Path
RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore
client = ResearchApiClient()
ids = [6864, 6866]
rows = []
for robot_id in ids:
    detail = client._get(f"robots/robots/{robot_id}/")
    photos = detail.get("photos") or []
    if isinstance(photos, dict): photos = photos.get("results") or photos.get("items") or []
    rows.append({
        "robot_id": robot_id,
        "name": detail.get("name"),
        "model_name": detail.get("model_name"),
        "family_name": detail.get("family_name"),
        "url": detail.get("url"),
        "image": detail.get("image"),
        "image_url": detail.get("image_url"),
        "s3_image": detail.get("s3_image"),
        "photo_count": len(photos),
        "photos": photos,
        "features": detail.get("features"),
        "description": detail.get("description"),
        "notes": detail.get("notes"),
        "quality_flags": detail.get("quality_flags"),
        "verification_confidence": detail.get("verification_confidence"),
    })
out = RESEARCH_DIR / "staging" / "reports" / "qinfeng_6864_6866_detail.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(rows, ensure_ascii=False, indent=2))
print("report:", out)
