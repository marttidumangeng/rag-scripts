"""Close the 144-lead / 37-company gap: LLM-approved leads for companies that
ALREADY had some robots imported (main run or earlier recovery pass), which
recover_backlog_via_llm.py deliberately skipped to avoid re-processing
already-done companies.

One of the 37 (mirax-robots) is a genuinely PRE-EXISTING prod company, not
one created this session — its leads need the same duplicate check as the
other 36.

Duplicate protection: the server's bulk-import endpoint already dedupes by
canonicalized name SCOPED TO THE SAME COMPANY (Robot.objects.filter(
Q(dedupe_name_key=...) | Q(name__iexact=...), company_ref=company)) and
skips instead of creating a duplicate row when update_existing is not set
(the default, and what import_staging uses here). This script additionally
does an explicit pre-check against each company's CURRENT prod robot list
and logs what it filters, for transparency — not because the server needs
the help, but because "check for duplicates" was an explicit ask.
"""
from __future__ import annotations

import json
import re
import sys
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
GAP_SLUGS_FILE = Path(
    r"C:\Users\tramk\AppData\Local\Temp\claude\C--Github-Personal-robot-ai-geek"
    r"\786ea426-ae3c-46be-92f8-bec9582fc8c2\scratchpad\gap37_slugs.json"
)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def main() -> None:
    d = json.loads(STAGED_FILE.read_text(encoding="utf-8"))
    companies = {c["slug"]: c for c in d["companies"]}
    robots_by_slug: dict[str, list[dict[str, Any]]] = {}
    for r in d["robots"]:
        robots_by_slug.setdefault(r["company_slug"], []).append(r)

    classification = json.loads(CLASSIFICATION_FILE.read_text(encoding="utf-8"))
    gap_slugs = json.loads(GAP_SLUGS_FILE.read_text(encoding="utf-8"))

    ledger = d.setdefault("import_ledger", {"note": "", "imported": [], "skipped": []})
    ledger.setdefault("imported", [])
    ledger.setdefault("skipped", [])

    client = ResearchApiClient()
    sess = requests.Session()

    n_created_co = 0
    n_created_robots = 0
    n_dup_filtered = 0
    n_skipped = 0
    n_errors = 0

    print(f"=== Gap-37 recovery: {len(gap_slugs)} companies queued ===", flush=True)

    for i, slug in enumerate(gap_slugs, 1):
        company = companies.get(slug)
        if not company:
            continue
        approved_names = {it["n"] for it in classification[slug] if it.get("k")}
        raw_robots = [r for r in robots_by_slug.get(slug, []) if r.get("name") in approved_names]
        if not raw_robots:
            continue

        try:
            # Explicit duplicate pre-check against the company's CURRENT prod
            # robot list (transparency layer on top of the server's own
            # canonicalized-name+company-scoped dedupe).
            hits = client.search_companies(company["name"], page_size=5)
            prod_match = next(
                (h for h in hits if norm(h.get("name", "")) == norm(company["name"])), None
            )
            existing_names: set[str] = set()
            if prod_match:
                existing_robots = client.list_robots_for_company(prod_match["id"])
                existing_names = {norm(r.get("name", "")) for r in existing_robots}

            pre_filtered = []
            for r in raw_robots:
                if norm(r.get("name", "")) in existing_names:
                    n_dup_filtered += 1
                    print(f"  [dup-skip] {company['name']}: \"{r['name']}\" already exists on prod", flush=True)
                    continue
                pre_filtered.append(r)

            if not pre_filtered:
                ledger["skipped"].append({"slug": slug, "reason": "all_leads_already_on_prod"})
                n_skipped += 1
                print(f"[{i}/{len(gap_slugs)}] {company['name']}: SKIP (all {len(raw_robots)} leads already exist)", flush=True)
                continue

            enriched = b.enrich_company_robots_llm_approved(pre_filtered, company, sess)

            if not enriched:
                ledger["skipped"].append({"slug": slug, "reason": "gap37_no_valid_content"})
                n_skipped += 1
                print(f"[{i}/{len(gap_slugs)}] {company['name']}: SKIP (0 valid after content filters)", flush=True)
                continue

            co_dir = ROBOTS_DIR / f"{slug}-gap37"
            co_dir.mkdir(parents=True, exist_ok=True)
            for old in co_dir.glob("*.json"):
                old.unlink()
            used_names: set[str] = set()
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
                print(f"[{i}/{len(gap_slugs)}] {company['name']}: SKIP (dry-run failed: "
                      f"{dry.get('errors', ['?'])[0][:100]})", flush=True)
                continue

            result = import_staging(co_dir, dry_run=False)
            created_ids = [r["id"] for r in result.get("results", []) if r.get("action") == "created"]
            server_skipped = [r for r in result.get("results", []) if r.get("action") == "skipped"]
            errored = [r for r in result.get("results", []) if r.get("action") == "error"]

            if server_skipped:
                print(f"  [server dedupe] {company['name']}: server also skipped "
                      f"{len(server_skipped)} as existing: "
                      f"{[r.get('name') for r in server_skipped]}", flush=True)

            if created_ids:
                n_created_co += 1
                n_created_robots += len(created_ids)
                ledger["imported"].append({
                    "slug": slug,
                    "prod_company_name": company["name"],
                    "robots": len(created_ids),
                    "robot_ids": created_ids,
                    "date": "2026-08-01",
                    "mode": "gap37_recovery_pass",
                })
                print(f"[{i}/{len(gap_slugs)}] {company['name']}: created {len(created_ids)} robots "
                      f"({', '.join(str(x) for x in created_ids)})"
                      + (f"; {len(server_skipped)} server-deduped" if server_skipped else "")
                      + (f"; {len(errored)} errored" if errored else ""), flush=True)
            else:
                if server_skipped and not errored:
                    n_skipped += 1
                    print(f"[{i}/{len(gap_slugs)}] {company['name']}: all leads were server-side duplicates", flush=True)
                else:
                    n_errors += 1
                    ledger["skipped"].append({
                        "slug": slug, "reason": "apply_created_nothing",
                        "errors": [e.get("error", "") for e in errored][:5],
                    })
                    print(f"[{i}/{len(gap_slugs)}] {company['name']}: ERROR — created 0 "
                          f"({errored[0].get('error', '?')[:120] if errored else 'unknown'})", flush=True)

        except Exception as exc:  # noqa: BLE001
            n_errors += 1
            ledger["skipped"].append({"slug": slug, "reason": "exception", "error": str(exc)[:200]})
            print(f"[{i}/{len(gap_slugs)}] {slug}: EXCEPTION {str(exc)[:150]}", flush=True)

        if i % 10 == 0 or i == len(gap_slugs):
            STAGED_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"--- checkpoint {i}/{len(gap_slugs)}: {n_created_co} companies / "
                  f"{n_created_robots} robots created, {n_dup_filtered} pre-filtered dups, "
                  f"{n_skipped} skipped, {n_errors} errors ---", flush=True)

    STAGED_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"=== DONE: {n_created_co} companies / {n_created_robots} robots created, "
          f"{n_dup_filtered} pre-filtered duplicates, {n_skipped} skipped, "
          f"{n_errors} errors ===", flush=True)


if __name__ == "__main__":
    main()
