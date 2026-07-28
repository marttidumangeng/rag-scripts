"""Parse HDC API dump with UTF-8 stdout."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

raw = json.loads(
    Path(
        r"C:\Users\tramk\.cursor\projects\c-Github-Personal-robot-ai-geek\agent-tools\4836a817-8527-4ccb-8d3c-c772c207a1b3.txt"
    ).read_text(encoding="utf-8")
)
for item in raw["data"]["content"]:
    bd = item.get("bdContent") or {}
    atts = bd.get("attachments") or []
    att = atts[0] if atts else bd.get("bdcThumbFile1")
    print("---")
    print(item.get("prdSeq"), repr(item.get("prdNm")))
    print("payload", item.get("prdBscSpec1"), "reach", item.get("prdBscSpec2"))
    print("fileSeq", (att or {}).get("fileSeq"), "ori", repr((att or {}).get("fileOriNm")))
    print("link", ((att or {}).get("fileDwLink") or "")[:200])
    print("n_atts", len(atts))
    for a in atts:
        print(" ", a.get("fileSeq"), repr(a.get("fileOriNm")), "link_len", len(a.get("fileDwLink") or ""))
