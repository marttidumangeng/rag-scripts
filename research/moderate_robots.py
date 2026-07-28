#!/usr/bin/env python3
"""Moderate robots: gate audit → publish / reject / hold buckets.

Product rule: Approve = Publish (ready for public view). Content-queue Approve
sets status=published.

Usage:
  python moderate_robots.py --company-id 882
  python moderate_robots.py --company-id 882 --apply --ids 3214 3215
  python moderate_robots.py --company-id 882 --apply --reject-ids 5227 --reason "duplicate: keep RM65 Standard"

Apply calls the admin content-queue endpoints (staff session cookie via
ADMIN_SESSION_ID env, or print IDs for manual bulk Approve when unset).
"""

from __future__ import annotations

import argparse
import json
import os
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

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from _audit_ready_to_approve import (  # noqa: E402
    _country_ok,
    _hard_blockers,
    _has_categories,
    _has_features,
    _has_image,
    _has_uses,
)

REPORT_DIR = _HERE / "staging" / "reports"


def _admin_base() -> str:
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    return api.replace("/api/v1", "")


def list_pending(client: ResearchApiClient, company_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": company_id,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        rows.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1
        time.sleep(0.05)
    return rows


def get_company(client: ResearchApiClient, company_id: int) -> dict[str, Any] | None:
    for path in (f"companies/{company_id}/", f"companies/companies/{company_id}/"):
        try:
            return client._get(path)
        except Exception:  # noqa: BLE001
            continue
    return None


def soft_warns(r: dict[str, Any]) -> list[str]:
    """Soft gaps — publish OK, but enrichment must still try (stakeholder 2026-07-20)."""
    warns: list[str] = []
    avail = r.get("availability_status")
    if avail is None or (isinstance(avail, dict) and not avail.get("id") and not avail.get("key")):
        warns.append("no_availability")
    if not (r.get("videos") or r.get("video_urls")):
        warns.append("no_video")
    # Typed Robot columns (same spirit as robots.quality.SPEC_FIELDS). Do NOT rely on
    # empty `specifications` JSON — that field is usually unset even when payload/speed exist.
    typed_spec_keys = (
        "weight_kg",
        "width_mm",
        "length_mm",
        "height_mm",
        "speed",
        "walking_speed",
        "runtime_minutes",
        "battery_wh",
        "charging_time_minutes",
        "dof",
        "payload_kg",
        "reach_mm",
        "repeatability_mm",
        "weight",
        "width",
        "length",
        "height",
        "runtime",
        "battery_capacity",
        "voltage",
    )

    def _blank(val: Any) -> bool:
        if val is None:
            return True
        if isinstance(val, str):
            return not val.strip()
        if isinstance(val, (list, dict)):
            return len(val) == 0
        return False

    if all(_blank(r.get(k)) for k in typed_spec_keys):
        warns.append("no_specs")
    tags = r.get("tags") or []
    if not tags:
        warns.append("no_tags")
    if not r.get("price_min") and not r.get("price_max") and not r.get("price"):
        warns.append("no_price")
    if not r.get("release_year"):
        warns.append("no_year")
    notes = (r.get("notes") or "").upper()
    if "IMAGE TO-DO" in notes:
        warns.append("image_todo_note")
    return warns


def bucket_robot(
    r: dict[str, Any],
    company: dict[str, Any] | None,
    *,
    reject_hints: dict[int, str],
) -> dict[str, Any]:
    rid = int(r["id"])
    entry: dict[str, Any] = {
        "id": rid,
        "name": r.get("name"),
        "url": r.get("url"),
        "bucket": "hold",
        "blockers": [],
        "soft_warns": soft_warns(r),
        "reason": "",
    }
    if rid in reject_hints:
        entry["bucket"] = "reject"
        entry["reason"] = reject_hints[rid]
        return entry

    blockers = _hard_blockers(r, company)
    entry["blockers"] = blockers
    # Also surface gate helpers for report clarity
    entry["gates"] = {
        "image": _has_image(r),
        "features": _has_features(r),
        "country": _country_ok(r, company),
        "categories": _has_categories(r),
        "uses": _has_uses(r),
    }
    if blockers:
        entry["bucket"] = "hold"
        entry["reason"] = "must_clear: " + ", ".join(blockers)
        return entry

    entry["bucket"] = "publish"
    entry["reason"] = "must_clear_pass"
    return entry


def plan(
    client: ResearchApiClient,
    company_id: int,
    *,
    only_ids: set[int] | None,
    reject_hints: dict[int, str],
) -> dict[str, Any]:
    company = get_company(client, company_id)
    robots = list_pending(client, company_id)
    if only_ids is not None:
        robots = [r for r in robots if int(r["id"]) in only_ids]

    rows = [bucket_robot(r, company, reject_hints=reject_hints) for r in robots]
    by_bucket = {"publish": [], "reject": [], "hold": []}
    for row in rows:
        by_bucket[row["bucket"]].append(row)

    return {
        "company_id": company_id,
        "company_name": (company or {}).get("name"),
        "pending_count": len(rows),
        "counts": {k: len(v) for k, v in by_bucket.items()},
        "publish_ids": [x["id"] for x in by_bucket["publish"]],
        "reject_ids": [x["id"] for x in by_bucket["reject"]],
        "hold_ids": [x["id"] for x in by_bucket["hold"]],
        "robots": rows,
        "note": (
            "Approve=Publish. Apply via content-queue Approve "
            "(sets status=published). Soft warns do not block."
        ),
    }


def _session_headers() -> dict[str, str] | None:
    sid = os.environ.get("ADMIN_SESSION_ID", "").strip()
    if not sid:
        return None
    return {"Cookie": f"sessionid={sid}", "Content-Type": "application/json"}


def apply_publish(ids: list[int]) -> list[dict[str, Any]]:
    headers = _session_headers()
    base = _admin_base()
    if not headers or not base:
        return [
            {
                "ok": False,
                "error": "Set ADMIN_SESSION_ID (Django session cookie) for --apply, "
                "or Approve these IDs in admin bulk",
                "ids": ids,
            }
        ]
    results = []
    for rid in ids:
        url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/approve/"
        try:
            resp = requests.post(url, headers=headers, json={"type": "robot"}, timeout=120)
            ok = resp.ok
            results.append(
                {
                    "id": rid,
                    "ok": ok,
                    "status": resp.status_code,
                    "body": (resp.text or "")[:300],
                }
            )
            print(f"publish {rid}: {'ok' if ok else resp.status_code}")
        except requests.RequestException as e:
            results.append({"id": rid, "ok": False, "error": str(e)})
            print(f"publish {rid}: ERR {e}")
        time.sleep(0.25)
    return results


def apply_reject(ids: list[int], reason: str) -> list[dict[str, Any]]:
    headers = _session_headers()
    base = _admin_base()
    if not headers or not base:
        return [
            {
                "ok": False,
                "error": "Set ADMIN_SESSION_ID for --apply reject",
                "ids": ids,
                "reason": reason,
            }
        ]
    if not reason.strip():
        return [{"ok": False, "error": "rejection reason required"}]
    results = []
    for rid in ids:
        url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
        try:
            resp = requests.post(
                url,
                headers=headers,
                json={"type": "robot", "reason": reason},
                timeout=120,
            )
            ok = resp.ok
            results.append(
                {
                    "id": rid,
                    "ok": ok,
                    "status": resp.status_code,
                    "body": (resp.text or "")[:300],
                }
            )
            print(f"reject {rid}: {'ok' if ok else resp.status_code}")
        except requests.RequestException as e:
            results.append({"id": rid, "ok": False, "error": str(e)})
            print(f"reject {rid}: ERR {e}")
        time.sleep(0.25)
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Moderate robots (approve=publish)")
    ap.add_argument("--company-id", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*", help="Limit dry-run / publish these IDs")
    ap.add_argument("--reject-ids", type=int, nargs="*", default=[])
    ap.add_argument("--reason", default="", help="Rejection reason (required with --reject-ids --apply)")
    args = ap.parse_args()

    only = set(args.ids) if args.ids else None
    reject_hints = {rid: (args.reason or "duplicate") for rid in (args.reject_ids or [])}

    client = ResearchApiClient()
    report = plan(client, args.company_id, only_ids=only, reject_hints=reject_hints)
    out = REPORT_DIR / f"moderate-{args.company_id}.json"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"company {args.company_id} pending={report['pending_count']} "
        f"publish={report['counts']['publish']} reject={report['counts']['reject']} "
        f"hold={report['counts']['hold']}"
    )
    for row in report["robots"]:
        print(
            f"  {row['id']:5d} {row['bucket']:7s} {row['name'][:36]:36s} "
            f"{row['reason'][:50]}"
        )
    print("wrote", out)

    if not args.apply:
        print("dry-run only; pass --apply after spot-check (Approve=Publish)")
        if report["publish_ids"]:
            print("publish_ids:", " ".join(str(i) for i in report["publish_ids"]))
        return 0

    results: dict[str, Any] = {"publish": [], "reject": []}
    publish_ids = list(args.ids) if args.ids else report["publish_ids"]
    if publish_ids:
        results["publish"] = apply_publish(publish_ids)
    if args.reject_ids:
        results["reject"] = apply_reject(list(args.reject_ids), args.reason)
    report["apply_results"] = results
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fail = any(not x.get("ok") for x in results["publish"] + results["reject"])
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
