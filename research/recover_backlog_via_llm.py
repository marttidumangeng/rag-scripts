"""Import the LLM-classified recovery set from the 3,177-lead backlog.

The strong-signal gate in bulk_import_remaining_gaps.py deliberately trades
recall for precision (requires a digit/trademark/mixed-case/singular-robot-
word/brand-prefix in the NAME). That's the right default for a fully
unattended run, but it leaves ~3,200 leads unprocessed — many of them real
products with plain names (person-named service robots, coined brand words
in plain Title Case) that the structural signal can't distinguish from
generic vertical/nav junk of the same shape.

This script processes that backlog using batch LLM classification (16 Agent
calls covering all 452 backlog companies, cross-validated during
development against known-good/known-bad examples) instead of more regex.
The classification replaces ONLY the name-gate (`is_probable_product_name`);
every other content-quality backstop from the main pipeline still applies —
description-required, duplicate-boilerplate detection, marketplace-template
detection, marketing-voice detection, category-description detection,
mojibake detection. An LLM-approved lead with no real page content, or with
templated/marketing prose, still gets dropped.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402
from import_staging import import_staging  # noqa: E402
import bulk_import_remaining_gaps as b  # noqa: E402

STAGED_FILE = _HERE / "staging" / "gap_discovery" / "staged_import.json"
ROBOTS_DIR = _HERE / "staging" / "gap_discovery" / "robots"
CLASSIFICATION_FILE = Path(
    r"C:\Users\tramk\AppData\Local\Temp\claude\C--Github-Personal-robot-ai-geek"
    r"\786ea426-ae3c-46be-92f8-bec9582fc8c2\scratchpad\merged_classification.json"
)


def main() -> None:
    d = json.loads(STAGED_FILE.read_text(encoding="utf-8"))
    companies = {c["slug"]: c for c in d["companies"]}
    robots_by_slug: dict[str, list[dict[str, Any]]] = {}
    for r in d["robots"]:
        robots_by_slug.setdefault(r["company_slug"], []).append(r)

    classification = json.loads(CLASSIFICATION_FILE.read_text(encoding="utf-8"))

    ledger = d.setdefault("import_ledger", {"note": "", "imported": [], "skipped": []})
    ledger.setdefault("imported", [])
    ledger.setdefault("skipped", [])
    # Companies already holding >=1 robot from the main run must be skipped
    # (avoid double-importing what already landed). Every OTHER ledger entry
    # (0-robot "imported" rows, and "skipped" rows for
    # no_valid_robots_after_filter/dry_run_failed/apply_created_nothing/
    # exception) is exactly the backlog this pass exists to reprocess — that
    # ledger state is WHY these companies have agent-approved leads waiting.
    # Only name_now_in_prod / research_institute_not_manufacturer represent a
    # genuine "this company should never be imported" verdict.
    has_robots_slugs = {e["slug"] for e in ledger["imported"] if e.get("robots", 0) > 0}
    permanently_excluded = {
        e["slug"] for e in ledger.get("skipped", [])
        if e.get("reason") in ("name_now_in_prod", "research_institute_not_manufacturer")
    }
    already_recovered = {
        e["slug"] for e in ledger["imported"] if e.get("mode") == "llm_recovery_pass"
    }

    todo = [
        slug for slug, items in classification.items()
        if any(it.get("k") for it in items)
        and slug not in has_robots_slugs
        and slug not in permanently_excluded
        and slug not in already_recovered
    ]
    print(f"=== LLM-recovery import: {len(todo)} companies queued ===", flush=True)

    # Drop stale 0-robot/skip entries for companies we're about to reprocess,
    # so each slug ends up with exactly one ledger entry reflecting reality.
    todo_set = set(todo)
    ledger["imported"] = [e for e in ledger["imported"] if e["slug"] not in todo_set]
    ledger["skipped"] = [e for e in ledger["skipped"] if e["slug"] not in todo_set]

    client = ResearchApiClient()
    sess = requests.Session()

    n_created_co = 0
    n_created_robots = 0
    n_skipped = 0
    n_errors = 0

    for i, slug in enumerate(todo, 1):
        company = companies.get(slug)
        if not company:
            continue
        approved_names = {it["n"] for it in classification[slug] if it.get("k")}
        raw_robots = [r for r in robots_by_slug.get(slug, []) if r.get("name") in approved_names]
        if not raw_robots:
            continue

        try:
            enriched = b.enrich_company_robots_llm_approved(raw_robots, company, sess)

            if not enriched:
                ledger["skipped"].append({"slug": slug, "reason": "llm_approved_but_no_valid_content"})
                n_skipped += 1
                print(f"[{i}/{len(todo)}] {company['name']}: SKIP (0 valid after content filters)", flush=True)
                continue

            co_dir = ROBOTS_DIR / slug
            co_dir.mkdir(parents=True, exist_ok=True)
            for old in co_dir.glob("*.json"):
                old.unlink()
            used_names: set[str] = set()
            import re
            for r in enriched:
                base = re.sub(r"[^a-z0-9]+", "-", r["name"].lower()).strip("-")[:60] or "robot"
                fn = base
                n = 2
                while fn in used_names:
                    fn = f"{base}-{n}"
                    n += 1
                used_names.add(fn)
                (co_dir / f"{fn}.json").write_text(
                    json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8"
                )

            dry = import_staging(co_dir, dry_run=True)
            if not dry.get("ok"):
                ledger["skipped"].append({
                    "slug": slug, "reason": "dry_run_failed",
                    "errors": dry.get("errors", [])[:5],
                })
                n_skipped += 1
                print(f"[{i}/{len(todo)}] {company['name']}: SKIP (dry-run failed: "
                      f"{dry.get('errors', ['?'])[0][:100]})", flush=True)
                continue

            result = import_staging(co_dir, dry_run=False)
            created_ids = [r["id"] for r in result.get("results", []) if r.get("action") == "created"]
            errored = [r for r in result.get("results", []) if r.get("action") == "error"]

            if created_ids:
                n_created_co += 1
                n_created_robots += len(created_ids)
                ledger["imported"].append({
                    "slug": slug,
                    "prod_company_name": company["name"],
                    "robots": len(created_ids),
                    "robot_ids": created_ids,
                    "date": "2026-07-31",
                    "mode": "llm_recovery_pass",
                })
                print(f"[{i}/{len(todo)}] {company['name']}: created {len(created_ids)} robots "
                      f"({', '.join(str(x) for x in created_ids)})"
                      + (f"; {len(errored)} errored" if errored else ""), flush=True)
            else:
                n_errors += 1
                ledger["skipped"].append({
                    "slug": slug, "reason": "apply_created_nothing",
                    "errors": [e.get("error", "") for e in errored][:5],
                })
                print(f"[{i}/{len(todo)}] {company['name']}: ERROR — created 0 "
                      f"({errored[0].get('error', '?')[:120] if errored else 'unknown'})", flush=True)

        except Exception as exc:  # noqa: BLE001
            n_errors += 1
            ledger["skipped"].append({"slug": slug, "reason": "exception", "error": str(exc)[:200]})
            print(f"[{i}/{len(todo)}] {slug}: EXCEPTION {str(exc)[:150]}", flush=True)

        if i % 10 == 0 or i == len(todo):
            STAGED_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"--- checkpoint {i}/{len(todo)}: {n_created_co} companies / "
                  f"{n_created_robots} robots created, {n_skipped} skipped, "
                  f"{n_errors} errors ---", flush=True)

    STAGED_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"=== DONE: {n_created_co} companies / {n_created_robots} robots created, "
          f"{n_skipped} skipped, {n_errors} errors ===", flush=True)


if __name__ == "__main__":
    main()
