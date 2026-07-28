#!/usr/bin/env python3
"""UT Austin Robot Perception Lab (1308) — discover + queue cleanup.

FINDING (2026-07-20):
  Harmon (605) is a CoRL 2024 *method/paper* (whole-body motion generation from
  language), not a robot product. Project page executes demos on Fourier GR1-T1/T2
  (third-party hardware). Facebook lookaside hero + no_country must-clear are
  secondary; primary fix is REJECT as non-robot.

SKIP (not RPL OEM robot products):
  - robosuite / robomimic / RoboCasa / RoboTurk / Deoxys / AMAGO / GIGA — software
  - VIOLA / GROOT / TRILL / BUMBLE / GR00T N1 — algorithms / foundation models
  - DRACO 3 — Apptronik-built for UT Austin *Human Centered Robotics Lab* (HCRL),
    not RPL; belongs under Apptronik / HCRL if catalogued, not this company
  - Fourier GR-1 — third-party platform used in Harmon demos

CREATE: none — RPL has no manufacturer robot SKUs on rpl.cs.utexas.edu

Usage:
  python discover_utaustin_rpl_robots.py
  python discover_utaustin_rpl_robots.py --apply
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

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1308
COMPANY_NAME = "University of Texas at Austin (Robot Perception Lab)"
US_ID = 20
REPORT = _RESEARCH_DIR / "staging" / "reports" / "utaustin-rpl-discover.json"

REJECT = [
    {
        "id": 605,
        "name": "Harmon",
        "reason": (
            "not a robot: Harmon is a CoRL 2024 motion-generation method/paper "
            "(ut-austin-rpl.github.io/Harmon), not a product. Real demos use "
            "Fourier GR1-T1/T2. RPL catalog has no OEM robot SKUs — software/"
            "algorithms only. DRACO 3 is Apptronik→HCRL, not RPL."
        ),
    },
]

SKIP_NOTES = [
    "robosuite / robomimic / RoboCasa / Deoxys — open-source software frameworks",
    "VIOLA / GROOT / TRILL / BUMBLE / GR00T N1 — research methods / models",
    "DRACO 3 — Apptronik custom for HCRL (sites.utexas.edu/hcrl/robots/), not RPL",
    "Fourier GR-1 — third-party hardware used in Harmon demos only",
]


def _admin_base() -> str:
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    if not api:
        api = os.environ.get("RESEARCH_API_BASE_URL", "").rstrip("/")
    return api.replace("/api/v1", "")


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    """Prefer admin reject; fall back to research PATCH status=rejected + notes."""
    headers = None
    sid = os.environ.get("ADMIN_SESSION_ID", "").strip()
    if sid:
        headers = {"Cookie": f"sessionid={sid}", "Content-Type": "application/json"}
    api = _admin_base()
    if headers and api:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
        try:
            resp = requests.post(
                url,
                headers=headers,
                json={"type": "robot", "reason": reason},
                timeout=120,
            )
            if resp.ok:
                return "admin-rejected"
            print(f"  admin reject HTTP {resp.status_code}; falling back to PATCH")
        except requests.RequestException as e:
            print(f"  admin reject err {e}; falling back to PATCH")
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": reason[:500],
                "notes": f"[REJECTED 2026-07-20] {reason}"[:2000],
            },
        )
        return "patched-rejected"
    except Exception as e:  # noqa: BLE001
        # Try DRF review endpoint used elsewhere
        try:
            client._post(
                f"robots/robots/{rid}/review/",
                {
                    "action": "reject",
                    "rejection_reason": reason[:500],
                    "notes": f"[REJECTED 2026-07-20] {reason}"[:2000],
                },
            )
            return "review-rejected"
        except Exception as e2:  # noqa: BLE001
            return f"fail:{e} / {e2}"


def ensure_company_country(client: ResearchApiClient) -> str:
    for path in (f"companies/companies/{COMPANY_ID}/", f"companies/{COMPANY_ID}/"):
        try:
            client._patch(path, {"country_id": US_ID})
            return f"country_id={US_ID} via {path}"
        except Exception as e:  # noqa: BLE001
            last = e
    return f"country_patch_fail: {last}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    by_status: dict[str, int] = {}
    for r in robots:
        st = str(r.get("status") or "?").lower()
        by_status[st] = by_status.get(st, 0) + 1

    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "company_name": COMPANY_NAME,
        "website": "https://rpl.cs.utexas.edu/",
        "inventory_before": {"total": len(robots), "by_status": by_status},
        "rejects": REJECT,
        "skip": SKIP_NOTES,
        "create": [],
        "conclusion": (
            "RPL is a research lab (software + algorithms). No manufacturer robot "
            "SKUs to create. Reject Harmon as non-robot. DRACO 3 stays out of scope "
            "(Apptronik / HCRL)."
        ),
    }

    print(f"{COMPANY_NAME} ({COMPANY_ID}) robots={len(robots)} {by_status}")
    print("REJECT:")
    for rej in REJECT:
        print(f"  {rej['id']} {rej['name']}: {rej['reason'][:100]}…")
    print("SKIP:")
    for s in SKIP_NOTES:
        print(f"  - {s}")
    print("CREATE: (none)")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {REPORT}")

    if not args.apply:
        print("dry-run; pass --apply to reject Harmon + set company country_id")
        return 0

    print("company country:", ensure_company_country(client))
    results = []
    for rej in REJECT:
        out = reject_robot(client, int(rej["id"]), rej["reason"])
        print(f"reject {rej['id']}: {out}")
        results.append({"id": rej["id"], "result": out})
        time.sleep(0.3)

    robots2 = client.list_robots_for_company(COMPANY_ID)
    by2: dict[str, int] = {}
    for r in robots2:
        st = str(r.get("status") or "?").lower()
        by2[st] = by2.get(st, 0) + 1
    report["inventory_after"] = {"total": len(robots2), "by_status": by2}
    report["apply_results"] = results
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"after: {by2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
