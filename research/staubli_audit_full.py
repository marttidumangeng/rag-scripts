"""Full audit of all Stäubli staged JSON files — images, names, models."""
import json
from pathlib import Path

base = Path("staging/robots/staubli-robotics")
all_files = sorted(base.rglob("robot_*.json"))

print(f"Total files found: {len(all_files)}\n")
print(f"{'File':<30} {'ID':>6} {'Name':<38} {'Model':<22} {'Image'}")
print("-" * 130)

missing = []
for f in all_files:
    raw = json.loads(f.read_text(encoding="utf-8"))
    d = raw[0] if isinstance(raw, list) else raw
    robot_id = d.get("id") or f.stem.split("_")[1]
    name = (d.get("name") or "")[:37]
    model = (d.get("model_name") or "")[:21]
    image = d.get("image") or ""
    images = d.get("images") or []
    if not image:
        status = "*** MISSING ***"
        missing.append((f, d))
    elif "placeholder" in image.lower():
        status = "PLACEHOLDER"
        missing.append((f, d))
    else:
        # Show just the filename part of the URL
        img_short = image.split("/")[-1][:40]
        status = f"OK: {img_short}"
    rel = str(f).replace(str(base), "").lstrip("/\\")
    print(f"{rel:<30} {str(robot_id):>6} {name:<38} {model:<22} {status}")

print(f"\n{'='*80}")
print(f"Missing/placeholder images: {len(missing)}")
for f, d in missing:
    print(f"  {f.name}: {d.get('name')} ({d.get('model_name')}) id={d.get('id')}")
