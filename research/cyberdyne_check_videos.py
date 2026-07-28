"""Check which Cyberdyne robots still have 0 videos after patching."""
import json
from pathlib import Path

staging_dir = Path("staging/robots/cyberdyne-inc/overnight")
no_vid = []
has_vid = []

for f in sorted(staging_dir.glob("robot_*.json")):
    raw = json.loads(f.read_text(encoding="utf-8"))
    d = raw[0] if isinstance(raw, list) else raw
    vids = d.get("video_urls") or []
    name = d.get("name", "")
    model = d.get("model_name", "")
    family = d.get("family_name", "")
    if len(vids) == 0:
        no_vid.append((f.name, name, model, family))
    else:
        has_vid.append((f.name, name, model, len(vids)))

print(f"Robots WITH videos: {len(has_vid)}")
for fn, name, model, n in has_vid:
    print(f"  {fn}: {name} ({model}) — {n} video(s)")

print(f"\nRobots with 0 videos: {len(no_vid)}")
for fn, name, model, family in no_vid:
    print(f"  {fn}: {name} ({model}) [{family}]")
