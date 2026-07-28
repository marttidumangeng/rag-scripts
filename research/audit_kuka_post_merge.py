"""Audit company 1396 after merge of company 57."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
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

EX57 = {62, 211, 213, 342, 2092, 2097, 2102, 2107, 2111, 2114, 2119, 2122, 2126, 2129, 2132}
OUT = _RESEARCH_DIR / "staging" / "reports" / "kuka_post_merge.json"


def main() -> int:
    client = ResearchApiClient()

    for cid in (57, 1396):
        try:
            co = client._get(f"companies/companies/{cid}/")
            print(
                f"company {cid}: name={co.get('name')} slug={co.get('slug')} "
                f"web={co.get('website')}"
            )
        except Exception as e:  # noqa: BLE001
            print(f"company {cid}: ERR {e}")

    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(1396)
            break
        except Exception as e:  # noqa: BLE001
            print(f"retry {a}: {e}")
            time.sleep(5)
    assert robots is not None

    try:
        r57 = client.list_robots_for_company(57)
        print(f"company 57 robot count: {len(r57)}")
    except Exception as e:  # noqa: BLE001
        print(f"company 57 list: {e}")

    print(f"company 1396 robot count: {len(robots)}")
    found = [r for r in robots if int(r["id"]) in EX57]
    print(f"ex-57 robots now on 1396: {len(found)} {sorted(int(r['id']) for r in found)}")

    fk: Counter[str] = Counter()
    robotics_keys = []
    for r in robots:
        k = (r.get("family_key") or "").strip()
        if k.startswith("kuka-robotics:"):
            fk["kuka-robotics"] += 1
            robotics_keys.append((int(r["id"]), r.get("name"), k))
        elif k.startswith("kuka:"):
            fk["kuka"] += 1
        elif k:
            fk["other"] += 1
        else:
            fk["(empty)"] += 1
    print(f"family_key prefixes: {dict(fk)}")
    if robotics_keys:
        print("still kuka-robotics:* keys:")
        for rid, name, k in robotics_keys:
            print(f"  {rid} {name} {k}")

    by_name: dict[str, list[int]] = defaultdict(list)
    for r in robots:
        by_name[(r.get("name") or "").strip().upper()].append(int(r["id"]))
    dups = {n: ids for n, ids in by_name.items() if len(ids) > 1}
    print(f"exact name dups: {len(dups)}")
    for n, ids in sorted(dups.items()):
        print(f"  {n}: {ids}")

    print("ex-57 detail:")
    for r in sorted(found, key=lambda x: int(x["id"])):
        print(
            f"  {r['id']} {r.get('name')} key={r.get('family_key')} "
            f"fam={r.get('family_name')} status={r.get('status')}"
        )

    OUT.write_text(
        json.dumps(
            {
                "count_1396": len(robots),
                "ex57_on_1396": sorted(int(r["id"]) for r in found),
                "family_key_prefixes": dict(fk),
                "robotics_keys": [
                    {"id": rid, "name": name, "key": k} for rid, name, k in robotics_keys
                ],
                "name_dups": dups,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
