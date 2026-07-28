"""Mark ADLINK (1374) skipped for US overnight drain — Taiwan HQ."""
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

# Prefer research CLI state mark when available; also triage done set.
DONE = _RESEARCH / "state" / "content_queue_done.json"
PROCESSED = _RESEARCH / "state" / "processed_ids.json"


def main() -> int:
    c = ResearchApiClient()
    co = c._get("companies/1374/")
    print("ADLINK website=", co.get("website"), "country=", co.get("country"))
    # Soft-set country TW if API accepts — do not invent if field differs
    try:
        countries = c._get("countries/")
        rows = countries if isinstance(countries, list) else countries.get("results") or []
        tw = next((x for x in rows if (x.get("code") or "").upper() == "TW"), None)
        if tw and not co.get("country"):
            c._patch("companies/1374/", {"country_id": tw["id"]})
            print("set country_id TW", tw["id"])
        elif tw:
            print("country already set or skip patch; tw_id=", tw["id"])
    except Exception as e:
        print("country patch warn", e)

    for path in (DONE, PROCESSED):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if "companies" in data and isinstance(data["companies"], list):
            if 1374 not in data["companies"]:
                data["companies"].append(1374)
                data["companies"] = sorted(set(data["companies"]))
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                print("added 1374 to", path.name)
            else:
                print("already in", path.name)
        elif "company_ids" in data:
            ids = data["company_ids"]
            if 1374 not in ids:
                ids.append(1374)
                data["company_ids"] = sorted(set(ids))
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                print("added 1374 company_ids", path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
