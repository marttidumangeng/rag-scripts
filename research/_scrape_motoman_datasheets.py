"""Download Motoman datasheet PDFs and extract weight/repeatability."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests
from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0"}
EXTRAS = json.loads(Path("staging/reports/yaskawa-pdp-extras.json").read_text(encoding="utf-8"))
OUT = Path("staging/reports/yaskawa-datasheet-specs.json")
PDF_DIR = Path("staging/tmp/yaskawa-pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)


def extract(text: str) -> dict:
    out = {}
    # Prefer table-style "Weight kg 250" / "Repeatability mm 0.02"
    m = re.search(r"Repeatability\s*mm\s*([\d.]+)", text, re.I)
    if not m:
        m = re.search(r"([\d.]+)\s*mm\s+repeatability", text, re.I)
    if m:
        out["repeatability_mm"] = float(m.group(1))
    m = re.search(r"Weight\s*kg\s*([\d.]+)", text, re.I)
    if not m:
        m = re.search(r"Mass\s*kg\s*([\d.]+)", text, re.I)
    if m:
        out["weight_kg"] = float(m.group(1))
    m = re.search(r"Maximum payload\s*kg\s*([\d.]+)", text, re.I)
    if m:
        out["payload_kg"] = float(m.group(1))
    m = re.search(r"Horizontal reach\s*mm\s*([\d,\.]+)", text, re.I)
    if m:
        out["hor_reach_mm"] = float(m.group(1).replace(",", ""))
    return out


def main() -> None:
    results = {}
    ok = fail = 0
    for rid, entry in EXTRAS["robots"].items():
        pdp = entry.get("pdp_url")
        model = entry.get("model") or ""
        if not pdp:
            fail += 1
            continue
        try:
            html = requests.get(pdp, headers=UA, timeout=40).text
        except Exception as e:
            print("HTML fail", rid, e)
            fail += 1
            continue
        m = re.search(r'href="(/getmedia/[^"]+\.pdf\.aspx)"', html, re.I)
        if not m:
            # try absolute
            m = re.search(r'href="(https://www\.motoman\.com/getmedia/[^"]+\.pdf\.aspx)"', html, re.I)
        if not m:
            print("no pdf", rid, model)
            fail += 1
            continue
        pdf_url = m.group(1)
        if pdf_url.startswith("/"):
            pdf_url = "https://www.motoman.com" + pdf_url
        pdf_path = PDF_DIR / f"{model}.pdf"
        try:
            if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
                raw = requests.get(pdf_url, headers=UA, timeout=90).content
                pdf_path.write_bytes(raw)
            reader = PdfReader(str(pdf_path))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            specs = extract(text)
            results[rid] = {
                "id": int(rid),
                "model": model,
                "pdf_url": pdf_url,
                **specs,
            }
            if specs:
                ok += 1
                print(f"OK {rid} {model}: {specs}")
            else:
                fail += 1
                print(f"EMPTY {rid} {model}")
        except Exception as e:
            fail += 1
            print(f"ERR {rid} {model}: {e}")
        time.sleep(0.1)

    OUT.write_text(json.dumps({"ok": ok, "fail": fail, "specs": results}, indent=2), encoding="utf-8")
    print(f"done ok={ok} fail={fail} -> {OUT}")


if __name__ == "__main__":
    main()
