"""Quick probe Universal Robots (192) as alternate next company."""

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


def probe(cid: int) -> None:
    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(cid)
            break
        except Exception as e:  # noqa: BLE001
            print(f"{cid} retry {a}: {e}")
            time.sleep(5)
    assert robots is not None
    cref = {}
    if robots:
        cref = robots[0].get("company_ref") or {}
    print(
        f"\n=== {cid} {cref.get('name') if isinstance(cref, dict) else ''} "
        f"n={len(robots)} web={(cref.get('website') if isinstance(cref, dict) else '')} ==="
    )
    print("status", Counter(str(r.get("status")) for r in robots))
    pending = [r for r in robots if str(r.get("status") or "").lower() == "pending_review"]
    no_img = sum(1 for r in pending if not (r.get("image") or r.get("s3_image") or "").strip())
    no_feat = sum(1 for r in pending if len((r.get("features") or "").strip()) < 40)
    print(f"pending={len(pending)} no_img={no_img} short_feat={no_feat}")
    for r in sorted(pending, key=lambda x: int(x["id"]))[:12]:
        img = bool((r.get("image") or r.get("s3_image") or "").strip())
        print(
            f"  {r['id']} img={img} feat={len((r.get('features') or '').strip())} "
            f"{(r.get('name') or '')[:50]} | {(r.get('url') or '')[:55]}"
        )


def main() -> int:
    for cid in (192, 1413, 1475):
        probe(cid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
