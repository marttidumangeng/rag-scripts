#!/usr/bin/env python3
"""Count stored quality_flags on KUKA pending_review (incl. AI verify chips)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

COMPANY_ID = 1396
OUT = Path("staging/reports/kuka-1396-stored-flags.json")


def main() -> int:
    c = ResearchApiClient()
    pending = []
    page = 1
    while True:
        data = c._get(
            "robots/robots/",
            params={
                "company_ref": COMPANY_ID,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        pending.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1

    err_c = Counter()
    warn_c = Counter()
    with_err = []
    samples = {"url_content_mismatch": [], "content_contradiction": [], "image_mismatch": []}

    for r in pending:
        flags = r.get("quality_flags") or []
        if not isinstance(flags, list):
            continue
        errs = [f for f in flags if isinstance(f, dict) and f.get("severity") == "error"]
        warns = [f for f in flags if isinstance(f, dict) and f.get("severity") == "warn"]
        for f in errs:
            err_c[f.get("flag")] += 1
        for f in warns:
            warn_c[f.get("flag")] += 1
        if errs:
            with_err.append(
                {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "errors": [
                        {"flag": f.get("flag"), "detail": (f.get("detail") or "")[:120]}
                        for f in errs
                    ],
                    "url": (r.get("url") or "")[:100],
                }
            )
        for key in samples:
            hit = next((f for f in flags if isinstance(f, dict) and f.get("flag") == key), None)
            if hit and len(samples[key]) < 5:
                samples[key].append(
                    {
                        "id": r.get("id"),
                        "name": r.get("name"),
                        "detail": (hit.get("detail") or "")[:160],
                        "url": (r.get("url") or "")[:90],
                    }
                )

    report = {
        "pending": len(pending),
        "with_errors": len(with_err),
        "error_counts": dict(err_c.most_common()),
        "warn_counts": dict(warn_c.most_common(20)),
        "samples": samples,
        "error_robots": with_err[:40],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"pending={len(pending)} with_errors={len(with_err)}")
    print("ERRORS:", dict(err_c.most_common()))
    print("top WARNs:", dict(warn_c.most_common(12)))
    print("samples url_mismatch:", json.dumps(samples["url_content_mismatch"], indent=2)[:800])
    print("samples contradiction:", json.dumps(samples["content_contradiction"], indent=2)[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
