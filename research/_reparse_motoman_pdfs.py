"""Re-parse downloaded Motoman PDFs with comma-aware weight extraction."""
from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader

PDF_DIR = Path("staging/tmp/yaskawa-pdfs")
OUT = Path("staging/reports/yaskawa-datasheet-specs.json")
EXTRAS = json.loads(Path("staging/reports/yaskawa-pdp-extras.json").read_text(encoding="utf-8"))


def extract(text: str) -> dict:
    out = {}
    m = re.search(r"Repeatability\s*mm\s*([\d.]+)", text, re.I)
    if not m:
        m = re.search(r"([\d.]+)\s*mm\s+repeatability", text, re.I)
    if m:
        out["repeatability_mm"] = float(m.group(1))
    # Weight kg 1,130 or Weight kg 250
    m = re.search(r"Weight\s*kg\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if not m:
        m = re.search(r"Mass\s*kg\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if m:
        out["weight_kg"] = float(m.group(1).replace(",", ""))
    m = re.search(r"Maximum payload\s*kg\s*([\d.]+)", text, re.I)
    if m:
        out["payload_kg"] = float(m.group(1))
    m = re.search(r"Horizontal reach\s*mm\s*([\d,\.]+)", text, re.I)
    if m:
        out["hor_reach_mm"] = float(m.group(1).replace(",", ""))
    return out


def main() -> None:
    results = {}
    ok = empty = 0
    for rid, entry in EXTRAS["robots"].items():
        model = entry.get("model") or ""
        pdf_path = PDF_DIR / f"{model}.pdf"
        if not pdf_path.exists():
            continue
        try:
            reader = PdfReader(str(pdf_path))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            specs = extract(text)
            # Reject absurd tiny weights for industrial arms (comma bug leftovers)
            if specs.get("weight_kg") is not None and specs["weight_kg"] < 5 and model not in (
                "MotoMini",
                "SG400",
                "SG650",
                "GP4",
            ):
                # try alternate pattern "1,130 kg" near Weight
                m = re.search(r"Weight[^\n]{0,40}?([\d,]{2,})\s*kg", text, re.I)
                if m:
                    specs["weight_kg"] = float(m.group(1).replace(",", ""))
            results[rid] = {"id": int(rid), "model": model, **specs}
            if specs.get("weight_kg") or specs.get("repeatability_mm"):
                ok += 1
                print(f"OK {rid} {model}: w={specs.get('weight_kg')} r={specs.get('repeatability_mm')}")
            else:
                empty += 1
                print(f"EMPTY {rid} {model}")
        except Exception as e:
            print(f"ERR {rid} {model}: {e}")
    OUT.write_text(json.dumps({"ok": ok, "empty": empty, "specs": results}, indent=2), encoding="utf-8")
    print(f"done ok={ok} empty={empty} -> {OUT}")


if __name__ == "__main__":
    main()
