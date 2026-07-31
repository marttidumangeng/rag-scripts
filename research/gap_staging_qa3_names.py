"""QA round 3: clean non-English robot names in staged_import.json.

A handful of robots staged during the early smoke batch (before the Gemini
screening was added to Stage E) carry Japanese/Chinese/Korean names. This pass
finds robot names with CJK characters and asks Gemini to produce the official
English/romanized product name, updating name/model_name/family_name in place.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from load_env import load_research_env  # noqa: E402

load_research_env()

from google import genai  # noqa: E402

STAGED = _HERE / "staging" / "gap_discovery" / "staged_import.json"

CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")

PROMPT = """These are robot product names scraped from manufacturer websites, some in
Japanese/Chinese/Korean. For each, give the official English or romanized
product name (as the manufacturer uses internationally). Keep model numbers.
E.g. "KXRシリーズ" -> "KXR Series". If unsure, romanize sensibly.

Return STRICT JSON object mapping original -> cleaned, no markdown fences.

NAMES:
"""


def main() -> None:
    data = json.loads(STAGED.read_text(encoding="utf-8"))
    robots = data["robots"]
    targets = sorted({r["name"] for r in robots if CJK_RE.search(r.get("name") or "")})
    print(f"robots with CJK names: {len(targets)}")
    if not targets:
        return

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    mapping: dict[str, str] = {}
    for i in range(0, len(targets), 40):
        chunk = targets[i:i + 40]
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=PROMPT + json.dumps(chunk, ensure_ascii=False),
                )
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.text or "").strip(), flags=re.S)
                mapping.update(json.loads(raw))
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  chunk {i}: attempt {attempt + 1} failed: {exc}")
                time.sleep(5)

    changed = 0
    for r in robots:
        old = r.get("name") or ""
        new = (mapping.get(old) or "").strip()
        if new and new != old:
            r["name"] = new
            if r.get("model_name") == old:
                r["model_name"] = new
            if r.get("family_name") == old:
                r["family_name"] = new
            note = r.get("research_notes") or ""
            r["research_notes"] = note + f" [QA3] Name translated from '{old}'."
            changed += 1

    print(f"renamed {changed} robots")
    for k, v in list(mapping.items())[:10]:
        print(f"  {k} -> {v}")

    STAGED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {STAGED}")


if __name__ == "__main__":
    main()
