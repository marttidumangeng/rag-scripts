"""Remap post-merge family_key kuka-robotics:* → kuka:* on company 1396.

Usage:
  python fix_kuka_post_merge_family_keys.py            # dry-run
  python fix_kuka_post_merge_family_keys.py --apply
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1396

# Explicit remaps (avoid kuka:kuka-omnimove).
REMAP = {
    "kuka-robotics:kr-agilus": "kuka:kr-agilus",
    "kuka-robotics:kr-cybertech": "kuka:kr-cybertech",
    "kuka-robotics:kr-cybertech-nano": "kuka:kr-cybertech-nano",
    "kuka-robotics:kr-iontec": "kuka:kr-iontec",
    "kuka-robotics:kr-fortec": "kuka:kr-fortec",
    "kuka-robotics:kr-fortec-pa": "kuka:kr-fortec-pa",
    "kuka-robotics:kr-quantec": "kuka:kr-quantec",
    "kuka-robotics:kr-delta": "kuka:kr-delta",
    "kuka-robotics:kr-1000-titan": "kuka:kr-1000-titan",
    "kuka-robotics:lbr-iisy": "kuka:lbr-iisy",
    "kuka-robotics:lbr-iiwa": "kuka:lbr-iiwa",
    "kuka-robotics:kmp": "kuka:kmp",
    "kuka-robotics:kuka-omnimove": "kuka:omnimove",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:  # noqa: BLE001
            print(f"retry {a}: {e}")
            time.sleep(5)
    if robots is None:
        return 1

    plan = []
    for r in robots:
        old = (r.get("family_key") or "").strip()
        if not old.startswith("kuka-robotics:"):
            continue
        new = REMAP.get(old)
        if not new:
            # fallback: swap prefix
            new = "kuka:" + old.split(":", 1)[1]
            if new.startswith("kuka:kuka-"):
                new = "kuka:" + new[len("kuka:kuka-") :]
        plan.append((int(r["id"]), r.get("name"), old, new))

    print(f"to_remap={len(plan)}")
    for rid, name, old, new in plan:
        print(f"  {rid} {name}: {old} → {new}")

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    ok = fail = 0
    for rid, name, old, new in plan:
        try:
            patched = client._patch(f"robots/robots/{rid}/", {"family_key": new})
            print(f"ok {rid} {patched.get('family_key')}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {rid} {name}: {exc}")
            fail += 1
        time.sleep(0.08)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
