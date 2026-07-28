"""Pull ECO63 Standard vs Force two-column specs from PDP."""
from __future__ import annotations

import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
html = requests.get(
    "https://www.realman-robotics.com/en/products/eco63.html",
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=45,
).text
text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
text = re.sub(r"<[^>]+>", "\n", text)
lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
# Print from Technical Specs-ish region
start = 0
for i, ln in enumerate(lines):
    if "Technical" in ln or ln == "Working Radius" or "Available in Standard" in ln:
        start = max(0, i - 3)
        break
for ln in lines[start : start + 80]:
    print(ln)
