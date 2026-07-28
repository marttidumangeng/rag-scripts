"""Re-audit company 57 after enrich."""

from __future__ import annotations

import sys
import time
from collections import Counter
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
from audit_kuka57 import approx_flags


def main() -> int:
    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(57)
            break
        except Exception as e:  # noqa: BLE001
            print(f"retry {a}: {e}")
            time.sleep(5)
    assert robots

    ctr: Counter[str] = Counter()
    for r in sorted(robots, key=lambda x: int(x["id"])):
        full = client._get(f"robots/robots/{r['id']}/")
        flags = approx_flags(full, "kuka.com")
        must = [f for f in flags if f != "missing_price"]
        for f in must:
            ctr[f] += 1
        feat = full.get("features") or ""
        desc = full.get("description") or ""
        print(f"{full['id']} {full.get('name')}")
        print(f"  must_flags={must}")
        print(
            f"  desc={len(desc.strip())} feat={len(feat.strip())} "
            f"purpose={(full.get('purpose') or '')[:70]}"
        )
        print(f"  url={(full.get('url') or '')[:75]}")
        print(
            f"  y={full.get('release_year')} p={full.get('payload_kg')} "
            f"r={full.get('reach_mm')} fam={full.get('family_name')} "
            f"key={full.get('family_key')}"
        )
        tags = full.get("tags") or []
        print(f"  cats={full.get('categories')} tags={tags[:6]}")
        print(f"  feat_preview={feat[:100]!r}")
        time.sleep(0.05)

    print("\nmust flag counts:", dict(ctr.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
