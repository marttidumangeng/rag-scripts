"""One-off: parse fetched OEM product API page dumps. Do not import in prod."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

TOOL_DIR = Path(r"C:\Users\tramk\.cursor\projects\c-Github-Personal-robot-ai-geek\agent-tools")
OUT = Path(__file__).resolve().parent / "_hyundai_catalog_dump.json"

files = sorted(TOOL_DIR.glob("*.txt"))
products: list[dict] = []
seen: set[int] = set()
for f in files:
    try:
        text = f.read_text(encoding="utf-8")
        if '"prdNm"' not in text or '"resCd"' not in text:
            continue
        raw = json.loads(text)
    except Exception:
        continue
    data = raw.get("data") or raw
    for item in data.get("content") or []:
        seq = item.get("prdSeq")
        if seq in seen:
            continue
        seen.add(seq)
        bd = item.get("bdContent") or {}
        atts = bd.get("attachments") or []
        att0 = atts[0] if atts else bd.get("bdcThumbFile1")
        products.append(
            {
                "prdSeq": seq,
                "prdNm": (item.get("prdNm") or "").replace("\r", "").strip(),
                "prdTypeCd": item.get("prdTypeCd"),
                "payload": item.get("prdBscSpec1"),
                "reach": str(item.get("prdBscSpec2") or "").replace(",", ""),
                "fileSeq": (att0 or {}).get("fileSeq") if isinstance(att0, dict) else None,
                "fileDwLink": (att0 or {}).get("fileDwLink") if isinstance(att0, dict) else None,
                "fileOriNm": (att0 or {}).get("fileOriNm") if isinstance(att0, dict) else None,
                "atts": [
                    {
                        "fileSeq": a.get("fileSeq"),
                        "fileOriNm": a.get("fileOriNm"),
                        "fileDwLink": a.get("fileDwLink"),
                    }
                    for a in atts
                ],
            }
        )

print("UNIQUE", len(products))
print("TYPES", Counter(p["prdTypeCd"] for p in products))
print("--- ALL ---")
for p in sorted(products, key=lambda x: (x["prdTypeCd"] or "", x["prdNm"])):
    print(
        f"{p['prdSeq']:3} {p['prdTypeCd']} {p['prdNm'][:55]:55} "
        f"fileSeq={p['fileSeq']} ori={p['fileOriNm']}"
    )

print("\n=== FOCUS ===")
for p in products:
    nm = p["prdNm"].upper()
    if any(k in nm for k in ("HDC", "HC", "HH050", "HDR50", "FPD", "HH020", "HH7", "HDF7")):
        print(json.dumps({k: p[k] for k in ("prdSeq", "prdNm", "prdTypeCd", "payload", "reach", "fileSeq", "fileOriNm")}, ensure_ascii=False))
        print("  link:", (p["fileDwLink"] or "")[:140])
        print("  atts:", [(a["fileSeq"], a["fileOriNm"]) for a in p["atts"]])

OUT.write_text(json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")
print("SAVED", OUT)
