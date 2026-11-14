"""Propose sales_status for published robots that are still not_assessed.

Report-only: writes a JSON snapshot and a CSV review sheet under output/.
A person fills the `decision` column, then apply_sales_status.py calls the
batch endpoint. Never writes to the site itself.

Run from scripts/research:
  export PYTHONIOENCODING=utf-8
  python assess_sales_status.py --category humanoid --limit 50
  python assess_sales_status.py --company-id 807 --limit 20 --no-gemini

Env: IMPORT_SYNC_API_BASE_URL, IMPORT_SYNC_API_KEY (admin key), GEMINI_API_KEY.
Missing ones are read from ../../robotaigeek-server/.env.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from recheck_company_funding import load_env_file  # noqa: E402
from recheck_published import PoliteFetcher, Probe, _get_with_backoff  # noqa: E402

ASSESSABLE = {
    "not_for_sale",
    "pre_order",
    "limited_availability",
    "general_sale",
    "made_to_order",
}

_SALES_SYSTEM = """You assess whether/how an OUTSIDE buyer can order ONE robot,
using the maker's product page (and any search snippets) as evidence. Return JSON only:
{
  "sales_status": "not_for_sale" | "pre_order" | "limited_availability" | "general_sale" | "made_to_order" | "unclear",
  "confidence": "high" | "medium" | "low",
  "quote": "verbatim sentence from the evidence that supports sales_status, else ''",
  "source_url": "the URL of the page that contains that quote, else ''",
  "reason": "one short sentence explaining the choice"
}
Meanings:
- not_for_sale: no way for an outside buyer to order (internal use, research only, announced without ordering)
- pre_order: orders/reservations/deposits are open; deliveries to buyers have not started
- limited_availability: delivered to selected customers only (pilots, allocated production, waitlist)
- general_sale: any qualifying buyer can order now from the maker or a reseller
- made_to_order: sold by quote and built or configured per customer
- unclear: the evidence does not support any of the above
Rules:
- Never invent a status. Prefer unclear over a guess.
- quote MUST be copied verbatim from the evidence. Empty quote => status must be unclear.
- source_url MUST be one of the evidence URLs. Empty URL => status must be unclear.
- Robolist and other aggregators are leads, never sources for a value.
- Do not confuse product stage (prototype/released) with buyability."""


def sales_status_key(raw: Any) -> str:
    if raw is None or raw == "":
        return "not_assessed"
    if isinstance(raw, dict):
        return str(raw.get("key") or raw.get("value") or "").strip().lower() or "not_assessed"
    return str(raw).strip().lower() or "not_assessed"


def parse_sales_assessment(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        data = json.loads(text)
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    status = str(data.get("sales_status") or "unclear").strip().lower().replace("-", "_").replace(" ", "_")
    quote = str(data.get("quote") or "").strip()
    source_url = str(data.get("source_url") or "").strip()
    confidence = str(data.get("confidence") or "low").strip().lower()
    reason = str(data.get("reason") or "").strip()[:300]
    if status not in ASSESSABLE or not quote or not source_url:
        status = "unclear"
        if not quote:
            reason = reason or "missing verbatim quote"
        elif not source_url:
            reason = reason or "missing source URL"
        elif status not in ASSESSABLE:
            reason = reason or "status not in allowed set"
    return {
        "sales_status": status,
        "confidence": confidence if confidence in ("high", "medium", "low") else "low",
        "quote": quote[:500],
        "source_url": source_url[:500],
        "reason": reason,
    }


def gemini_sales_assessment(
    robot: dict[str, Any],
    company: str,
    probe: Probe,
    snippets: list[dict[str, str]] | None = None,
    *,
    model: str = "models/gemini-2.5-flash",
) -> dict[str, Any] | None:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    from google.genai import types

    import spend_guard
    client = spend_guard.client(api_key=api_key, http_options={"api_version": "v1beta"})
    ours = {
        "name": robot.get("name"),
        "model_name": robot.get("model_name"),
        "url": robot.get("url") or "",
        "availability": sales_status_key(robot.get("availability_status")),
    }
    blocks = [f"[PAGE] {probe.final_url or probe.url}\nTitle: {probe.title}\n{probe.text[:9000]}"]
    for s in (snippets or [])[:6]:
        blocks.append(
            f"[SEARCH] {s.get('link', '')}\n{s.get('title', '')}\n{s.get('snippet', '')}"
        )
    prompt = (
        f"{_SALES_SYSTEM}\n\nMaker: {company}\nOur record: "
        f"{json.dumps(ours, ensure_ascii=False, default=str)}"
        f"\n\n--- Evidence ---\n" + "\n\n".join(blocks)
    )
    resp = client.models.generate_content(
        model=model,
        contents=prompt[:40000],
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            max_output_tokens=1024,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return parse_sales_assessment(resp.text or "")


def list_unassessed(
    api: Any,
    *,
    category: str = "",
    company_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Published robots with sales_status=not_assessed, makers grouped."""
    out: list[dict[str, Any]] = []
    page = 1
    params: dict[str, Any] = {
        "lite": 1,
        "status": "published",
        "sales_status": "not_assessed",
        "ordering": "company_ref__name,name",
        "page_size": 100,
    }
    if category.strip():
        params["c"] = category.strip()
    while True:
        data = _get_with_backoff(api, "robots/robots/", {**params, "page": page})
        rows = data.get("results", []) if isinstance(data, dict) else (data or [])
        for r in rows:
            if sales_status_key(r.get("sales_status")) != "not_assessed":
                continue
            c = r.get("company_ref")
            cid = c.get("id") if isinstance(c, dict) else None
            if company_id is not None and cid != company_id:
                continue
            out.append({
                "id": r["id"],
                "name": r.get("name") or "",
                "company_id": cid,
                "company": (c.get("name") if isinstance(c, dict) else r.get("company")) or "",
                "url": r.get("url") or "",
                "availability_status": sales_status_key(r.get("availability_status")),
            })
            if len(out) >= limit:
                return out
        if not rows or (isinstance(data, dict) and not data.get("next")):
            break
        page += 1
    return out


def load_excluded_ids(paths: list[Path]) -> set[int]:
    ids: set[int] = set()
    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for row in data.get("rows") or data.get("robots") or []:
            rid = row.get("id") or row.get("robot_id")
            if rid is not None:
                ids.add(int(rid))
    return ids


CSV_FIELDS = [
    "id",
    "name",
    "maker",
    "current_status",
    "proposed_sales_status",
    "confidence",
    "quote",
    "source_url",
    "reason",
    "decision",
]


def write_outputs(rows: list[dict[str, Any]], out_dir: Path, run_id: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"sales_status_assess_{run_id}.json"
    csv_path = out_dir / f"sales_status_assess_{run_id}.csv"
    payload = {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(rows),
        "rows": rows,
    }
    tmp = json_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(json_path)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})
    return json_path, csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", default="", help="Category slug filter (API `c`).")
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-gemini", type=int, default=150)
    parser.add_argument("--no-gemini", action="store_true")
    parser.add_argument(
        "--exclude-snapshots",
        nargs="*",
        default=[],
        help="Prior assess JSON snapshots whose robot ids to skip.",
    )
    parser.add_argument("--output-dir", default=str(_HERE / "output"))
    parser.add_argument("--api-base", default="", help="Override IMPORT_SYNC_API_BASE_URL.")
    parser.add_argument("--api-key", default=None, help="Override IMPORT_SYNC_API_KEY ('' for none).")
    args = parser.parse_args(argv)

    load_env_file(_HERE.parents[1] / "robotaigeek-server" / ".env")
    if args.api_base:
        os.environ["IMPORT_SYNC_API_BASE_URL"] = args.api_base
    if args.api_key is not None:
        os.environ["IMPORT_SYNC_API_KEY"] = args.api_key
    for key in ("IMPORT_SYNC_API_BASE_URL", "IMPORT_SYNC_API_KEY"):
        if key == "IMPORT_SYNC_API_KEY" and args.api_key == "":
            continue
        if not os.environ.get(key):
            print(f"Missing {key}", file=sys.stderr)
            return 2

    from api_client import ResearchApiClient

    api = ResearchApiClient(
        base_url=os.environ.get("IMPORT_SYNC_API_BASE_URL"),
        api_key=os.environ.get("IMPORT_SYNC_API_KEY", ""),
    )
    excluded = load_excluded_ids([Path(p) for p in args.exclude_snapshots])
    briefs = list_unassessed(
        api,
        category=args.category,
        company_id=args.company_id,
        limit=max(args.limit * 3, args.limit),
    )
    briefs = [b for b in briefs if b["id"] not in excluded][: args.limit]

    fetcher = PoliteFetcher()
    run_id = datetime.now().strftime("%Y%m%d-%H%M")
    rows: list[dict[str, Any]] = []
    gemini_calls = 0

    for brief in briefs:
        robot = _get_with_backoff(api, f"robots/robots/{brief['id']}/")
        url = (robot.get("url") or brief.get("url") or "").strip()
        probe = fetcher.probe(url) if url else Probe(
            url="", status="no_url", http=None, final_url="", title="", text="", full_text="", detail="no_url",
        )
        assessment: dict[str, Any] = {
            "sales_status": "unclear",
            "confidence": "low",
            "quote": "",
            "source_url": "",
            "reason": "no Gemini run",
        }
        if not args.no_gemini and gemini_calls < args.max_gemini and probe.status == "ok":
            result = gemini_sales_assessment(
                robot,
                brief.get("company") or "",
                probe,
            )
            gemini_calls += 1
            if result:
                assessment = result
                if assessment["sales_status"] != "unclear" and not assessment["source_url"]:
                    assessment["source_url"] = probe.final_url or probe.url
        elif probe.status != "ok":
            assessment["reason"] = f"source page {probe.status}"

        rows.append({
            "id": brief["id"],
            "name": robot.get("name") or brief.get("name") or "",
            "maker": brief.get("company") or "",
            "current_status": "not_assessed",
            "proposed_sales_status": assessment["sales_status"],
            "confidence": assessment["confidence"],
            "quote": assessment["quote"],
            "source_url": assessment["source_url"],
            "reason": assessment["reason"],
            "decision": "",
        })

    json_path, csv_path = write_outputs(rows, Path(args.output_dir), run_id)
    counts = Counter(r["proposed_sales_status"] for r in rows)
    print(f"Assessed {len(rows)} robots. Proposals: {dict(counts)}")
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print("Fill the decision column (accept / corrected key / leave blank), then run apply_sales_status.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
