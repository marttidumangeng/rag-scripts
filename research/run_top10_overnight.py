"""Patch websites for top-10 backlog OEMs, then run overnight enrich on those IDs.

Usage:
  python -u run_top10_overnight.py
  python -u run_top10_overnight.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

# Top 10 from enrichment-backlog.json (remaining, by gap score).
TOP10 = [
    220,  # Estun Automation
    189,  # FANUC
    1479,  # EFORT
    1480,  # Xiamen MUKA
    1225,  # BEWIS Sensing
    1476,  # Wesar Intelligence
    1413,  # Pangolin Robotics
    1475,  # Stäubli Robotics
    1484,  # Yamaha Motor (Robotics Division)
    1477,  # Yamaha Motor Robotics
]

# Only patch when CRM website is blank.
WEBSITE_PATCHES: dict[int, str] = {
    1479: "https://www.efort.com.cn/en/",
    1480: "https://muka-tech.com/",
    1476: "https://www.wesar.cn/",
    1413: "https://www.csjbot.com/",
    1475: "https://www.staubli.com/global/en/robotics.html",
    1484: "https://global.yamaha-motor.com/business/robot/",
    1477: "https://global.yamaha-motor.com/business/robot/",
}

BACKLOG = _RESEARCH_DIR / "staging" / "reports" / "enrichment-backlog.json"
STATUS = _RESEARCH_DIR / "staging" / "reports" / "top10-overnight-status.json"


def patch_websites(client: ResearchApiClient) -> list[dict]:
    results = []
    for cid, url in WEBSITE_PATCHES.items():
        try:
            co = client.get_company(cid)
        except Exception as exc:  # noqa: BLE001
            results.append({"company_id": cid, "error": str(exc)})
            continue
        existing = (co.get("website") or "").strip()
        if existing:
            results.append(
                {
                    "company_id": cid,
                    "name": co.get("name"),
                    "action": "keep",
                    "website": existing,
                }
            )
            continue
        try:
            client.patch_company(cid, {"website": url})
            results.append(
                {
                    "company_id": cid,
                    "name": co.get("name"),
                    "action": "patched",
                    "website": url,
                }
            )
            print(f"website patched {cid} {co.get('name')} -> {url}", flush=True)
        except Exception as exc:  # noqa: BLE001
            results.append({"company_id": cid, "name": co.get("name"), "error": str(exc)})
            print(f"website patch fail {cid}: {exc}", flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-patch",
        action="store_true",
        help="Do not patch blank websites before overnight",
    )
    parser.add_argument(
        "--max-robots-per-company",
        type=int,
        default=0,
        help="Forwarded to overnight_queue_enrich (0=unlimited)",
    )
    args = parser.parse_args()

    ids = list(TOP10)
    if BACKLOG.is_file():
        try:
            data = json.loads(BACKLOG.read_text(encoding="utf-8"))
            top = data.get("top_remaining") or []
            if top:
                ids = [int(c["company_id"]) for c in top[:10]]
                print(f"Loaded top10 from backlog: {ids}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN backlog read failed ({exc}); using hardcoded TOP10", flush=True)

    client = ResearchApiClient()
    patch_results: list[dict] = []
    if not args.skip_patch and not args.dry_run:
        patch_results = patch_websites(client)

    plan = {
        "company_ids": ids,
        "website_patches": patch_results,
        "mode": "overnight_gap_only",
        "dry_run": args.dry_run,
        "note": (
            "Gap-only auto enrich (no Gemini, no curated visual QA). "
            "Check overnight-queue-progress.json in the morning."
        ),
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"status -> {STATUS}", flush=True)

    cmd = [
        sys.executable,
        "-u",
        str(_RESEARCH_DIR / "overnight_queue_enrich.py"),
        "--company-ids",
        ",".join(str(i) for i in ids),
    ]
    if args.max_robots_per_company:
        cmd.extend(["--max-robots-per-company", str(args.max_robots_per_company)])
    if args.dry_run:
        cmd.append("--dry-run")

    print("exec:", " ".join(cmd), flush=True)
    # Replace process so this wrapper's exit code matches overnight.
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    raise SystemExit(main())
