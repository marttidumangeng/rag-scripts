"""Extract ECO62/RX71/RX75 variant toggle values from PDP HTML."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(slug: str) -> str:
    url = f"https://www.realman-robotics.com/en/products/{slug}.html"
    r = requests.get(url, headers=UA, timeout=45)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def main() -> None:
    for slug in ("eco62", "eco63", "rx71", "rx75"):
        html = fetch(slug)
        # dump snippets around Standard / Force / Vision option buttons
        print(f"\n======== {slug} ========")
        # Look for JSON-ish embedded product data
        for m in re.finditer(r"\{[^{}]{0,200}(?:Standard|Six-Axis|Vision|payload|radius)[^{}]{0,200}\}", html, re.I):
            s = re.sub(r"\s+", " ", m.group(0))
            if len(s) > 40:
                print(" jsonish:", s[:200])
        # Table-like consecutive spans
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = re.sub(r"\n+", "\n", text)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        # print window around Force/Standard mentions that aren't nav
        for i, ln in enumerate(lines):
            low = ln.casefold()
            if low in {"standard", "six-axis force", "vision"} or "force sensor" in low or "working radius" in low:
                ctx = lines[max(0, i - 2) : i + 6]
                print(" --", " | ".join(ctx)[:180])

    out = Path("staging/reports/realman-missing-variant-verdict.json")
    verdict = {
        "create": [
            {
                "name": "ECO63 Standard",
                "why": "OEM folder ECO63-标准版 + page says Available in Standard and Six-Axis Force",
            },
            {
                "name": "ECO63 Six-Axis Force",
                "why": "OEM folder ECO63-六维力版 with distinct renders",
            },
            {
                "name": "RX71 Standard",
                "why": "Only OEM folder is RX71-标准版; name the published bare RX71 sibling pattern",
            },
        ],
        "do_not_create": [
            {
                "name": "ECO62 Six-Axis Force",
                "why": "UI label Six-Axis Force exists but ONLY ECO62-标准版 assets on PDP; no 六维力版 folder (404). Fail-closed — no distinct Force hero.",
            },
            {
                "name": "RX71 Six-Axis Force",
                "why": "Not a SKU. Spec labels are 'Six-Axis Force Range' and 'Working Radius (incl. force sensor)' — force is built into the single RX71.",
            },
            {
                "name": "RX75 Six-Axis Force",
                "why": "Not a SKU. Page: 'Integrated Six-Axis Force' feature + 'Available in Standard and Vision' only. No RX75-六维力版 assets.",
            },
        ],
        "note": "Of the original 6 gap names, 3 are real create targets; 3 fail OEM evidence.",
    }
    out.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\nwrote", out)


if __name__ == "__main__":
    main()
