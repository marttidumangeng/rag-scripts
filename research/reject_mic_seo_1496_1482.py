"""Reject Made-in-China SEO shells for high-gap companies 1496 and 1482.

1496 Dongguan Rainbow — 19 MIC listings (no TL-* model identity); real OEM catalog
      lives on rainbow-robots.com for a future greenfield import.
1482 Guangzhou Aobo Information Technology — 14 MIC keyword titles; same OEM as
      company 1384 Aobo Robot (aoborobot.com), already enriched.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

REASONS = {
    1496: (
        "seo_mic_shell: Made-in-China marketplace SEO listing without TL-* model "
        "identity or OEM primary URL. Dongguan Rainbow real catalog is on "
        "rainbow-robots.com (/show/*.html) — reject MIC shells; do not enrich in place."
    ),
    1482: (
        "seo_mic_shell: Made-in-China keyword-stuffed title (not a distinct SKU). "
        "Same Guangzhou Aobo OEM already enriched as company 1384 Aobo Robot "
        "(aoborobot.com). Reject MIC spillover; do not duplicate under 1482."
    ),
}


def _admin_base() -> str:
    return (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")


def _internal_secret() -> str:
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
    if secret:
        return secret
    for candidate in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": _internal_secret(),
    }
    admin_msg = ""
    try:
        resp = requests.post(
            url, headers=headers, json={"rejection_reason": reason[:500]}, timeout=60
        )
        if resp.ok:
            return f"admin-reject {resp.status_code}"
        admin_msg = f"admin {resp.status_code} {(resp.text or '')[:120]}"
    except requests.RequestException as e:
        admin_msg = f"admin ERR {e}"
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {"status": "rejected", "rejection_reason": reason[:500]},
        )
        return f"api-patch-rejected (fallback after {admin_msg})"
    except Exception as e:
        return f"FAIL {admin_msg} / patch {e}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--companies", type=int, nargs="*", default=[1496, 1482])
    args = parser.parse_args()

    client = ResearchApiClient()
    report: dict[str, list] = {}
    for cid in args.companies:
        reason = REASONS[cid]
        robots = [
            r
            for r in client.list_robots_for_company(cid)
            if str(r.get("status") or "").lower() == "pending_review"
        ]
        print(f"Company {cid}: {len(robots)} pending_review to reject")
        report[str(cid)] = []
        for r in robots:
            rid = int(r["id"])
            name = r.get("name")
            url = (r.get("url") or "")[:80]
            print(f"  {rid} {name!r} {url}")
            if not args.apply:
                report[str(cid)].append({"id": rid, "name": name, "dry_run": True})
                continue
            msg = reject_robot(client, rid, reason)
            print(f"    -> {msg}")
            report[str(cid)].append({"id": rid, "name": name, "result": msg})

    out = _RESEARCH_DIR / "staging" / "reports" / "reject-mic-seo-1496-1482.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Report: {out}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply --mark-done")
        return 0

    if args.mark_done:
        for cid in args.companies:
            subprocess.check_call(
                [
                    sys.executable,
                    str(_RESEARCH_DIR / "triage_content_queue.py"),
                    "--mark-done",
                    str(cid),
                ],
                cwd=str(_RESEARCH_DIR),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
