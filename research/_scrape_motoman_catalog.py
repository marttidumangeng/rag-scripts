"""Scrape Motoman industrial Spec Finder catalog → payload/reach by model."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "https://www.motoman.com/en-us/products/robots/industrial"
OUT = Path(__file__).resolve().parent / "staging" / "reports" / "yaskawa-motoman-catalog.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeek/1.0)"}


def strip(html: str) -> str:
    t = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"&amp;", "&", t)
    return re.sub(r"\n+", "\n", t)


def main() -> None:
    r = requests.get(URL, headers=UA, timeout=60)
    r.raise_for_status()
    text = strip(r.text)
    Path("staging/tmp/motoman-industrial.txt").write_text(text, encoding="utf-8")

    # Pattern: model name line followed by payload / vert / hor numbers in nearby lines
    # From WebFetch the structure is:
    # GP4
    # GP7
    # 7.00
    # 1693
    # 927
    # Actually looking at fetch - each model has its three numbers after the name
    # More reliable: find series blocks

    models: dict[str, dict] = {}
    # Explicit table from the page content - parse lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Known model pattern
    model_re = re.compile(
        r"^(GP\d+[A-Z0-9\-]*|HC\d+[A-Z0-9\-]*|NEX\d+|PL\d+|MPP\d+[A-Z]*|"
        r"SG\d+|MH\d+|PH\d+[A-Z]*|MYS\d+[A-Z]*|AR\d+[A-Z]*|GA\d+|"
        r"SP\d+[A-Z0-9\-]*|MPX[L]?\d+|MotoMini|SDA\d+[A-Z]*|SIA\d+[A-Z]*|"
        r"HC\d+\s+for\s+Welding|MHP\d+[A-Z]*)$",
        re.I,
    )

    i = 0
    while i < len(lines):
        ln = lines[i]
        if model_re.match(ln) and not ln.lower().endswith("series"):
            # Look ahead for three floats/ints
            nums: list[float] = []
            j = i + 1
            while j < len(lines) and len(nums) < 3:
                m = re.match(r"^(\d+(?:\.\d+)?)$", lines[j])
                if m:
                    nums.append(float(m.group(1)))
                    j += 1
                elif model_re.match(lines[j]):
                    break
                else:
                    j += 1
                    if j - i > 8:
                        break
            if len(nums) == 3:
                key = ln.upper().replace(" ", "")
                if "FORWELDING" in key:
                    key = re.sub(r"FORWELDING", "", key)
                models[ln] = {
                    "name": ln,
                    "payload_kg": nums[0],
                    "vert_reach_mm": nums[1],
                    "hor_reach_mm": nums[2],
                    "reach_mm": nums[2],  # Motoman "Max Working Range" ≈ horizontal
                }
                i = j
                continue
        i += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"url": URL, "count": len(models), "models": models}, indent=2), encoding="utf-8")
    print(f"parsed {len(models)} models -> {OUT}")
    for name, spec in sorted(models.items(), key=lambda x: x[0])[:15]:
        print(f"  {name}: pay={spec['payload_kg']} hor={spec['hor_reach_mm']} vert={spec['vert_reach_mm']}")
    print("...")
    missing_check = ["GP4", "GP25-12", "HC10DTP", "MotoMini", "SP185R", "MPX3500", "MPP3S"]
    for m in missing_check:
        hit = models.get(m) or models.get(m.upper())
        print(f"check {m}: {hit}")


if __name__ == "__main__":
    main()
