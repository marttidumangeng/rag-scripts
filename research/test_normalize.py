"""Test normalize_hikrobot_model with variant suffixes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from hikrobot_catalog import normalize_hikrobot_model

tests = [
    ("TP5-50DCP(T)", ""),
    ("TP5-50DCW(T)", ""),
    ("TP6-50SCH", ""),
    ("TP6-50SCP", ""),
    ("Q3-600D (Hikrobot)", ""),
    ("F3-1500 (Hikrobot)", ""),
    ("Q3S 潜行式清扫机器人", ""),
    ("TP0-T50", ""),
]

all_ok = True
expected = {
    "TP5-50DCP(T)": "TP5-50DCP",
    "TP5-50DCW(T)": "TP5-50DCW",
    "TP6-50SCH": "TP6-50SCH",
    "TP6-50SCP": "TP6-50SCP",
    "Q3-600D (Hikrobot)": "Q3-600D",
    "F3-1500 (Hikrobot)": "F3-1500",
    "Q3S 潜行式清扫机器人": "Q3S",
    "TP0-T50": "TP0-T50",
}

for name, model in tests:
    result = normalize_hikrobot_model(name, model)
    exp = expected[name]
    status = "OK" if result == exp else f"FAIL (expected {exp!r})"
    print(f"  {name!r:35s} -> {result!r}  [{status}]")
    if result != exp:
        all_ok = False

print()
print("All tests passed!" if all_ok else "SOME TESTS FAILED!")
