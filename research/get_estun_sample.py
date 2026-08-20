from __future__ import annotations
import json
import sys
from pathlib import Path

research_dir = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(research_dir))
from api_client import ResearchApiClient  # type: ignore

client = ResearchApiClient()
robot_id = 2443
robot = client._get(f"robots/robots/{robot_id}/")
out = research_dir / "staging" / "reports" / f"estun_robot_{robot_id}_full.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(robot, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"robot_id": robot_id, "keys": sorted(robot.keys()), "image": robot.get("image"), "photo_count": len(robot.get("photos") or []), "report": str(out)}, ensure_ascii=False, indent=2))
