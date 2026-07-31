"""Check whether round-2 suspect companies already exist in the prod baseline."""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

base = json.loads(Path("staging/reports/prod_baseline.json").read_text(encoding="utf-8"))
names = [c.get("name", "") for c in base.get("companies", [])]

suspects = [
    "nachi", "mobile industrial", "mir", "teradyne", "zoox", "cruise", "waymo",
    "panasonic", "honeywell", "intelligrated", "yaskawa", "fanuc", "denso",
    "igus", "fuji", "kobe", "dmg mori", "iris ohyama", "musashi", "anki",
    "mayfield", "yushin", "iai", "siasun", "volvo", "disney", "wing",
    "faraday", "okura", "shinmaywa", "sailor",
]
for s in suspects:
    hits = [n for n in names if s in n.lower()]
    print(f"{s:22s} -> {hits if hits else 'NOT IN PROD'}")
