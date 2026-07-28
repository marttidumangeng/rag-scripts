#!/usr/bin/env python3
"""
patch_company_websites.py
=========================
Set the website field for companies that have robot-level URLs but no
company-level website set. This unblocks the overnight_queue_enrich.py
pipeline which requires a company website to proceed.

Run with --dry-run to preview, then without to apply.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
load_research_env()

from api_client import ResearchApiClient

# Companies to patch: (company_id, company_name, official_website)
COMPANIES = [
    (1416, "ROKAE Robotics",                        "https://www.rokae.com"),
    (1423, "Shenzhen Wellwit Robotics Co., Ltd.",   "https://wellwit.com"),
    (1400, "BORUNTE ROBOT CO., LTD",                "https://www.borunte.net"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print changes without applying them")
    args = parser.parse_args()

    client = ResearchApiClient()

    for cid, name, website in COMPANIES:
        company = client.get_company(cid)
        current_website = (company.get("website") or "").strip()
        if current_website:
            print(f"  ID {cid} {name}: already has website={current_website!r} — skipping")
            continue
        print(f"  ID {cid} {name}: set website -> {website!r}")
        if not args.dry_run:
            client._patch(f"companies/{cid}/", {"website": website})
            print(f"    OK")

    print("\nDone.")


if __name__ == "__main__":
    main()
