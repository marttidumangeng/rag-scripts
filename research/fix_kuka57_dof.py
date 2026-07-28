"""Set factual dof on company-57 family placeholders to clear missing_specs."""

from __future__ import annotations

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

load_research_env()

from api_client import ResearchApiClient

DOF = {
    62: 6,
    2092: 6,
    2097: 4,
    2102: 7,
    2107: 7,
    2111: 6,
    2114: 6,
    2119: 6,
    2126: 6,
    2129: 6,
    2132: 6,
}


def main() -> int:
    client = ResearchApiClient()
    ok = fail = 0
    for rid, dof in DOF.items():
        try:
            patched = client._patch(f"robots/robots/{rid}/", {"dof": dof})
            print(f"ok {rid} dof={patched.get('dof')}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {rid}: {exc}")
            fail += 1
        time.sleep(0.08)
    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
