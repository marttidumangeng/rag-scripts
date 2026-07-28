"""Rebuild a clean executive morning report from session JSONL + queue."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

QUEUE = _RESEARCH / "staging" / "reports" / "us-overnight-queue.json"
PROGRESS = _RESEARCH / "staging" / "reports" / "us-overnight-progress.json"
SESSION = _RESEARCH / "staging" / "reports" / "us-overnight-session.jsonl"
REPORT = _RESEARCH / "docs" / "reports" / "us-overnight-morning-report.md"
DONE = _RESEARCH / "state" / "content_queue_done.json"


def main() -> int:
    queue = json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.is_file() else {}
    progress = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.is_file() else {}
    done = json.loads(DONE.read_text(encoding="utf-8")) if DONE.is_file() else {}
    sessions = []
    if SESSION.is_file():
        for line in SESSION.read_text(encoding="utf-8").splitlines():
            if line.strip():
                sessions.append(json.loads(line))

    us = [c for c in (queue.get("companies") or []) if (c.get("country") or "").upper() == "US"]
    us = [c for c in us if c["company_id"] != 375]  # Brightpick CZ

    lines = [
        "---",
        "type: log",
        "title: US Overnight Discover — Morning Report",
        "status: draft",
        "version: 1.1",
        "owner: AI",
        f"last_updated: {datetime.now(timezone.utc).date().isoformat()}",
        "tags:",
        "  - content-queue",
        "  - overnight",
        "  - us-drain",
        "---",
        "",
        "# US Overnight Discover — Morning Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Executive summary",
        "",
        f"- Content-queue done set: **{len(done.get('companies') or [])}** companies",
        f"- Explicit-US companies still with pending (excl. Brightpick CZ): **{len(us)}**",
        f"- Explicit-US pending robots: **{sum(c.get('pending') or 0 for c in us)}**",
        f"- Overnight soft-pass companies: **{len(progress.get('companies') or [])}**",
        f"- Session enrich records: **{len(sessions)}**",
        "",
        "### Cleared this session (stakeholder + cleanup)",
        "",
        "| Company | ID | Notes |",
        "|---------|---:|-------|",
        "| Bluefin Robotics (GDMS) | 160 | Approved BF-9/12/HAUV; BF-21 EN soft-fill; rejected 5044 |",
        "| NASA | 174 | Rejected 22 Xiaomi/CyberDog misfiles → 0 pending |",
        "| SMP Robotics | 212 | Approved earlier same day |",
        "| Ekso Bionics | 147 | Approved earlier same day |",
        "",
        "### Explicit-US remaining queue",
        "",
        "| Pending | ID | Company | Website |",
        "|--------:|---:|---------|---------|",
    ]
    for c in sorted(us, key=lambda x: (-(x.get("pending") or 0), x.get("name") or "")):
        lines.append(
            f"| {c.get('pending')} | {c['company_id']} | {c.get('name')} | {c.get('website') or '—'} |"
        )

    lines.extend(
        [
            "",
            "## Company → website → robots (explicit US)",
            "",
        ]
    )
    for c in sorted(us, key=lambda x: x.get("name") or ""):
        lines.append(f"### {c.get('name')} ({c['company_id']})")
        lines.append("")
        lines.append(f"- Website: {c.get('website') or '—'}")
        lines.append(f"- Pending (snapshot): {c.get('pending')}")
        lines.append("")
        for r in c.get("robots") or []:
            lines.append(f"- `{r.get('id')}` {r.get('name')} — {r.get('url') or '(no url)'}")
        lines.append("")

    lines.extend(
        [
            "## Overnight soft-pass results",
            "",
            "| Company | ID | Pending processed | OEM links crawled |",
            "|---------|---:|------------------:|------------------:|",
        ]
    )
    for p in progress.get("companies") or []:
        lines.append(
            f"| {p.get('name')} | {p.get('company_id')} | {p.get('pending')} | {p.get('oem_links')} |"
        )

    lines.extend(
        [
            "",
            "## Deep enrich session log",
            "",
            "_(Curated discover scripts append below as overnight agents finish.)_",
            "",
            "## Data files",
            "",
            "- Queue snapshot: `staging/reports/us-overnight-queue.json`",
            "- Soft-pass progress: `staging/reports/us-overnight-progress.json`",
            "- Session JSONL: `staging/reports/us-overnight-session.jsonl`",
            "",
            "## Related",
            "",
            "- [approve-publish-status.md](../checklists/approve-publish-status.md)",
            "- [log.md](../log.md)",
            "",
        ]
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
