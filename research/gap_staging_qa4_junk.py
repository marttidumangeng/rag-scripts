"""QA round 4: drop robots whose names are clearly not products.

The CJK translation pass (QA3) revealed some staged "robots" are actually blog
posts, news items, or category pages (e.g. "Introduction to Anti-Counterfeit
Measures", "AGV vs AMR: What's the Difference?"). This pass drops robots whose
name matches article/news/question patterns.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STAGED = Path(__file__).resolve().parent / "staging" / "gap_discovery" / "staged_import.json"

JUNK_RE = re.compile(
    r"(\?$"                                # questions
    r"|^\d{4}[./-]\d{1,2}[./-]\d{1,2}"     # leading dates
    r"|\b(introduction to|how to|what is|guide to|vs\.?|difference|news|blog|"
    r"exhibition|trade show|catalog(ue)? download|press release|notice|"
    r"announcement|faq|about us|contact|privacy|terms)\b)",
    re.I,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(STAGED.read_text(encoding="utf-8"))
    robots = data["robots"]
    kept, dropped = [], []
    for r in robots:
        name = (r.get("name") or "").strip()
        if JUNK_RE.search(name) or len(name) > 90:
            dropped.append(name)
            continue
        kept.append(r)

    print(f"robots: {len(robots)} -> {len(kept)} (dropped {len(dropped)})")
    print("dropped sample:", dropped[:15])
    if args.dry_run:
        return

    data["robots"] = kept
    data["robot_count"] = len(kept)
    data.setdefault("qa_dropped", {})["qa4_article_junk"] = dropped
    STAGED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {STAGED}")


if __name__ == "__main__":
    main()
