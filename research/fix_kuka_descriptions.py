"""Rewrite KUKA depth-import descriptions from OEM facts only (no invented padding).

Sources (in order): typed payload_kg/reach_mm, Robot.features OEM table lines,
family_name. Never invent applications, industries, or marketing claims.

Usage:
  python fix_kuka_descriptions.py            # dry-run
  python fix_kuka_descriptions.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1396
MIN_ID = 5374
MIN_DESC = 100  # robots.quality.MIN_DESCRIPTION_CHARS


def _feat_map(features: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (features or "").splitlines():
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("External "):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        # drop citation tail like "(OEM family table)"
        val = re.sub(r"\s*\(OEM family table\)\s*$", "", val).strip()
        if key and val:
            out[key] = val
    return out


def _num(v: Any) -> str | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return f"{f:g}"
    except (TypeError, ValueError):
        return None


def build_description(robot: dict[str, Any]) -> str | None:
    """Return a fact-only description, or None if we lack enough OEM facts."""
    name = (robot.get("name") or "").strip()
    if not name:
        return None

    fam = (robot.get("family_name") or "").strip()
    feats = _feat_map(robot.get("features") or "")

    payload = _num(robot.get("payload_kg"))
    if not payload:
        m = re.search(r"([\d.]+)\s*kg", feats.get("total load", ""), re.I)
        if m:
            payload = m.group(1)

    reach = _num(robot.get("reach_mm"))
    if not reach:
        m = re.search(r"([\d.]+)\s*mm", feats.get("maximum reach", ""), re.I)
        if m:
            reach = m.group(1)

    env = feats.get("version / environment") or feats.get("version environment") or ""
    construction = feats.get("construction type") or ""
    protection = feats.get("protection class") or ""
    mounting = feats.get("mounting positions") or ""
    controller = feats.get("controller") or ""

    # Need at least payload or reach from OEM — otherwise refuse (no invention).
    if not payload and not reach:
        return None

    bits: list[str] = []
    if fam:
        bits.append(f"KUKA {fam} robot {name}.")
    else:
        bits.append(f"KUKA industrial robot {name}.")

    spec_bits: list[str] = []
    if payload:
        spec_bits.append(f"total load {payload} kg")
    if reach:
        spec_bits.append(f"maximum reach {reach} mm")
    if spec_bits:
        # Capitalize first letter for sentence start
        first = spec_bits[0][0].upper() + spec_bits[0][1:]
        rest = spec_bits[1:]
        bits.append(", ".join([first, *rest]) + ".")

    # Only append OEM table attributes that are present — no filler.
    detail_bits: list[str] = []
    if construction and construction.lower() not in {"standard", "n/a", "-"}:
        detail_bits.append(f"Construction type: {construction}")
    if env and env.lower() not in {"standard", "n/a", "-"}:
        detail_bits.append(f"Environment: {env}")
    if protection:
        detail_bits.append(f"Protection: {protection}")
    if mounting:
        detail_bits.append(f"Mounting: {mounting}")
    if controller and controller.lower() not in {"n/a", "-", "none"}:
        detail_bits.append(f"Controller: {controller}")
    if detail_bits:
        bits.append(" ".join(f"{b}." for b in detail_bits))

    desc = " ".join(bits)
    desc = re.sub(r"\s+", " ", desc).strip()
    # Fix double periods from detail join edge cases
    desc = re.sub(r"\.\.+", ".", desc)
    return desc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--min-len", type=int, default=MIN_DESC)
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:  # noqa: BLE001
            print(f"list retry {a}: {e}", file=sys.stderr)
            time.sleep(5)
    if robots is None:
        return 1

    targets = [
        r
        for r in robots
        if int(r.get("id") or 0) >= MIN_ID
        and (not args.ids or int(r["id"]) in set(args.ids))
        and len((r.get("description") or "").strip()) < args.min_len
    ]
    targets.sort(key=lambda r: int(r["id"]))

    planned: list[tuple[dict, str]] = []
    skipped = 0
    for r in targets:
        # Need full features — list payload may be truncated; refetch if short
        feats = r.get("features") or ""
        if len(feats) < 80:
            r = client._get(f"robots/robots/{r['id']}/")
        desc = build_description(r)
        if not desc:
            print(f"SKIP {r['id']} {r.get('name')}: insufficient OEM facts")
            skipped += 1
            continue
        planned.append((r, desc))
        print(
            f"{r['id']} {r.get('name')}: {len(r.get('description') or '')}→{len(desc)} "
            f"{'OK' if len(desc) >= args.min_len else 'STILL-SHORT'}"
        )
        print(f"  {desc}")

    still_short = sum(1 for _, d in planned if len(d) < args.min_len)
    print(
        f"\nplanned={len(planned)} skipped={skipped} still_short_after={still_short}"
    )
    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0 if still_short == 0 and skipped == 0 else 1

    ok = fail = 0
    for r, desc in planned:
        rid = int(r["id"])
        note = (
            f"[DESC 2026-07-18] Rewrote description from OEM family-table facts only "
            f"(payload/reach/environment/construction/IP/mounting/controller); no invented claims."
        )
        notes = (r.get("notes") or "").strip()
        if note not in notes:
            notes = (note + "\n---\n" + notes).strip() if notes else note
        try:
            patched = client._patch(
                f"robots/robots/{rid}/",
                {"description": desc, "notes": notes, "source_locale": "en"},
            )
            print(f"ok {rid} len={len(patched.get('description') or '')}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {rid}: {exc}")
            fail += 1
        time.sleep(0.08)

    print(f"\nDONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
