from __future__ import annotations
import json
import sys
from pathlib import Path

research_dir = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(research_dir))
from api_client import ResearchApiClient  # type: ignore

ROBOT_ID = 2443
CANDIDATE = "https://www.estun.com/uploads/20250903/1ee2b7172376d1bd128ba6139c7e9727.png"
client = ResearchApiClient()
result = client._patch(
    f"robots/robots/{ROBOT_ID}/",
    {
        "image": CANDIDATE,
        "notes": "[QUALITY REVIEW] Replaced invalid technical drawing primary with official Estun iER-family product image. Exact model page returned HTTP 502; family-level scope retained for manual review.",
    },
)
print(json.dumps({"robot_id": ROBOT_ID, "new_image": CANDIDATE, "result": result}, ensure_ascii=False, indent=2))
