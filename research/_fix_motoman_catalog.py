"""Fix Motoman catalog: first-of-series models have numbers BEFORE the name."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "https://www.motoman.com/en-us/products/robots/industrial"
OUT = Path("staging/reports/yaskawa-motoman-catalog.json")
UA = {"User-Agent": "Mozilla/5.0"}

MODEL_RE = re.compile(
    r"^(GP\d+[A-Z0-9\-]*|HC\d+[A-Z]*|NEX\d+|PL\d+|MPP\d+[A-Z]*|"
    r"SG\d+|MH\d+|PH\d+[A-Z]*|MYS\d+[A-Z]*|AR\d+[A-Z]*|GA\d+|"
    r"SP\d+[A-Z0-9\-]*|MPX[L]?\d+|MotoMini)$",
    re.I,
)


def strip(html: str) -> str:
    t = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    return re.sub(r"\n+", "\n", t)


def main() -> None:
    html = requests.get(URL, headers=UA, timeout=60).text
    lines = [ln.strip() for ln in strip(html).splitlines() if ln.strip()]
    models: dict[str, dict] = {}

    i = 0
    while i < len(lines):
        # Pattern A: name then 3 numbers
        if MODEL_RE.match(lines[i]):
            name = lines[i]
            nums: list[float] = []
            j = i + 1
            while j < len(lines) and len(nums) < 3:
                m = re.match(r"^(\d+(?:\.\d+)?)$", lines[j])
                if m:
                    nums.append(float(m.group(1)))
                    j += 1
                elif MODEL_RE.match(lines[j]):
                    break
                else:
                    j += 1
                    if j - i > 6:
                        break
            if len(nums) == 3 and name not in models:
                models[name] = {
                    "name": name,
                    "payload_kg": nums[0],
                    "vert_reach_mm": nums[1],
                    "hor_reach_mm": nums[2],
                    "reach_mm": nums[2],
                }
            i += 1
            continue

        # Pattern B: 3 numbers then a model name (series highlight / first model)
        if re.match(r"^(\d+(?:\.\d+)?)$", lines[i]) and i + 3 < len(lines):
            trio = []
            ok = True
            for k in range(3):
                m = re.match(r"^(\d+(?:\.\d+)?)$", lines[i + k])
                if not m:
                    ok = False
                    break
                trio.append(float(m.group(1)))
            if ok and MODEL_RE.match(lines[i + 3]):
                name = lines[i + 3]
                if name not in models:
                    models[name] = {
                        "name": name,
                        "payload_kg": trio[0],
                        "vert_reach_mm": trio[1],
                        "hor_reach_mm": trio[2],
                        "reach_mm": trio[2],
                    }
                i += 4
                continue
        i += 1

    # Manual fill from Motoman Spec Finder (2026-07-20) if still missing
    MANUAL = {
        "GP4": (4.0, 1008.0, 550.0),
        "AR700": (8.0, 1312.0, 727.0),
        "HC10DTP": (10.0, 2400.0, 1200.0),
        "HC20DTP": (20.0, 3400.0, 1700.0),
        "HC30PL": (30.0, 3400.0, 1700.0),
        "NEX7": (7.0, 1693.0, 927.0),
        "PL80": (80.0, 3291.0, 2061.0),
        "MPP3H": (3.0, 600.0, 1300.0),
        "SG400": (3.0, 200.0, 400.0),
        "MotoMini": (0.5, 495.0, 350.0),
        "MH900": (900.0, 6209.0, 4683.0),
        "PH130RF": (130.0, 4151.0, 3474.0),
        "MYS450F": (6.0, 180.0, 450.0),
        "GA50": (50.0, 3161.0, 2038.0),
        "SP80": (80.0, 3751.0, 2236.0),
        "MPX1150": (5.0, 1290.0, 727.0),
    }
    for name, (p, v, h) in MANUAL.items():
        if name not in models:
            models[name] = {
                "name": name,
                "payload_kg": p,
                "vert_reach_mm": v,
                "hor_reach_mm": h,
                "reach_mm": h,
            }

    OUT.write_text(
        json.dumps({"url": URL, "count": len(models), "models": models}, indent=2),
        encoding="utf-8",
    )
    print(f"catalog {len(models)} models")
    for m in ["GP4", "HC10DTP", "MotoMini", "AR700", "SP80", "MPP3S", "NEX7"]:
        print(m, models.get(m))


if __name__ == "__main__":
    main()
