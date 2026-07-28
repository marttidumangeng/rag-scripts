"""Enrich KUKA (company 1396) features with OEM spec data from the family spec tables.

WHY NOT force-overwrite: the 73 robots flagged `feat<40` do NOT hold junk. They hold
short but valid, model-distinct application keywords ("Very high payload, robust,
precise" / "Heavy assembly, force-sensitive tasks, human-robot collaboration"), and
their descriptions are good model-specific prose. The <40-char flag is a LENGTH
heuristic, not a junk detector — unlike EFORT (identical footer junk), wiping here
would destroy real content. So this APPENDS the OEM spec line; it never wipes.

Source: kuka_recon.py scrapes each family page's server-rendered products table
(`js-item list__item` → data-name / data-load-capacity / data-reach + Construction
type / Mounting positions / Protection class / Controller). KUKA labels payload
"Total load", which is why naive keyword scrapes missed it and left these terse.

payload_kg / reach_mm / ip_rating are NOT Robot columns (see Comau + Jaten lessons),
so these OEM specs can only live in features — which is exactly the point of this pass.

Name matching: DB appends suffixes KUKA's table omits (" IONTEC", " ultra", " nano")
— normalized before lookup. Idempotent: skips rows already carrying the spec marker.

Usage:
  python fix_kuka_features.py            # dry-run
  python fix_kuka_features.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1396
CATALOG = _RESEARCH_DIR / "staging" / "reports" / "kuka-recon.json"
MARKER = "Total load:"

_SUFFIX = re.compile(r"\s+(IONTEC|ultra|nano|AGILUS|titan|CYBERTECH|QUANTEC|FORTEC|Delta)\b", re.I)

# Payload token in the model name, e.g. "KR 340 R3200-2 PA" -> 340. Used as a GUARD:
# an alias is only accepted when the catalog row's Total load equals the name's payload.
_PAYLOAD_RE = re.compile(r"^(?:KR|LBR)\s+(\d{1,4})\b", re.I)


def name_payload(name: str) -> int | None:
    m = _PAYLOAD_RE.match(name.strip())
    return int(m.group(1)) if m else None


def catalog_load(rec: dict[str, Any]) -> int | None:
    m = re.search(r"(\d{1,4})", (rec.get("total_load") or ""))
    return int(m.group(1)) if m else None

# Order matters: this is the reader-facing spec line.
FIELDS = [
    ("total_load", "Total load"),
    ("max_reach", "Maximum reach"),
    ("construction_type", "Construction type"),
    ("mounting_positions", "Mounting positions"),
    ("protection_class", "Protection class"),
    ("version_environment", "Version environment"),
    ("controller", "Controller"),
]


def candidates(name: str) -> list[tuple[str, bool]]:
    """(alias, trusted) variants, most literal first.

    KUKA's table and our DB disagree in two DIFFERENT ways, which need different trust:

    TRUSTED — a family word is appended to the DB name; dropping it cannot change
    which robot is meant:
      DB "KR 50 R2100 IONTEC" -> KUKA "KR 50 R2100"
      DB "KR 3 D1200 Delta"   -> KUKA "KR 3 D1200"

    GUARDED — a generation/suffix hop, which CAN change the robot:
      DB "KR 340 R3200 PA"     -> KUKA "KR 340 R3200-2 PA"   (DB drops the -2)
      DB "KR 120 R3200-1 PA"   -> KUKA "KR 120 R3200 PA"     (DB adds -1 for gen-1)
      DB "KR 8 R1440 arc HW-2" -> KUKA "KR 8 R1440-2 arc HW" (suffix shuffle)
    """
    n = re.sub(r"\s+", " ", name).strip()
    out: list[tuple[str, bool]] = [(n, True)]
    s = _SUFFIX.sub("", n).strip()
    if s != n:
        out.append((s, True))  # family-word strip: same robot
    for base, _ in list(out):
        m = re.match(r"^(.*?)\s+arc HW-(\d)$", base, re.I)
        if m:
            out.append((f"{m.group(1)}-{m.group(2)} arc HW", False))
        if base.endswith(" PA"):
            stem = base[:-3]
            if not re.search(r"-\d$", stem):
                out.append((f"{stem}-2 PA", False))
            m1 = re.match(r"^(.*?)-1$", stem)
            if m1:
                out.append((f"{m1.group(1)} PA", False))
    seen, dedup = set(), []
    for a, t in out:
        if a not in seen:
            seen.add(a); dedup.append((a, t))
    return dedup


def match(name: str, catalog: dict[str, Any]) -> str | None:
    """Exact/family-strip are trusted; generation hops are payload-guarded.

    The guard matters: KUKA's -2 arms are a NEWER GENERATION, not a rename
    (different controller: KR C4 vs KR C5). A bare gen-1 name like "KR 120 R2700"
    is never hopped onto "KR 120 R2700-2" — those stay unmatched on purpose.

    The guard is NOT applied to family-word strips because KUKA's "Total load" is
    payload + supplementary load, so it legitimately exceeds the name's number on
    some families (KR 3 D1200 -> Total load 6 kg). Guarding those would wrongly
    reject a correct match.
    """
    upper = {k.upper(): k for k in catalog}
    want = name_payload(name)
    for alias, trusted in candidates(name):
        key = alias if alias in catalog else upper.get(alias.upper())
        if not key:
            continue
        if trusted:
            return key
        got = catalog_load(catalog[key])
        if want is None or (got is not None and got == want):
            return key
    return None


def spec_line(rec: dict[str, Any]) -> str:
    bits = []
    for key, label in FIELDS:
        v = (rec.get(key) or "").strip()
        if v and v.lower() not in ("standard",) or (v and key in ("construction_type", "version_environment")):
            bits.append(f"{label}: {v}")
    return " | ".join(bits)


def main() -> int:
    ap = argparse.ArgumentParser(description="Append KUKA OEM specs to features")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not CATALOG.is_file():
        print(f"ERROR: {CATALOG} missing — run kuka_recon.py first", file=sys.stderr)
        return 1
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID); break
        except Exception as e:
            print(f"list retry {a}: {str(e)[:60]}", file=sys.stderr); time.sleep(5)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr); return 1

    plan = []
    unmatched = []
    for r in sorted([x for x in robots if str(x.get("status") or "").lower() == "pending_review"],
                    key=lambda x: x["id"]):
        key = match(r["name"], catalog)
        if not key:
            unmatched.append(r["name"]); continue
        rec = catalog[key]
        line = spec_line(rec)
        if not line:
            continue
        cur = (r.get("features") or "").strip()
        if MARKER in cur:
            continue  # idempotent
        merged = f"{cur} | {line}" if cur else line
        plan.append({"id": int(r["id"]), "name": r["name"], "matched": key,
                     "old_len": len(cur), "new_len": len(merged), "features": merged[:1900]})

    print(f"matched+to-update: {len(plan)} | unmatched: {len(unmatched)}")
    for p in plan[:6]:
        print(f"\n  [{p['id']}] {p['name']}  (matched '{p['matched']}')  {p['old_len']}->{p['new_len']} chars")
        print(f"     {p['features'][:210]}")
    print(f"\n  ... unmatched ({len(unmatched)}): {unmatched[:10]}")

    preview = _RESEARCH_DIR / "staging" / "reports" / "kuka-features-preview.json"
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not plan:
        print("Nothing to do."); return 0
    if not args.apply:
        print(f"\nPreview: {preview}. Re-run with --apply")
        return 0

    ok = fail = 0
    for p in plan:
        try:
            # DRF PATCH: bulk-import patch mode would NOT overwrite the existing
            # non-blank `features`, and we are deliberately appending to it.
            client._patch(f"robots/robots/{p['id']}/", {"features": p["features"]})
            ok += 1
            print(f"  ok {p['id']} {p['name']} ({p['old_len']}->{p['new_len']})")
        except Exception as exc:
            fail += 1
            print(f"  FAIL {p['id']}: {str(exc)[:80]}", file=sys.stderr)
    out = {"ok": fail == 0, "updated": ok, "failed": fail, "unmatched": len(unmatched)}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "kuka-features-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
