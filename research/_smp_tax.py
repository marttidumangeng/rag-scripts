"""Print taxonomy keys useful for SMP enrich."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient


def main() -> int:
    c = ResearchApiClient()
    r = c._get("robots/robots/5261/")
    print(
        json.dumps(
            {
                "uses": [
                    u.get("key") if isinstance(u, dict) else u for u in (r.get("uses") or [])
                ],
                "industries": [
                    i.get("key") if isinstance(i, dict) else i
                    for i in (r.get("industries") or [])
                ],
                "categories": [
                    cat.get("slug") if isinstance(cat, dict) else cat
                    for cat in (r.get("categories") or [])
                ],
                "movement": [
                    m.get("key") if isinstance(m, dict) else m
                    for m in (r.get("movement_types") or [])
                ],
                "tags": r.get("tags"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    for path, label in [
        ("robots/uses/", "uses"),
        ("robots/industries/", "industries"),
        ("robots/movement-types/", "movement"),
    ]:
        rows = c._get(path)
        keys = sorted((x.get("key") or "") for x in rows if x.get("key"))
        print(f"\n== {label} ({len(keys)}) ==")
        for k in keys:
            if any(
                w in k
                for w in (
                    "secur",
                    "patrol",
                    "inspect",
                    "surveil",
                    "guard",
                    "monitor",
                    "deliver",
                    "enviro",
                    "agricult",
                    "logistics",
                    "defense",
                    "oil",
                    "energy",
                    "facility",
                    "clean",
                    "transport",
                    "service",
                    "research",
                )
            ):
                print(" ", k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
