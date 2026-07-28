#!/usr/bin/env python3
"""Build Robolist coverage progress HTML with focus OEMs (Exail / Huayan / Epson)."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGING = ROOT / "staging" / "robolist_gap"
BASELINE = STAGING / "baseline_2026-07-18"
PREV = STAGING / "snapshot_2026-07-19T02"  # mid-day rematch before tonight's approvals
OUT = ROOT.parents[0] / "output" / "robolist_gap"

# Stakeholder focus this evening
FOCUS = [
    {
        "our_id": 428,
        "label": "Exail Robotics",
        "name_re": r"exail|e(?:ca|ca )?robotics|ixblue",
        "note": "Approved tonight (9 published).",
    },
    {
        "our_id": 1490,
        "label": "Huayan Robotics",
        "name_re": r"huayan|elfin|guangdong huayan",
        "note": "Partial — 9 published, 18 still To Review.",
    },
    {
        "our_id": 400,
        "label": "Epson (Seiko Epson)",
        "name_re": r"\bepson\b|seiko epson",
        "note": "Approved tonight (51 published).",
    },
]


def pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def load_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def focus_stats(robot_matches: list[dict], company_matches: list[dict]) -> list[dict]:
    rows = []
    for f in FOCUS:
        pat = re.compile(f["name_re"], re.I)
        robots = [
            r
            for r in robot_matches
            if pat.search(r.get("manufacturer") or "")
            or pat.search(r.get("name") or "")
            or pat.search(r.get("slug") or "")
        ]
        cos = [
            c
            for c in company_matches
            if pat.search(c.get("name") or "") or pat.search(c.get("slug") or "")
        ]
        matched = [r for r in robots if r.get("match_status") == "matched"]
        missing = [r for r in robots if r.get("match_status") != "matched"]
        co_matched = [c for c in cos if c.get("match_status") == "matched"]
        rows.append(
            {
                **f,
                "robolist_robots": len(robots),
                "matched": len(matched),
                "missing": len(missing),
                "coverage_pct": pct(len(matched), len(robots)),
                "company_on_robolist": len(cos),
                "company_matched": len(co_matched),
                "robolist_company_names": [c.get("name") for c in cos[:5]],
                "matched_samples": [r.get("name") for r in matched[:8]],
                "missing_samples": [r.get("name") for r in missing[:8]],
            }
        )
    return rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Preserve previous "current" as mid snapshot if not already archived
    prev_summary = STAGING / "summary.json"
    # We already overwrote summary — restore mid from progress.json current block if needed
    progress_old = json.loads((STAGING / "progress.json").read_text(encoding="utf-8"))
    PREV.mkdir(parents=True, exist_ok=True)
    if not (PREV / "summary.json").exists():
        # progress.by_category.matched / coverage_pct = state at mid rematch
        mid_cats = []
        for c in progress_old.get("by_category") or []:
            rc = c.get("robolist_count") or 0
            matched = c.get("matched")
            if matched is None:
                continue
            mid_cats.append(
                {
                    "category": c["category"],
                    "robolist_count": rc,
                    "matched": matched,
                    "missing": rc - matched,
                    "coverage_pct": c.get("coverage_pct"),
                }
            )
        mid = {
            "generated_at": progress_old.get("current_at") or "2026-07-19T02:55:17Z",
            "ours": progress_old["current"]["ours"],
            "gap": progress_old["current"]["gap"],
            "by_category": mid_cats,
            "robolist": {"robots_merged": 4340, "companies_merged": 987},
            "note": "Archived mid-day rematch (before Exail/Huayan/Epson approve wave).",
        }
        (PREV / "summary.json").write_text(
            json.dumps(mid, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    base = load_summary(BASELINE / "summary.json")
    mid = load_summary(PREV / "summary.json")
    now = load_summary(STAGING / "summary.json")
    robot_matches = json.loads((STAGING / "robot_matches.json").read_text(encoding="utf-8"))
    company_matches = json.loads((STAGING / "company_matches.json").read_text(encoding="utf-8"))
    focus = focus_stats(robot_matches, company_matches)

    bg, mg, ng = base["gap"], mid["gap"], now["gap"]

    def delta(a, b, key):
        return (b.get(key) or 0) - (a.get(key) or 0)

    robot_pp_full = round(ng["robot_coverage_pct"] - bg["robot_coverage_pct"], 1)
    robot_pp_wave = round(ng["robot_coverage_pct"] - mg["robot_coverage_pct"], 1)
    matched_full = delta(bg, ng, "robots_matched")
    matched_wave = delta(mg, ng, "robots_matched")
    missing_closed_full = delta(ng, bg, "robots_missing")  # positive when gap shrinks
    missing_closed_full = bg["robots_missing"] - ng["robots_missing"]
    missing_closed_wave = mg["robots_missing"] - ng["robots_missing"]

    # category vs baseline
    base_cats = {c["category"]: c for c in base.get("by_category") or []}
    mid_cats = {c["category"]: c for c in mid.get("by_category") or []}
    cat_rows = []
    for c in now.get("by_category") or []:
        b = base_cats.get(c["category"]) or {}
        m = mid_cats.get(c["category"]) or {}
        cat_rows.append(
            {
                **c,
                "matched_baseline": b.get("matched"),
                "coverage_baseline": b.get("coverage_pct"),
                "matched_mid": m.get("matched"),
                "coverage_mid": m.get("coverage_pct"),
                "delta_vs_baseline": (c.get("matched") or 0) - (b.get("matched") or 0),
                "delta_vs_mid": (c.get("matched") or 0) - (m.get("matched") or 0),
                "pp_vs_baseline": round(
                    (c.get("coverage_pct") or 0) - (b.get("coverage_pct") or 0), 1
                ),
                "pp_vs_mid": round((c.get("coverage_pct") or 0) - (m.get("coverage_pct") or 0), 1),
            }
        )
    cat_rows.sort(key=lambda x: -(x.get("delta_vs_baseline") or 0))

    progress = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline_at": base.get("generated_at"),
        "mid_at": mid.get("generated_at"),
        "current_at": now.get("generated_at"),
        "robolist_catalog_fixed": True,
        "note": (
            "Same Robolist catalog snapshot (2026-07-18 scrape) rematched against "
            "current RobotAIGeek inventory. Before = Jul 18 baseline; mid = prior rematch; "
            "after = now (includes Exail / Huayan partial / Epson approvals)."
        ),
        "focus_companies": focus,
        "baseline": {"ours": base["ours"], "gap": bg},
        "mid": {"ours": mid["ours"], "gap": mg},
        "current": {"ours": now["ours"], "gap": ng},
        "progress_vs_baseline": {
            "robot_coverage_pp": robot_pp_full,
            "robots_matched_delta": matched_full,
            "robots_missing_closed": missing_closed_full,
            "pct_of_baseline_robot_gap_closed": pct(missing_closed_full, bg["robots_missing"]),
            "company_coverage_pp": round(
                ng["company_coverage_pct"] - bg["company_coverage_pct"], 1
            ),
            "our_robot_count_delta": now["ours"]["robots"] - base["ours"]["robots"],
        },
        "progress_vs_mid": {
            "robot_coverage_pp": robot_pp_wave,
            "robots_matched_delta": matched_wave,
            "robots_missing_closed": missing_closed_wave,
            "our_robot_count_delta": now["ours"]["robots"] - mid["ours"]["robots"],
        },
        "by_category": cat_rows,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (STAGING / "progress.json").write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "progress.json").write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    focus_html = "\n".join(
        f"<tr>"
        f"<td><b>{f['label']}</b><br/><span class='muted'>our id {f['our_id']}</span></td>"
        f"<td>{f['note']}</td>"
        f"<td>{f['robolist_robots']}</td>"
        f"<td><b>{f['matched']}</b></td>"
        f"<td>{f['missing']}</td>"
        f"<td><b>{f['coverage_pct']}%</b></td>"
        f"<td>{'yes' if f['company_matched'] else 'no'} "
        f"({', '.join(f['robolist_company_names'][:2]) or '—'})</td>"
        f"<td>{', '.join(f['missing_samples'][:4]) or '—'}</td>"
        f"</tr>"
        for f in focus
    )

    cat_html = "\n".join(
        f"<tr><td>{c['category']}</td>"
        f"<td>{c.get('robolist_count')}</td>"
        f"<td>{c.get('coverage_baseline')}%</td>"
        f"<td>{c.get('coverage_mid') if c.get('coverage_mid') is not None else '—'}%</td>"
        f"<td><b>{c.get('coverage_pct')}%</b></td>"
        f"<td>{c.get('pp_vs_baseline'):+} pp</td>"
        f"<td>{c.get('matched_baseline')}</td>"
        f"<td>{c.get('matched')}</td>"
        f"<td>{c.get('delta_vs_baseline'):+}</td>"
        f"<td>{c.get('missing')}</td></tr>"
        for c in cat_rows
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Robolist Coverage Gap — Before &amp; After</title>
<style>
  body {{ font-family: Segoe UI, system-ui, sans-serif; margin: 2rem; color: #111; max-width: 1040px; }}
  h1 {{ margin-bottom: 0.25rem; }}
  .sub {{ color: #555; margin-bottom: 1.5rem; }}
  .muted {{ color: #777; font-size: 0.85rem; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
  .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 1rem; background: #fafafa; }}
  .card .label {{ font-size: 0.75rem; color: #666; text-transform: uppercase; letter-spacing: .03em; }}
  .card .value {{ font-size: 1.45rem; font-weight: 700; margin-top: 0.25rem; }}
  .up {{ color: #0a7a2f; }}
  .flat {{ color: #666; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.88rem; }}
  th, td {{ border-bottom: 1px solid #eee; padding: 0.45rem 0.5rem; text-align: left; vertical-align: top; }}
  th {{ background: #f3f3f3; }}
  .note {{ background: #fff8e6; border: 1px solid #f0d78c; padding: 0.75rem 1rem; border-radius: 8px; margin: 1rem 0; }}
  .timeline {{ display: grid; grid-template-columns: 1fr auto 1fr auto 1fr; gap: 0.5rem; align-items: center; margin: 1.25rem 0; }}
  .tbox {{ border: 1px solid #ddd; border-radius: 8px; padding: 0.75rem; background: #fff; text-align: center; }}
  .tbox b {{ display: block; font-size: 1.2rem; }}
  .arrow {{ color: #888; font-size: 1.4rem; }}
</style>
</head>
<body>
  <h1>Robolist Coverage Gap — Before &amp; After</h1>
  <p class="sub">Generated {progress['generated_at']} · fixed Robolist catalog (scraped 2026-07-18)</p>

  <div class="note">
    <b>How to read:</b> Coverage % = share of Robolist names we already have (higher is better).
    Missing ≈ 100% − coverage. Robolist is a competitive reference only — not an import source.
    Tonight’s focus OEMs: <b>Exail (428)</b>, <b>Huayan (1490, still 18 To Review)</b>, <b>Epson (400)</b>.
  </div>

  <div class="timeline">
    <div class="tbox"><span class="muted">Baseline Jul 18</span>
      <b>{bg['robot_coverage_pct']}%</b>
      <span class="muted">{bg['robots_matched']} matched</span></div>
    <div class="arrow">→</div>
    <div class="tbox"><span class="muted">Mid Jul 19 (~03:00)</span>
      <b>{mg['robot_coverage_pct']}%</b>
      <span class="muted">{mg['robots_matched']} matched</span></div>
    <div class="arrow">→</div>
    <div class="tbox"><span class="muted">Now (after approvals)</span>
      <b class="up">{ng['robot_coverage_pct']}%</b>
      <span class="muted">{ng['robots_matched']} matched</span></div>
  </div>

  <div class="cards">
    <div class="card"><div class="label">Robot coverage (baseline → now)</div>
      <div class="value">{bg['robot_coverage_pct']}% → <span class="up">{ng['robot_coverage_pct']}%</span></div>
      <div class="up">+{robot_pp_full} pp · +{matched_full} matched · gap closed {missing_closed_full}</div></div>
    <div class="card"><div class="label">This approval wave (mid → now)</div>
      <div class="value">{mg['robot_coverage_pct']}% → <span class="up">{ng['robot_coverage_pct']}%</span></div>
      <div class="{'up' if robot_pp_wave else 'flat'}">{robot_pp_wave:+} pp · {matched_wave:+} matched · gap closed {missing_closed_wave}</div></div>
    <div class="card"><div class="label">Company coverage</div>
      <div class="value">{bg['company_coverage_pct']}% → {ng['company_coverage_pct']}%</div>
      <div class="muted">matched {bg['companies_matched']} → {ng['companies_matched']}</div></div>
    <div class="card"><div class="label">Our inventory</div>
      <div class="value">{base['ours']['robots']} → {now['ours']['robots']}</div>
      <div class="up">{now['ours']['robots']-base['ours']['robots']:+} robots</div>
      <div class="muted">companies {base['ours']['companies']} → {now['ours']['companies']}</div></div>
  </div>

  <h2>Focus OEMs (tonight)</h2>
  <p class="sub">Robolist name-match status for the companies you just approved / partially approved.</p>
  <table>
    <tr>
      <th>Company</th><th>Status</th><th>On Robolist (#)</th>
      <th>Matched</th><th>Still missing</th><th>Coverage</th>
      <th>Company matched?</th><th>Missing samples</th>
    </tr>
    {focus_html}
  </table>

  <h2>Coverage by category</h2>
  <p class="sub">% we already have. Δ is vs Jul 18 baseline.</p>
  <table>
    <tr>
      <th>Category</th><th>On Robolist</th>
      <th>% Jul 18</th><th>% mid</th><th>% now</th><th>Change</th>
      <th>Had (#)</th><th>Have (#)</th><th>Δ</th><th>Still missing</th>
    </tr>
    {cat_html}
  </table>

  <p class="muted" style="margin-top:2rem">
    Artifacts: <code>scripts/output/robolist_gap/Robolist_Coverage_Progress.html</code>,
    <code>progress.json</code>, CSVs under <code>scripts/research/staging/robolist_gap/</code>.
  </p>
</body>
</html>
"""
    html_path = OUT / "Robolist_Coverage_Progress.html"
    html_path.write_text(html, encoding="utf-8")
    (STAGING / "Robolist_Coverage_Progress.html").write_text(html, encoding="utf-8")

    print(json.dumps({
        "vs_baseline": progress["progress_vs_baseline"],
        "vs_mid": progress["progress_vs_mid"],
        "focus": [
            {
                "label": f["label"],
                "matched": f["matched"],
                "missing": f["missing"],
                "coverage_pct": f["coverage_pct"],
                "company_matched": f["company_matched"],
            }
            for f in focus
        ],
    }, indent=2))
    print(f"wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
