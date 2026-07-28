import json
from collections import Counter
from pathlib import Path

staging = Path("staging/robots/estun-robotics")
heroes = []
for f in sorted(staging.glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    heroes.append((f.stem, d.get("image") or "", len(d.get("images") or [])))

hc = Counter(h for _, h, _ in heroes if h)
lines = ["duplicate hero URLs:"]
for url, n in hc.most_common(10):
    if n > 1:
        lines.append(f"  {n}x {url}")

listed = [
    "ier15-1430-mi", "ier20-800-sr-hi", "ier20-2300-hi", "ier220-2650",
    "ier6-600-sr", "ier8-720-mi-c", "ier10-500-sr",
]
lines.append("")
for s in listed:
    row = next((x for x in heroes if x[0] == s), None)
    if row:
        lines.append(f"{row[0]}: hero={row[1][-55:]} gallery={row[2]}")

Path("tmp_audit_out.txt").write_text("\n".join(lines), encoding="utf-8")
print("wrote tmp_audit_out.txt")
