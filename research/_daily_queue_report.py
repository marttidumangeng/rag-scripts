#!/usr/bin/env python3
"""Daily content-queue numbers report (shareable).

Outputs:
  staging/reports/daily-queue-YYYY-MM-DD.json
  scripts/output/daily_queue/Daily_Queue_Report_YYYY-MM-DD.html
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

_HERE = Path(__file__).resolve().parent
OUT_DIR = _HERE.parents[0] / "output" / "daily_queue"
REPORT_DIR = _HERE / "staging" / "reports"
TZ = ZoneInfo("Asia/Singapore")  # stakeholder local (UTC+8)

# Companies stakeholder published today (Approve = Publish). From cleared checklist + session.
# Do NOT treat Django status "approved" as a separate public state for robots.
TODAY_PUBLISHED_COMPANIES = [
    {"id": 771, "name": "JAKA Robotics"},
    {"id": 168, "name": "Ghost Robotics"},
    {"id": 252, "name": "Serve Robotics"},
    {"id": 428, "name": "Exail Robotics"},
    {"id": 131, "name": "Richtech Robotics"},
    {"id": 14, "name": "Apptronik"},
    {"id": 9, "name": "Agility Robotics"},
    {"id": 92, "name": "Sanctuary AI"},
    {"id": 882, "name": "Realman"},
    {"id": 1413, "name": "Pangolin Robotics"},
    {"id": 192, "name": "Universal Robots"},
    {"id": 237, "name": "Segway Robotics"},
    {"id": 1369, "name": "ACY Automation"},
    {"id": 1396, "name": "KUKA"},
    {"id": 109, "name": "Unitree Robotics"},
    {"id": 1028, "name": "Noblelift"},
    {"id": 239, "name": "RobCo"},
    {"id": 400, "name": "Epson (Seiko Epson)"},
    {"id": 73, "name": "Mitsubishi Electric"},
    {"id": 1490, "name": "Huayan Robotics", "partial": True, "note": "partial — some still To Review"},
    {"id": 195, "name": "Rethink Robotics"},
]


def parse_ts(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def in_local_day(ts: datetime | None, day: date) -> bool:
    if not ts:
        return False
    return ts.astimezone(TZ).date() == day


def has_image(r: dict) -> bool:
    return bool(r.get("s3_image") or r.get("image") or r.get("image_url"))


def has_features(r: dict) -> bool:
    return len((r.get("features") or "").strip()) >= 40


def country_ok(r: dict) -> bool:
    if r.get("manufacturer_country_ref"):
        return True
    mc = r.get("manufacturer_countries") or []
    if isinstance(mc, list) and mc:
        return True
    if r.get("country") or r.get("country_code"):
        return True
    return False


def list_ok(r: dict, key: str) -> bool:
    v = r.get(key) or []
    return isinstance(v, list) and len(v) > 0


def hard_blockers(r: dict) -> list[str]:
    b = []
    notes = r.get("notes") or ""
    if "[IMAGE TO-DO" in notes:
        b.append("image_todo")
    if not has_image(r):
        b.append("no_image")
    if not has_features(r):
        b.append("no_features")
    if not country_ok(r):
        b.append("no_country")
    if not list_ok(r, "categories"):
        b.append("no_categories")
    if not list_ok(r, "uses"):
        b.append("no_uses")
    return b


def count_by_status(client: ResearchApiClient) -> dict[str, int]:
    """Use pagination counts if available; else count pages."""
    counts: dict[str, int] = {}
    for status in ("published", "pending_review", "draft", "rejected", "approved"):
        try:
            data = client._get(
                "robots/robots/",
                params={"status": status, "page": 1, "page_size": 1, "lite": "1"},
            )
            if isinstance(data, dict) and "count" in data:
                counts[status] = int(data["count"])
            else:
                counts[status] = len(data) if isinstance(data, list) else 0
        except Exception as e:
            print(f"status {status} count failed: {e}")
            counts[status] = -1
        time.sleep(0.15)
    return counts


def iter_status(client: ResearchApiClient, status: str, *, lite: bool = True, max_pages: int = 80):
    page = 1
    while page <= max_pages:
        params: dict[str, Any] = {"status": status, "page": page, "page_size": 100}
        if lite:
            params["lite"] = "1"
        for attempt in range(5):
            try:
                data = client._get("robots/robots/", params=params)
                break
            except Exception:
                time.sleep(1.5 * (attempt + 1))
                data = None
        if not data:
            break
        results = data.get("results") if isinstance(data, dict) else data
        if not results:
            break
        for r in results:
            yield r
        if not (isinstance(data, dict) and data.get("next")):
            break
        page += 1
        if page % 5 == 0:
            print(f"  …{status} page {page}")


def classify_pending(client: ResearchApiClient, pending_ids: list[int]) -> dict[str, Any]:
    """Hydrate pending robots and classify ready vs needs enrichment."""
    details: dict[int, dict] = {}

    def fetch(rid: int):
        for a in range(4):
            try:
                return rid, client._get(f"robots/robots/{rid}/")
            except Exception:
                time.sleep(1.0 * (a + 1))
        return rid, None

    print(f"hydrating {len(pending_ids)} pending for readiness…")
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = [pool.submit(fetch, rid) for rid in pending_ids]
        n = 0
        for fut in as_completed(futs):
            rid, d = fut.result()
            n += 1
            if d:
                details[rid] = d
            if n % 200 == 0 or n == len(pending_ids):
                print(f"  hydrated {n}/{len(pending_ids)}")

    ready = 0
    needs = 0
    blocker_counts: Counter[str] = Counter()
    by_company: dict[str, dict[str, int]] = defaultdict(lambda: {"ready": 0, "needs": 0, "total": 0})

    for rid, r in details.items():
        blockers = hard_blockers(r)
        cref = r.get("company_ref") or {}
        cname = cref.get("name") if isinstance(cref, dict) else str(r.get("company") or "?")
        by_company[cname or "?"]["total"] += 1
        if blockers:
            needs += 1
            by_company[cname or "?"]["needs"] += 1
            for b in blockers:
                blocker_counts[b] += 1
        else:
            ready += 1
            by_company[cname or "?"]["ready"] += 1

    top_companies_ready = sorted(
        ({"company": k, **v} for k, v in by_company.items() if v["ready"] > 0),
        key=lambda x: -x["ready"],
    )[:20]
    top_blockers = blocker_counts.most_common(12)

    return {
        "sampled": len(details),
        "ready": ready,
        "needs_enrichment": needs,
        "blocker_counts": dict(top_blockers),
        "top_companies_ready": top_companies_ready,
    }


def main() -> int:
    today = datetime.now(TZ).date()
    day_start = datetime(today.year, today.month, today.day, tzinfo=TZ)
    client = ResearchApiClient()

    print("=== status totals ===")
    status_counts = count_by_status(client)
    print(status_counts)

    # Published today = Approve today (product rule: Approve = Publish).
    # Count ONLY published_at — never reviewed_at (enrichment touches inflate that).
    print("=== published today via focus OEMs (published_at only) ===")
    oem_pub_today = []
    for co in TODAY_PUBLISHED_COMPANIES:
        robots = None
        for attempt in range(5):
            try:
                robots = client.list_robots_for_company(co["id"])
                break
            except Exception as e:
                print(f"  co {co['id']} list retry {attempt}: {e}")
                time.sleep(min(2 ** attempt, 20))
        if robots is None:
            oem_pub_today.append({**co, "published_total": -1, "pending": -1, "published_today": 0, "error": "list_failed"})
            continue
        n_today = 0
        n_pub = 0
        n_pend = 0
        pub_ids: list[int] = []
        for lite in robots:
            st = str(lite.get("status") or "").lower()
            if st == "published":
                n_pub += 1
                pub_ids.append(int(lite["id"]))
            elif st == "pending_review":
                n_pend += 1

        def _fetch(rid: int):
            for a in range(4):
                try:
                    return client._get(f"robots/robots/{rid}/")
                except Exception:
                    time.sleep(0.8 * (a + 1))
            return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            for d in pool.map(_fetch, pub_ids):
                if not d:
                    continue
                ts = parse_ts(d.get("published_at"))  # Approve=Publish; no reviewed_at
                if in_local_day(ts, today):
                    n_today += 1
        oem_pub_today.append(
            {**co, "published_total": n_pub, "pending": n_pend, "published_today": n_today}
        )
        print(f"  co {co['id']} {co['name']}: pub={n_pub} pend={n_pend} today={n_today}")

    published_today = sum(int(x.get("published_today") or 0) for x in oem_pub_today)
    published_today_by_co = Counter(
        {x["name"]: int(x.get("published_today") or 0) for x in oem_pub_today if x.get("published_today")}
    )

    # Pending list (ids) for classification — cap if huge
    print("=== listing pending_review ===")
    pending_ids: list[int] = []
    pending_by_co_lite: Counter[str] = Counter()
    for r in iter_status(client, "pending_review", lite=True, max_pages=60):
        pending_ids.append(int(r["id"]))
        cref = r.get("company_ref") or {}
        cname = (
            cref.get("name")
            if isinstance(cref, dict)
            else str(r.get("company") or "unknown")
        ) or "unknown"
        pending_by_co_lite[cname] += 1

    # If count API said more, note sample
    pending_total = status_counts.get("pending_review") or len(pending_ids)
    if pending_total > len(pending_ids):
        print(f"WARNING: only listed {len(pending_ids)} of {pending_total} pending")

    readiness = classify_pending(client, pending_ids)

    # Discovery backlog from latest Robolist rematch
    gap_path = _HERE / "staging" / "robolist_gap" / "summary.json"
    discovery = {}
    if gap_path.exists():
        gap = json.loads(gap_path.read_text(encoding="utf-8"))
        discovery = {
            "source": "Robolist coverage rematch (fixed Jul-18 catalog)",
            "robolist_robots": gap["robolist"]["robots_merged"],
            "matched": gap["gap"]["robots_matched"],
            "still_to_discover": gap["gap"]["robots_missing"],
            "robot_coverage_pct": gap["gap"]["robot_coverage_pct"],
            "companies_missing_on_robolist": gap["gap"]["companies_missing"],
            "generated_at": gap.get("generated_at"),
        }

    # Headline: published today == approved today (Approve = Publish)
    published_today_headline = published_today

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "local_day": today.isoformat(),
        "timezone": "Asia/Singapore",
        "headline": {
            "published_today": published_today_headline,
            "approved_today": published_today_headline,  # alias — same action
            "still_pending_approval": pending_total,
            "ready_to_approve": readiness["ready"],
            "needs_enrichment": readiness["needs_enrichment"],
            "still_to_discover_robolist": discovery.get("still_to_discover"),
        },
        "inventory_totals": {
            **status_counts,
            "note": "For robots, content-queue Approve sets status=published. Django 'approved' is unused (0).",
        },
        "published_today": {
            "count": published_today_headline,
            "by_company": published_today_by_co.most_common(30),
            "focus_oems": oem_pub_today,
            "rule": "Approve = Publish. Count robots with published_at on local day (SGT). Never use reviewed_at.",
        },
        "pending": {
            "total": pending_total,
            "listed": len(pending_ids),
            "ready": readiness["ready"],
            "needs_enrichment": readiness["needs_enrichment"],
            "blocker_counts": readiness["blocker_counts"],
            "top_companies_ready": readiness["top_companies_ready"],
            "top_companies_pending_volume": pending_by_co_lite.most_common(25),
        },
        "discovery": discovery,
        "definitions": {
            "published_today": "Robots with published_at on local calendar day (SGT). Approve = Publish — same number.",
            "ready_to_approve": "pending_review with photo + features≥40 + country + categories + uses (no IMAGE TO-DO).",
            "needs_enrichment": "pending_review failing one or more must-clear gates.",
            "still_to_discover": "Robolist catalog robots not matched in our DB (competitive gap, not import list).",
        },
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = today.isoformat()
    json_path = REPORT_DIR / f"daily-queue-{stamp}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / f"daily-queue-{stamp}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    h = report["headline"]
    blockers_html = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in (readiness["blocker_counts"] or {}).items()
    )
    ready_cos = "".join(
        f"<tr><td>{c['company']}</td><td>{c['ready']}</td><td>{c['needs']}</td><td>{c['total']}</td></tr>"
        for c in readiness["top_companies_ready"][:15]
    )
    oem_html = "".join(
        f"<tr><td>{c['name']}</td><td>{c['id']}</td><td>{c.get('published_today')}</td>"
        f"<td>{c.get('published_total')}</td><td>{c.get('pending')}</td>"
        f"<td>{'partial' if c.get('partial') else 'cleared'}</td></tr>"
        for c in oem_pub_today
    )

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Daily Queue Report — {stamp}</title>
<style>
body{{font-family:Segoe UI,system-ui,sans-serif;margin:2rem;max-width:920px;color:#111}}
h1{{margin-bottom:.2rem}}.sub{{color:#555;margin-bottom:1.5rem}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin:1.25rem 0}}
.card{{border:1px solid #ddd;border-radius:10px;padding:1rem;background:#fafafa}}
.card .l{{font-size:.75rem;color:#666;text-transform:uppercase}}
.card .v{{font-size:1.8rem;font-weight:700;margin-top:.25rem}}
table{{border-collapse:collapse;width:100%;font-size:.9rem;margin:1rem 0}}
th,td{{border-bottom:1px solid #eee;padding:.4rem .5rem;text-align:left}}
th{{background:#f3f3f3}}.note{{background:#fff8e6;border:1px solid #f0d78c;padding:.75rem 1rem;border-radius:8px}}
.ok{{color:#0a7a2f}}.warn{{color:#9a6700}}
</style></head><body>
<h1>Content queue — daily numbers</h1>
<p class="sub">{stamp} · Asia/Singapore · generated {report['generated_at']}</p>

<div class="cards">
  <div class="card"><div class="l">Published today<br/><span style="font-weight:400;text-transform:none;font-size:.7rem">(Approve = Publish)</span></div><div class="v ok">{h['published_today']}</div></div>
  <div class="card"><div class="l">Still pending approval</div><div class="v">{h['still_pending_approval']}</div></div>
  <div class="card"><div class="l">Ready to approve</div><div class="v ok">{h['ready_to_approve']}</div></div>
  <div class="card"><div class="l">Needs enrichment</div><div class="v warn">{h['needs_enrichment']}</div></div>
  <div class="card"><div class="l">Still to discover*</div><div class="v">{h['still_to_discover_robolist']}</div>
    <div style="font-size:.8rem;color:#666">Robolist gap</div></div>
</div>

<div class="note">
<b>Share line:</b> Today we published <b>{h['published_today']}</b> robots (Approve = Publish).
<b>{h['still_pending_approval']}</b> remain in To Review —
<b>{h['ready_to_approve']}</b> are ready to approve,
<b>{h['needs_enrichment']}</b> still need enrichment.
Competitive discovery backlog vs Robolist: <b>{h['still_to_discover_robolist']}</b> unmatched robots
({discovery.get('robot_coverage_pct')}% coverage).
</div>

<h2>Inventory totals</h2>
<table>
<tr><th>Status</th><th>Count</th></tr>
{"".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k,v in status_counts.items())}
</table>

<h2>Focus OEMs — published today (published_at)</h2>
<table>
<tr><th>Company</th><th>ID</th><th>Published today</th><th>Published total</th><th>Pending</th><th>Queue</th></tr>
{oem_html}
</table>

<h2>Pending readiness</h2>
<p>Must-clear: photo · features (≥40) · country · categories · uses.</p>
<table>
<tr><th>Blocker</th><th>Robots</th></tr>
{blockers_html}
</table>

<h2>Top companies with ready-to-approve pending</h2>
<table>
<tr><th>Company</th><th>Ready</th><th>Needs enrich</th><th>Pending total</th></tr>
{ready_cos}
</table>

<h2>Discovery*</h2>
<p>Robolist competitive gap (not an import mandate): {discovery.get('matched')} matched /
{discovery.get('robolist_robots')} catalog · {discovery.get('still_to_discover')} still unmatched ·
coverage {discovery.get('robot_coverage_pct')}%.</p>

<p style="color:#777;font-size:.85rem">* Discovery = Robolist names we do not yet have. Ready/needs = pending_review gate split.</p>
</body></html>
"""
    html_path = OUT_DIR / f"Daily_Queue_Report_{stamp}.html"
    html_path.write_text(html, encoding="utf-8")
    print(json.dumps(report["headline"], indent=2))
    print(f"wrote {json_path}")
    print(f"wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
