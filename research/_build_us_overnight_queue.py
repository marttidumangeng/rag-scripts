"""Build remaining US content-queue company list for overnight drain.

Writes:
  staging/reports/us-overnight-queue.json
  docs/reports/us-overnight-morning-report.md  (skeleton)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

DONE_PATH = _RESEARCH / "state" / "content_queue_done.json"
OUT = _RESEARCH / "staging" / "reports" / "us-overnight-queue.json"
REPORT = _RESEARCH / "docs" / "reports" / "us-overnight-morning-report.md"


def main() -> int:
    c = ResearchApiClient()
    done = set(json.loads(DONE_PATH.read_text(encoding="utf-8")).get("companies") or [])
    hits: list[dict] = []
    page = 1
    while page <= 80:
        data = c._get("companies/", params={"page": page, "page_size": 100})
        results = data.get("results") or []
        if not results:
            break
        for co in results:
            cid = co.get("id")
            if not cid or cid in done:
                continue
            country = co.get("country") or {}
            code = (country.get("code") if isinstance(country, dict) else "") or ""
            # Include explicit US; also null-country companies with US website TLD heuristics later
            if code and code.upper() != "US":
                continue
            if not code:
                # skip non-US null only if we can detect; keep null for US-first sweep
                # Prefer those with .com and pending — still include null-country for US drain
                pass
            pr = c._get(
                "robots/robots/",
                params={"company_ref": cid, "status": "pending_review", "page_size": 1},
            )
            cnt = int(pr.get("count") or 0) if isinstance(pr, dict) else 0
            if cnt <= 0:
                continue
            # For null country, only keep if website looks US OEM or name known — keep all null with pending for overnight
            # but flag country_uncertain
            uncertain = not code
            full = c._get(
                "robots/robots/",
                params={
                    "company_ref": cid,
                    "status": "pending_review",
                    "page_size": 50,
                },
            )
            robots = []
            for r in full.get("results") or []:
                robots.append(
                    {
                        "id": r.get("id"),
                        "name": r.get("name"),
                        "url": r.get("url"),
                        "status": r.get("status"),
                    }
                )
            hits.append(
                {
                    "company_id": cid,
                    "name": co.get("name"),
                    "website": co.get("website") or "",
                    "country": code or "?",
                    "country_uncertain": uncertain,
                    "pending": cnt,
                    "robots": robots,
                }
            )
            print(
                f"HIT {cnt:3d}  {cid:5d}  {(code or '?'):3}  "
                f"{(co.get('name') or '')[:38]:38}  {(co.get('website') or '')[:45]}"
            )
        if not data.get("next"):
            break
        page += 1
        if page % 5 == 0:
            print(f"... page {page}, hits={len(hits)}")

    hits.sort(key=lambda x: (-x["pending"], x["name"] or ""))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "done_companies": len(done),
        "us_pending_companies": len(hits),
        "us_pending_robots": sum(h["pending"] for h in hits),
        "companies": hits,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT} companies={len(hits)} robots={payload['us_pending_robots']}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "type: log",
        "title: US Overnight Discover — Morning Report",
        "status: draft",
        "version: 1.0",
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
        f"Started: {payload['generated_at']}",
        "",
        f"- Done companies (content_queue_done): **{len(done)}**",
        f"- Remaining US companies with pending: **{len(hits)}**",
        f"- Remaining US pending robots: **{payload['us_pending_robots']}**",
        "",
        "## Queue (US pending, largest first)",
        "",
        "| Pending | ID | Company | Website |",
        "|--------:|---:|---------|---------|",
    ]
    for h in hits:
        web = h["website"] or "—"
        lines.append(f"| {h['pending']} | {h['company_id']} | {h['name']} | {web} |")
    lines.extend(
        [
            "",
            "## Per-company robot URLs (queue snapshot)",
            "",
        ]
    )
    for h in hits:
        lines.append(f"### {h['name']} ({h['company_id']})")
        lines.append("")
        lines.append(f"- Website: {h['website'] or '—'}")
        lines.append(f"- Pending: {h['pending']}")
        lines.append("")
        for r in h["robots"]:
            lines.append(f"- `{r['id']}` {r['name']} — {r.get('url') or '(no url)'}")
        lines.append("")
    lines.extend(
        [
            "## Overnight session log",
            "",
            "_(appended as companies are enriched)_",
            "",
            "## Related",
            "",
            "- [approve-publish-status.md](../checklists/approve-publish-status.md)",
            "- [log.md](../log.md)",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
