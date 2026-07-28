"""Quick verification of patched Cyberdyne JSON files."""
import json
from pathlib import Path

staging_dir = Path("staging/robots/cyberdyne-inc/overnight")
files = sorted(staging_dir.glob("robot_*.json"))

print(f"{'File':<25} {'Name':<45} {'Model':<20} {'Family':<30} {'Videos':>6} {'Specs':>5}")
print("-" * 140)

for f in files:
    raw = json.loads(f.read_text(encoding="utf-8"))
    d = raw[0] if isinstance(raw, list) else raw
    name = d.get("name", "")[:44]
    model = d.get("model_name", "")[:19]
    family = d.get("family_name", "")[:29]
    videos = len(d.get("video_urls") or [])
    # count non-empty spec fields
    spec_fields = ["weight_kg", "height_mm", "width_mm", "length_mm", "runtime_minutes", "dof", "payload_kg", "ip_rating"]
    specs = sum(1 for s in spec_fields if d.get(s) not in (None, "", []))
    print(f"{f.name:<25} {name:<45} {model:<20} {family:<30} {videos:>6} {specs:>5}")
