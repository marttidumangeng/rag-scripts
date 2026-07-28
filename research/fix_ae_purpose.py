#!/usr/bin/env python3
"""
fix_ae_purpose.py
-----------------
Fix missing `purpose` field on 7 AE Robotics robots that were identified
by the daily validation script as having an empty purpose field.

Robots to fix:
  4834 AE AIR10-A Industrial Robot       → Manufacturing & Industrial
  4833 AE AIR8-A Industrial Robot        → Manufacturing & Industrial
  4832 AE AIR7L-B Arc Welding Robot      → Manufacturing & Industrial
  4831 AE AIR3-A Industrial Robotic Arm  → Manufacturing & Industrial
  4821 Delta Robot AR-1000D              → Manufacturing & Industrial
  4820 Delta Robot AR-800D               → Manufacturing & Industrial
  4819 Delta Robot AR-500D               → Manufacturing & Industrial

Usage:
    python fix_ae_purpose.py --dry-run
    python fix_ae_purpose.py
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
load_research_env()

from api_client import ResearchApiClient

# Robot IDs → purpose value
FIXES = {
    4834: "Manufacturing & Industrial",  # AE AIR10-A Industrial Robot
    4833: "Manufacturing & Industrial",  # AE AIR8-A Industrial Robot
    4832: "Manufacturing & Industrial",  # AE AIR7L-B Arc Welding Robot
    4831: "Manufacturing & Industrial",  # AE AIR3-A Industrial Robotic Arm
    4821: "Manufacturing & Industrial",  # Delta Robot AR-1000D
    4820: "Manufacturing & Industrial",  # Delta Robot AR-800D
    4819: "Manufacturing & Industrial",  # Delta Robot AR-500D
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix missing purpose on AE Robotics robots")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    client = ResearchApiClient()
    fixed = failed = 0

    for rid, purpose in FIXES.items():
        print(f"[{rid}] purpose → {purpose!r}")
        if args.dry_run:
            print("  [DRY RUN] Would patch")
            fixed += 1
            continue
        try:
            client._patch(f"robots/robots/{rid}/", {"purpose": purpose})
            print("  ✓ Patched")
            fixed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1
        time.sleep(0.15)

    print(f"\nSummary: fixed={fixed}, failed={failed}")


if __name__ == "__main__":
    main()
