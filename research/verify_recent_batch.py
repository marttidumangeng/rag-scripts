from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore

COMPANIES = [220, 1490, 1419, 1637, 1422, 1635, 1489, 1630, 1474, 204, 416, 107, 1458, 1421, 883, 1399]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--poll-seconds", type=int, default=15)
    ap.add_argument("--json-out", default="staging/reports/recent_ai_verification.json")
    args = ap.parse_args()
    client = ResearchApiClient()
    robots = []
    seen = set()
    for company_id in COMPANIES:
        for robot in client.list_robots_for_company(company_id):
            rid = int(robot.get("id") or 0)
            if rid and rid not in seen:
                seen.add(rid)
                robots.append(robot)
    ids = [int(robot["id"]) for robot in robots]
    result = {"apply": args.apply, "companies": COMPANIES, "robots": len(ids), "jobs": [], "errors": []}
    if args.apply:
        for start in range(0, len(ids), args.batch_size):
            batch = ids[start : start + args.batch_size]
            try:
                job = client.ai_verify_start(batch, force=True)
                job_id = job.get("job_id") or job.get("id")
                item = {"start": start, "count": len(batch), "job": job}
                if job_id:
                    while True:
                        status = client.ai_verify_status(str(job_id))
                        item["status"] = status
                        state = str(status.get("status") or status.get("state") or "").lower()
                        if state in {"completed", "complete", "done", "failed", "error"} or status.get("finished") is True:
                            break
                        time.sleep(args.poll_seconds)
                result["jobs"].append(item)
            except Exception as exc:  # noqa: BLE001
                result["errors"].append({"start": start, "count": len(batch), "error": str(exc)})
    out = RESEARCH_DIR / args.json_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"apply": args.apply, "robots": len(ids), "jobs": len(result["jobs"]), "errors": len(result["errors"]), "report": str(out)}, ensure_ascii=False, indent=2))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
