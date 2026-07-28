"""Retry copy-media for Universal Robots IDs that got HTTP 502."""
from __future__ import annotations

import sys
import time
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from fix_universal_robots import copy_media, _internal_secret

IDS = [4322, 4750, 4875]


def main() -> int:
    secret = _internal_secret()
    if not secret:
        print("no INTERNAL_API_SECRET")
        return 1
    for rid in IDS:
        for attempt in range(1, 6):
            cm = copy_media(rid, secret)
            print(f"{rid} attempt={attempt} -> {cm}")
            if cm == "ok":
                break
            time.sleep(3 * attempt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
