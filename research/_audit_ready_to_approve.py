#!/usr/bin/env python3
"""Audit which companies have pending_review robots that clear must-approve gates.

Must-clear (stakeholder): photo, country, categories, uses, features.
Warnings (soft): no video, no specs, no tags, IMAGE TO-DO notes.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402

STATE_PATH = _HERE / "state" / "content_queue_done.json"
OUT_PATH = _HERE / "staging" / "reports" / "ready-to-approve.json"

# Recently curated / known focus OEMs (even if not in done set)
EXTRA_COMPANY_IDS = {
    1413,  # Pangolin
}


def _load_done_ids() -> set[int]:
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return set(int(x) for x in data.get("companies") or []) | EXTRA_COMPANY_IDS


def _has_image(r: dict[str, Any]) -> bool:
    return bool(r.get("s3_image") or r.get("image") or r.get("image_url"))


def _has_features(r: dict[str, Any]) -> bool:
    return len((r.get("features") or "").strip()) >= 40


def _country_ok(r: dict[str, Any], company: dict[str, Any] | None) -> bool:
    mc = r.get("manufacturer_countries") or []
    if isinstance(mc, list) and mc:
        return True
    if r.get("country") or r.get("country_code"):
        return True
    if company:
        c = company.get("country")
        if isinstance(c, dict) and (c.get("name") or c.get("code")):
            return True
        if isinstance(c, str) and c.strip():
            return True
        if company.get("country_code"):
            return True
    return False


def _list_field(r: dict[str, Any], key: str) -> list[Any]:
    val = r.get(key) or []
    return val if isinstance(val, list) else []


def _has_categories(r: dict[str, Any]) -> bool:
    return len(_list_field(r, "categories")) > 0


def _has_uses(r: dict[str, Any]) -> bool:
    return len(_list_field(r, "uses")) > 0


def _hard_blockers(r: dict[str, Any], company: dict[str, Any] | None) -> list[str]:
    blockers: list[str] = []
    notes = (r.get("notes") or "")
    if "[IMAGE TO-DO" in notes:
        blockers.append("image_todo_note")
    if not _has_image(r):
        blockers.append("no_image")
    if not _has_features(r):
        blockers.append("no_features")
    if not _country_ok(r, company):
        blockers.append("no_country")
    if not _has_categories(r):
        blockers.append("no_categories")
    if not _has_uses(r):
        blockers.append("no_uses")
    return blockers


def _soft_warns(r: dict[str, Any]) -> list[str]:
    warns: list[str] = []
    vids = r.get("videos") or r.get("video_urls") or []
    if not (isinstance(vids, list) and vids):
        warns.append("no_video")
    tags = r.get("tags") or []
    if not (isinstance(tags, list) and tags):
        warns.append("no_tags")
    has_spec = any(
        r.get(k) is not None
        for k in ("weight_kg", "dof", "length_mm", "width_mm", "height_mm", "payload_kg", "reach_mm")
    ) or bool((r.get("dimensions_mm") or "").strip())
    if not has_spec:
        warns.append("no_specs")
    return warns


def fetch_company(client: ResearchApiClient, cid: int) -> dict[str, Any]:
    for attempt in range(4):
        try:
            return client._get(f"companies/{cid}/")
        except Exception:  # noqa: BLE001
            time.sleep(2**attempt)
    return {"id": cid}


def list_pending_for_company(client: ResearchApiClient, cid: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        data = None
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                data = client._get(
                    "robots/robots/",
                    params={
                        "company_ref": cid,
                        "status": "pending_review",
                        "page": page,
                        "page_size": 50,
                    },
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(2**attempt)
        if data is None:
            print(f"  WARN company {cid} page {page} failed: {last_exc}", flush=True)
            break
        batch = data.get("results") or []
        results.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1
    return results


def main() -> int:
    done_ids = sorted(_load_done_ids())
    client = ResearchApiClient()
    report: dict[str, Any] = {
        "scanned_companies": len(done_ids),
        "clean_companies": [],
        "partial_companies": [],
        "blocked_companies": [],
        "zero_pending": [],
    }

    for i, cid in enumerate(done_ids, 1):
        company = fetch_company(client, cid)
        name = company.get("name") or f"company-{cid}"
        pending = list_pending_for_company(client, cid)
        print(f"[{i}/{len(done_ids)}] {cid} {name}: {len(pending)} pending", flush=True)
        if not pending:
            report["zero_pending"].append({"company_id": cid, "name": name})
            continue

        clean: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for r in pending:
            blockers = _hard_blockers(r, company)
            row = {
                "id": r.get("id"),
                "name": r.get("name"),
                "blockers": blockers,
                "warns": _soft_warns(r),
            }
            if blockers:
                blocked.append(row)
            else:
                clean.append(row)

        entry = {
            "company_id": cid,
            "name": name,
            "pending": len(pending),
            "clean": len(clean),
            "blocked": len(blocked),
            "admin_url": (
                f"https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/"
                f"?company_id={cid}"
            ),
            "clean_robots": clean,
            "blocked_robots": blocked[:15],
            "blocker_counts": dict(
                defaultdict(
                    int,
                    {
                        b: sum(1 for x in blocked if b in x["blockers"])
                        for b in {bb for x in blocked for bb in x["blockers"]}
                    },
                )
            ),
        }

        if not blocked:
            report["clean_companies"].append(entry)
        elif clean:
            report["partial_companies"].append(entry)
        else:
            report["blocked_companies"].append(entry)

    for key in ("clean_companies", "partial_companies", "blocked_companies"):
        report[key].sort(key=lambda c: (-c["clean"], -c["pending"], c["name"]))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n=== CLEAN (all pending ready to approve) ===")
    for c in report["clean_companies"]:
        print(f"  {c['company_id']:>5}  {c['name']}: {c['clean']} robots  {c['admin_url']}")

    print("\n=== PARTIAL (approve the clean ones; skip blocked) ===")
    for c in report["partial_companies"][:25]:
        print(
            f"  {c['company_id']:>5}  {c['name']}: {c['clean']}/{c['pending']} clean"
            f"  blockers={c['blocker_counts']}"
        )

    print(f"\nwrote {OUT_PATH}")
    print(
        f"summary: clean_cos={len(report['clean_companies'])} "
        f"partial={len(report['partial_companies'])} "
        f"blocked={len(report['blocked_companies'])} "
        f"zero_pending={len(report['zero_pending'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
