"""Probe company 57 (Kuka Robotics) vs 1396 (KUKA) for merge candidacy."""

from __future__ import annotations

import json
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

OUT = _RESEARCH_DIR / "staging" / "reports" / "kuka57_probe.json"


def get_company(client: ResearchApiClient, cid: int) -> dict:
    for path in (f"companies/companies/{cid}/", f"companies/{cid}/"):
        try:
            return client._get(path)
        except Exception as e:  # noqa: BLE001
            last = str(e)
    return {"_err": last}


def main() -> int:
    client = ResearchApiClient()
    for cid in (57, 1396):
        co = get_company(client, cid)
        print(f"=== COMPANY {cid} ===")
        if isinstance(co, dict):
            for k in (
                "id",
                "name",
                "slug",
                "website",
                "website_url",
                "country",
                "description",
                "status",
                "logo_url",
            ):
                if k in co:
                    v = co.get(k)
                    if isinstance(v, str) and len(v) > 140:
                        v = v[:140] + "..."
                    print(f"  {k}: {v}")
            # dump keys that look relevant
            for k, v in sorted(co.items()):
                lk = k.lower()
                if any(x in lk for x in ("country", "web", "name", "slug", "domain")) and k not in {
                    "id",
                    "name",
                    "slug",
                    "website",
                    "website_url",
                    "country",
                    "description",
                    "status",
                    "logo_url",
                }:
                    print(f"  {k}: {v}")
        print()

    robots57 = robots1396 = None
    for a in range(12):
        try:
            robots57 = client.list_robots_for_company(57)
            robots1396 = client.list_robots_for_company(1396)
            break
        except Exception as e:  # noqa: BLE001
            print(f"list retry {a}: {e}", file=sys.stderr)
            time.sleep(5)
    assert robots57 is not None and robots1396 is not None

    print(f"count 57={len(robots57)} 1396={len(robots1396)}")
    print("status 57", Counter(str(r.get("status")) for r in robots57))
    print("names 57:")
    for r in sorted(robots57, key=lambda x: int(x["id"])):
        url = (r.get("url") or "")[:80]
        print(f"  {r['id']} | {r.get('name')} | status={r.get('status')} | url={url}")

    n57 = {(r.get("name") or "").strip().upper(): r for r in robots57}
    n1396 = {(r.get("name") or "").strip().upper(): r for r in robots1396}
    overlap = sorted(set(n57) & set(n1396))
    print(f"exact name overlap: {len(overlap)}")
    for n in overlap:
        a, b = n57[n], n1396[n]
        print(f"  SAME: {n} | 57={a['id']} | 1396={b['id']}")

    # fuzzy: normalize spaces/hyphens
    def norm(s: str) -> str:
        return " ".join((s or "").upper().replace("-", " ").replace("_", " ").split())

    f57 = {norm(r.get("name") or ""): r for r in robots57}
    f1396 = {norm(r.get("name") or ""): r for r in robots1396}
    foverlap = sorted(set(f57) & set(f1396))
    print(f"normalized name overlap: {len(foverlap)}")
    for n in foverlap:
        if n not in {norm(x) for x in overlap}:
            print(f"  NORM: {n} | 57={f57[n]['id']} | 1396={f1396[n]['id']}")

    rows = []
    for r in robots57:
        rows.append(
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "url": r.get("url"),
                "status": r.get("status"),
                "description": (r.get("description") or "")[:200],
                "desc_len": len((r.get("description") or "").strip()),
                "features": (r.get("features") or "")[:200],
                "feat_len": len((r.get("features") or "").strip()),
                "image": r.get("image") or r.get("s3_image"),
                "payload_kg": r.get("payload_kg"),
                "reach_mm": r.get("reach_mm"),
                "release_year": r.get("release_year"),
                "family_name": r.get("family_name"),
                "manufacturer_country": r.get("manufacturer_country"),
                "categories": r.get("categories"),
                "uses": r.get("uses") or r.get("use_keys"),
                "n_videos": len(r.get("videos") or r.get("video_urls") or []),
                "availability": r.get("availability_status") or r.get("availability_status_id"),
                "price_min": r.get("price_min"),
                "price_max": r.get("price_max"),
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "company_57": get_company(client, 57),
                "company_1396": get_company(client, 1396),
                "overlap_exact": overlap,
                "overlap_normalized": foverlap,
                "robots_57": rows,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
