"""Audit approved Universal Robots (192): CDN health + variant coverage."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from fix_universal_robots import normalize_model
from verify_cdn_images import probe_url

COMPANY_ID = 192
OUT = _RESEARCH_DIR / "staging" / "reports" / "ur-approved-audit.json"

# Current OEM catalog (marketing site / recent launches). Legacy CB kept as optional.
CURRENT_CATALOG = {
    "UR Series": ["UR8 Long", "UR15", "UR18", "UR20", "UR30"],
    "e-Series": ["UR3e", "UR5e", "UR7e", "UR10e", "UR12e", "UR16e"],
    "CB-Series (legacy)": ["UR3", "UR5", "UR10"],
}


def main() -> int:
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    by_status: dict[str, list] = defaultdict(list)
    for r in robots:
        by_status[str(r.get("status") or "").lower()].append(r)

    print("status counts:")
    for st, rows in sorted(by_status.items(), key=lambda x: -len(x[1])):
        print(f"  {st}: {len(rows)}")

    approved = by_status.get("approved", []) + by_status.get("published", [])
    # de-dupe by id
    seen_ids: set[int] = set()
    uniq = []
    for r in approved:
        rid = int(r["id"])
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        uniq.append(r)
    approved = uniq
    print(f"\napproved/published targets: {len(approved)}")

    cdn_ok = cdn_bad = 0
    no_img = 0
    hash_by_model: dict[str, set[str]] = defaultdict(set)
    hash_owners: dict[str, list[tuple[int, str]]] = defaultdict(list)
    models_present: dict[str, list[int]] = defaultdict(list)
    rows_out = []

    for r in sorted(approved, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        # refresh for image fields
        full = client._get(f"robots/robots/{rid}/")
        name = full.get("name") or ""
        model = normalize_model(name) or "?"
        models_present[model].append(rid)
        img = (full.get("s3_image") or full.get("image") or "").strip()
        status = full.get("status")
        if not img:
            no_img += 1
            cdn_bad += 1
            print(f"FAIL {rid} {model}: no image")
            rows_out.append({"id": rid, "model": model, "name": name, "ok": False, "error": "no_image"})
            continue
        check = probe_url(img)
        ok = bool(check.get("ok"))
        if ok:
            cdn_ok += 1
            # hash bytes for cross-model contamination
            try:
                data = requests.get(img, timeout=60).content
                h = hashlib.md5(data).hexdigest()
                hash_by_model[model].add(h)
                hash_owners[h].append((rid, model))
                size = len(data)
            except Exception as exc:  # noqa: BLE001
                h = ""
                size = 0
                print(f"WARN {rid} hash fail: {exc}")
        else:
            cdn_bad += 1
            h = ""
            size = 0
        mark = "OK" if ok else "FAIL"
        print(
            f"{mark} {rid} {model:<10} HTTP {check.get('status')} "
            f"bytes={size} md5={h[:12] or '-'} {(img[:70])}"
        )
        rows_out.append(
            {
                "id": rid,
                "model": model,
                "name": name,
                "status": status,
                "ok": ok,
                "url": img,
                "http": check.get("status"),
                "error": check.get("error"),
                "md5": h,
                "bytes": size,
            }
        )

    # cross-model same-hash (same model dups are OK for duplicate records)
    print("\n=== cross-model hero hash collisions ===")
    collisions = 0
    for h, owners in hash_owners.items():
        models = {m for _, m in owners}
        if len(models) > 1:
            # UR8 and UR8 Long share product — allow
            if models <= {"UR8", "UR8 Long"}:
                print(f"  OK shared UR8/UR8 Long md5={h[:12]} owners={owners}")
                continue
            collisions += 1
            print(f"  COLLISION md5={h[:12]} models={sorted(models)} owners={owners}")
    if collisions == 0:
        print("  none (aside from UR8/UR8 Long alias if present)")

    print("\n=== model coverage (approved) ===")
    for series, models in CURRENT_CATALOG.items():
        print(f"  {series}:")
        for m in models:
            ids = models_present.get(m) or []
            mark = "HAVE" if ids else "MISSING"
            print(f"    {mark} {m}: {ids or '—'}")

    extra = sorted(set(models_present) - {m for ms in CURRENT_CATALOG.values() for m in ms})
    if extra:
        print("  other models in approved:")
        for m in extra:
            print(f"    {m}: {models_present[m]}")

    # duplicate display-name / model clusters
    print("\n=== approved model clusters (near-dupes) ===")
    for m, ids in sorted(models_present.items(), key=lambda x: -len(x[1])):
        if len(ids) > 1:
            print(f"  {m}: {ids}")

    # scrape live OEM product cards for names we might have missed
    print("\n=== OEM products page model tokens ===")
    oem_models = set()
    try:
        html = requests.get(
            "https://www.universal-robots.com/products/",
            timeout=45,
            headers={"User-Agent": "Mozilla/5.0"},
        ).text
        for m in re.findall(r"/products/(ur[\w-]+)/", html, re.I):
            slug = m.lower().replace("-robot", "").replace("-", " ")
            # normalize
            slug = re.sub(r"\s+", " ", slug).strip()
            if slug.startswith("ur"):
                oem_models.add(slug)
        # also storyblok/product names
        for m in re.findall(r"\b(UR(?:\d+\s*Long|\d+e?))\b", html):
            oem_models.add(m.upper().replace("E", "e") if m.lower().endswith("e") else m.upper().replace(" LONG", " Long"))
        print(f"  tokens found: {sorted(oem_models)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  scrape fail: {exc}")

    report = {
        "company_id": COMPANY_ID,
        "approved_count": len(approved),
        "cdn_ok": cdn_ok,
        "cdn_bad": cdn_bad,
        "no_img": no_img,
        "cross_model_collisions": collisions,
        "models_present": {k: v for k, v in models_present.items()},
        "catalog": CURRENT_CATALOG,
        "rows": rows_out,
        "status_counts": {k: len(v) for k, v in by_status.items()},
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nCDN approved: ok={cdn_ok} bad={cdn_bad} no_img={no_img} -> {OUT}")
    return 1 if cdn_bad or collisions else 0


if __name__ == "__main__":
    raise SystemExit(main())
