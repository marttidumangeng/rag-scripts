"""Audit all Stäubli staged JSON files for missing or placeholder images."""
import json
from pathlib import Path

STAGING_DIRS = [
    Path("staging/robots/staubli-robotics/overnight"),
    Path("staging/robots/staubli-robotics"),
]

print(f"{'File':<25} {'ID':>6} {'Name':<35} {'Model':<22} {'Image status'}")
print("-" * 120)

for staging_dir in STAGING_DIRS:
    if not staging_dir.exists():
        continue
    for f in sorted(staging_dir.glob("robot_*.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        d = raw[0] if isinstance(raw, list) else raw
        robot_id = d.get("id") or f.stem.split("_")[1]
        name = (d.get("name") or "")[:34]
        model = (d.get("model_name") or "")[:21]
        image = d.get("image") or ""
        images = d.get("images") or []
        if not image:
            status = "MISSING"
        elif "placeholder" in image.lower() or "no-image" in image.lower():
            status = "PLACEHOLDER"
        else:
            status = f"OK ({len(images)} imgs)"
        print(f"{f.name:<25} {str(robot_id):>6} {name:<35} {model:<22} {status}")
