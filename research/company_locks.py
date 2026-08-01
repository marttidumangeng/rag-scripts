"""Shared cross-session company locks — the coordination gap that let a manual
sweep and the VM's automated pipeline both write to the same AgileX robots on
2026-08-01, clobbering each other's changes (see remedies/engine.py's
stale-snapshot fix for the write-side half of that incident; this is the
scan-side half: keeping the automated pipeline off a company entirely while
someone else is doing exclusive manual work on it).

A single shared JSON file in GCS, checked by every stage that builds a
per-company dispatch list. Either session can lock/unlock/list from the CLI:

    python company_locks.py --lock 1382 --hours 24 --reason "manual sweep" --by martti-session
    python company_locks.py --list
    python company_locks.py --unlock 1382

This only works if BOTH sides check it — there is no enforcement beyond that.
It fails OPEN (treats everything as unlocked) on any read error, matching the
project's existing pattern of "the gate that must not silently block is the
smoke test; everything else degrades gracefully" — a lock-file outage should
never be able to halt the whole pipeline.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_LOCKS_URI = "gs://robotaigeek-core-enrichment/locks/company_locks.json"
_GCS_PROJECT = "robotaigeek-core"
"""Always pass --project explicitly: the ambient gcloud default account/project
on shared dev machines drifts (confirmed 2026-07-31, unrelated business
account), and a lock write that silently no-ops is exactly the kind of gap
that caused the incident this module exists to prevent."""

_GCLOUD = shutil.which("gcloud") or "gcloud"
"""subprocess.run(["gcloud", ...]) silently fails to find gcloud on Windows,
where it's a .cmd wrapper, not a plain executable — shutil.which resolves the
real path (with extension) so this works from a dev machine, not just the
Linux VM. Falls back to the bare name so PATH resolution still gets a chance
on POSIX if `which` somehow comes up empty."""


def _read_locks_raw() -> dict[str, Any]:
    """Fetch + parse the shared lock file. `{}` on any error or if it doesn't exist yet."""
    try:
        proc = subprocess.run(
            [_GCLOUD, "storage", "cat", _LOCKS_URI, "--project", _GCS_PROJECT],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {}
        return json.loads(proc.stdout)
    except Exception:  # noqa: BLE001
        return {}


def _write_locks_raw(data: dict[str, Any]) -> bool:
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f, indent=2)
            tmp_path = f.name
        proc = subprocess.run(
            [_GCLOUD, "storage", "cp", tmp_path, _LOCKS_URI, "--project", _GCS_PROJECT],
            capture_output=True, text=True, timeout=30,
        )
        Path(tmp_path).unlink(missing_ok=True)
        if proc.returncode != 0:
            print(f"lock write failed: {proc.stderr[:300]!r}", file=sys.stderr)
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001
        print(f"lock write exception: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def load_locked_company_ids() -> set[int]:
    """Currently-active locked company IDs (expired locks are ignored).

    Fails open: any read/parse error returns an empty set rather than raising,
    so a GCS hiccup can never block the whole pipeline — only an ACTIVE,
    correctly-written lock does.
    """
    raw = _read_locks_raw()
    now = datetime.now(timezone.utc)
    out: set[int] = set()
    for key, entry in raw.items():
        try:
            cid = int(key)
            until = datetime.fromisoformat(str(entry.get("until", "")))
        except (TypeError, ValueError):
            continue
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until > now:
            out.add(cid)
    return out


def lock_company(company_id: int, *, reason: str, hours: float = 24, locked_by: str = "") -> None:
    raw = _read_locks_raw()
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    raw[str(company_id)] = {
        "reason": reason,
        "locked_by": locked_by,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "until": until.isoformat(),
    }
    if not _write_locks_raw(raw):
        raise RuntimeError(f"failed to write {_LOCKS_URI}")


def unlock_company(company_id: int) -> bool:
    raw = _read_locks_raw()
    if str(company_id) not in raw:
        return False
    del raw[str(company_id)]
    if not _write_locks_raw(raw):
        raise RuntimeError(f"failed to write {_LOCKS_URI}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lock", type=int, metavar="COMPANY_ID")
    ap.add_argument("--unlock", type=int, metavar="COMPANY_ID")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--reason", default="manual work in progress")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--by", default="")
    args = ap.parse_args()

    if args.lock:
        lock_company(args.lock, reason=args.reason, hours=args.hours, locked_by=args.by)
        print(f"locked company {args.lock} for {args.hours}h: {args.reason!r}")
        return 0
    if args.unlock:
        removed = unlock_company(args.unlock)
        print(f"{'unlocked' if removed else 'no lock found for'} company {args.unlock}")
        return 0
    if args.list or True:
        raw = _read_locks_raw()
        active = load_locked_company_ids()
        if not raw:
            print("no locks on file")
            return 0
        for key, entry in raw.items():
            cid = int(key)
            status = "ACTIVE" if cid in active else "expired"
            print(f"  [{status:8}] company {cid}: {entry.get('reason','')!r} "
                  f"by={entry.get('locked_by','')!r} until={entry.get('until','')}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
