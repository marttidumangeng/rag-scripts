#!/usr/bin/env python3
"""Preflight health check for the RobotAIGeek Manus pipelines.

Run this as the FIRST command of any run. It answers one question with an
exit code: is everything this run needs actually present and usable? It
never fixes anything and never touches the network.

    python3 preflight_check.py --pipeline daily
    python3 preflight_check.py --pipeline topic \
        --calendar ../ARPI_Content_Calendar_Strategy_v6.xlsx
    python3 preflight_check.py --pipeline daily --json

Exit 0 = ready to run (warnings allowed).
Exit 1 = BLOCKING: something required is missing or unusable. Do not run
         the pipeline; do not improvise replacements. Report and fix.

Stdlib only, so it works even when optional dependencies are missing.
"""
import argparse
import importlib
import json
import os
import sys
from pathlib import Path

MANIFESTS = {
    "daily": {
        "scripts": ["scan_due_sources.py", "dedup_check.py",
                    "package_lint.py", "validate_registry.py"],
        "data": ["registry_v4_20260805.csv"],
        "dirs": ["state", "out"],
        "modules": [],
    },
    "topic": {
        "scripts": ["assignment_lookup.py", "market_ledger_seed.py",
                    "article_lint.py", "build_docx.py"],
        "data": ["registry_v4_20260805.csv"],
        "dirs": ["heroes", "scan_history"],
        "modules": [("openpyxl", "assignment_lookup.py"),
                    ("docx", "build_docx.py (pip3 install python-docx)")],
    },
}


def check_writable(path):
    probe = Path(path) / ".preflight_write_test"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def count_unbaselined(root):
    """Sources in the registry with no completed first fetch."""
    state_file = root / "state" / "scan_state.json"
    registry = root / "registry_v4_20260805.csv"
    if not state_file.exists() or not registry.exists():
        return None, None
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    import csv
    urls = set()
    with open(registry, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            u = (r.get("url_news") or "").strip()
            if u:
                urls.add(u)
    unbaselined = sum(
        1 for u in urls
        if not state.get(u, {}).get("link_hashes")
        and not state.get(u, {}).get("seen_rss"))
    return unbaselined, len(urls)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", choices=list(MANIFESTS), required=True)
    ap.add_argument("--root", default=".",
                    help="pipeline directory (default: current directory)")
    ap.add_argument("--calendar", help="topic pipeline: calendar workbook path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    man = MANIFESTS[args.pipeline]
    errors, warnings, info = [], [], {}

    info["pipeline"] = args.pipeline
    info["root"] = str(root)
    info["python"] = sys.version.split()[0]

    if not root.is_dir():
        errors.append(f"pipeline directory does not exist: {root}")
        report(info, errors, warnings, args.json)

    # 1. the directory must persist: warn loudly if it looks sandbox-local
    if str(root).startswith("/home/ubuntu") and "/projects/" not in str(root):
        errors.append(
            f"{root} is under the ephemeral sandbox home. Install into the "
            "PROJECT shared-file directory (/home/ubuntu/projects/<project>/"
            "...) or everything here is lost on the next run.")

    # 2. required files
    for name in man["scripts"] + man["data"]:
        p = root / name
        if not p.exists():
            errors.append(f"missing required file: {name}")
        elif p.stat().st_size == 0:
            errors.append(f"required file is empty: {name}")

    # 3. required directories (created if absent, that is not an error)
    for d in man["dirs"]:
        p = root / d
        if not p.exists():
            try:
                p.mkdir(parents=True)
                warnings.append(f"created missing directory: {d}/")
            except OSError as e:
                errors.append(f"cannot create required directory {d}/: {e}")

    # 4. writability
    if not check_writable(root):
        errors.append(f"pipeline directory is not writable: {root}")

    # 5. optional module dependencies
    for mod, why in man["modules"]:
        try:
            importlib.import_module(mod)
        except ImportError:
            errors.append(f"missing python module {mod!r}, required by {why}")

    # 6. pipeline-specific state checks
    if args.pipeline == "daily":
        state = root / "state" / "scan_state.json"
        log = root / "state" / "published_log.jsonl"
        if not state.exists():
            warnings.append(
                "state/scan_state.json missing: no scan baseline yet. Run "
                "scan_due_sources.py --force-all before trusting coverage.")
        else:
            un, total = count_unbaselined(root)
            info["sources_total"] = total
            info["sources_unbaselined"] = un
            if un and total and un > total * 0.25:
                warnings.append(
                    f"{un} of {total} sources have no baseline and cannot "
                    "produce candidates. Run with --force-all "
                    "--missing-baseline-only until the count stops falling.")
        if not log.exists():
            warnings.append(
                "state/published_log.jsonl missing: dedup has no memory. "
                "Seed it before the first run.")
        else:
            n = sum(1 for line in log.read_text(encoding="utf-8").splitlines()
                    if line.strip())
            info["dedup_log_entries"] = n
            if n == 0:
                warnings.append("published_log.jsonl is empty (dedup blind)")

    if args.pipeline == "topic":
        if args.calendar:
            cal = Path(args.calendar)
            if not cal.exists():
                errors.append(f"calendar workbook not found: {cal}")
            else:
                info["calendar"] = str(cal.resolve())
        else:
            warnings.append(
                "no --calendar given; pass it so the check can confirm the "
                "workbook the run will read")
        heroes = root / "heroes"
        if heroes.is_dir():
            n = len([p for p in heroes.iterdir() if p.is_file()])
            info["heroes_archived"] = n
            if n == 0:
                warnings.append(
                    "heroes/ is empty: hero differentiation will need up to "
                    "3 page fetches this run, then the archive fills up.")
        hist = root / "scan_history"
        if hist.is_dir():
            n = len(list(hist.glob("scan_delta_*.json")))
            info["scan_delta_files"] = n
            if n == 0:
                warnings.append(
                    "scan_history/ has no scan deltas: ledger seed runs in "
                    "RSS-only mode (expected unless deltas were copied over).")

    report(info, errors, warnings, args.json)


def report(info, errors, warnings, as_json):
    ok = not errors
    if as_json:
        print(json.dumps({"ok": ok, "info": info, "errors": errors,
                          "warnings": warnings}, indent=1))
    else:
        for k, v in info.items():
            print(f"  {k}: {v}")
        for e in errors:
            print(f"  ERROR   {e}")
        for w in warnings:
            print(f"  warning {w}")
        print(f"PREFLIGHT: {'READY' if ok else 'BLOCKED'} "
              f"({len(errors)} errors, {len(warnings)} warnings)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
