"""Pre-import verification gate for staged robots.

Scores every staging JSON in a directory with the server's AI verifier BEFORE
`--apply-import`, so a robot whose URL points at a catalog page or whose hero
image shows a sibling model never reaches the admin queue at all.

Outcomes per staged robot:
  - confidence >= min_confidence (default 50)  → stays in place, gets imported
  - confidence <  min_confidence               → file moved to quarantine/ with the
    verification result (scores + model rationale) embedded under "_verification",
    ready for a human to fix and move back
  - unverifiable (page fetch failed / nothing scorable) → stays in place by default
    (bot-walled vendor sites must not block imports), quarantined with --strict

A `_verification_report.json` summarizing every robot is written next to the
staging files either way. Quarantined files are excluded from import because
`import_staging` globs `*.json` non-recursively.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from schema import StagedRobot
from verify_lib import (
    DEFAULT_MODEL,
    gemini_client,
    server_verification,
    verification_flags,
    verify_staged_robot,
)

DEFAULT_MIN_CONFIDENCE = 50
QUARANTINE_DIR_NAME = "quarantine"
REPORT_FILE_NAME = "_verification_report.json"


def _staging_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return [p for p in sorted(target.glob("*.json")) if not p.name.startswith("_")]
    return []


def verify_staging(
    target: Path,
    *,
    company_name: str = "",
    company_website: str = "",
    min_confidence: int = DEFAULT_MIN_CONFIDENCE,
    strict: bool = False,
    quarantine: bool = True,
    model: str = DEFAULT_MODEL,
    delay: float = 1.0,
    timeout: int = 15,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Verify every staged robot under `target`. Returns a summary report dict.

    `quarantine=False` scores and reports without moving files (dry-run of the gate).
    """
    files = _staging_files(target)
    if not files:
        return {"ok": False, "error": f"no staging JSON found at {target}"}

    client = gemini_client()
    if client is None:
        return {
            "ok": False,
            "error": "GEMINI_API_KEY not set — cannot verify; import without the gate or set the key",
        }
    session = session or requests.Session()

    results: list[dict[str, Any]] = []
    passed = quarantined = unverifiable = errors = 0

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        staged = StagedRobot.from_dict(data)
        row: dict[str, Any] = {"file": path.name, "name": staged.name}

        try:
            verification = verify_staged_robot(
                staged,
                client=client,
                session=session,
                company_name=company_name,
                company_website=company_website,
                model=model,
                timeout=timeout,
            )
        except server_verification.VerificationError as exc:
            errors += 1
            row.update({"outcome": "error", "error": str(exc)})
            results.append(row)
            continue

        confidence = verification.get("confidence")
        flags = verification_flags(verification)
        row.update({
            "confidence": confidence,
            "summary": verification.get("summary", ""),
            "dimensions": verification.get("dimensions", {}),
            "flags": [f["flag"] for f in flags],
        })

        if confidence is None:
            # Nothing scorable (usually a bot-walled page). Not the robot's fault —
            # only --strict treats "couldn't check" the same as "checked and failed".
            unverifiable += 1
            row["outcome"] = "unverifiable"
            should_quarantine = strict
        elif confidence < min_confidence:
            row["outcome"] = "quarantined"
            should_quarantine = True
        else:
            passed += 1
            row["outcome"] = "passed"
            should_quarantine = False

        if should_quarantine and quarantine:
            if row["outcome"] != "quarantined":
                row["outcome"] = "quarantined"
            quarantined += 1
            data["_verification"] = verification
            qdir = path.parent / QUARANTINE_DIR_NAME
            qdir.mkdir(exist_ok=True)
            qpath = qdir / path.name
            qpath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            path.unlink()
            row["quarantined_to"] = str(qpath)
        elif should_quarantine:
            # quarantine disabled: report what WOULD move, leave the file alone
            row["outcome"] = "would_quarantine"

        results.append(row)
        if delay:
            time.sleep(delay)

    report = {
        "ok": True,
        "target": str(target),
        "min_confidence": min_confidence,
        "strict": strict,
        "quarantine": quarantine,
        "counts": {
            "total": len(files),
            "passed": passed,
            "quarantined": quarantined,
            "unverifiable": unverifiable,
            "errors": errors,
        },
        "results": results,
    }

    report_dir = target if target.is_dir() else target.parent
    (report_dir / REPORT_FILE_NAME).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report
