"""Overnight content-queue enrich: oldest pending → newest, gap-fill only.

Rules:
- Walk pending_review robots ordered by created_at ASC (oldest first).
- Group by company in that order.
- Research + import only robots that still have gaps.
- Merge/patch only blank fields — never force-overwrite good data.
- Never enable Gemini (grounded=False, no verify_content / verify_staging).
- Prefer companies with a website; soft-skip marketplace shells without one.
- Leave status pending_review; copy-media when a new image was filled.

Usage:
  python -u overnight_queue_enrich.py
  python -u overnight_queue_enrich.py --max-companies 20
  python -u overnight_queue_enrich.py --max-robots-per-company 40
  python -u overnight_queue_enrich.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import RobotAutoResearcher, _merge_staged
from schema import StagedRobot, VideoRef
from slug_utils import resolve_company_slug
from triage_content_queue import (
    _load_done,
    _save_done,
    robot_gaps,
)
from validate_staging import validate_robot

PROGRESS_PATH = _RESEARCH_DIR / "staging" / "reports" / "overnight-queue-progress.json"
# Robots whose last research pass changed NOTHING. Without this the queue is a
# treadmill: gap-fill only ever picks the oldest gapped companies, so a robot whose
# gaps cannot be filled (no video exists, no findable image) keeps them forever and
# its company stays at the head of the queue. Measured on the first continuous run —
# cycles 1-3 re-researched the SAME 8 companies (DJI remaining_gapped 22→22→22),
# ~60 robots re-imported three times for no change. Same idea as the remedy
# library's NO_OP ledger, applied to the enrichment pass.
STALL_PATH = _RESEARCH_DIR / "staging" / "state" / "enrich_stalled.json"
STALL_COOLDOWN_HOURS = float(os.environ.get("ENRICH_STALL_COOLDOWN_HOURS", "168"))  # 7 days


def _load_stalled() -> dict[str, Any]:
    if STALL_PATH.exists():
        try:
            return json.loads(STALL_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_stalled(data: dict[str, Any]) -> None:
    STALL_PATH.parent.mkdir(parents=True, exist_ok=True)
    STALL_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _is_stalled(stalled: dict[str, Any], robot_id: int) -> bool:
    entry = stalled.get(str(robot_id))
    if not entry:
        return False
    try:
        at = datetime.fromisoformat(str(entry.get("at")).replace("Z", "+00:00"))
    except Exception:
        return False
    age_h = (datetime.now(timezone.utc) - at).total_seconds() / 3600.0
    return age_h < STALL_COOLDOWN_HOURS


SUMMARY_PATH = _RESEARCH_DIR / "staging" / "reports" / "overnight-queue-summary.json"

# Guards for shared writes when --workers > 1 (companies run concurrently):
# the progress checkpoint file and the shared triage done.json (read-modify-write).
_PROGRESS_LOCK = threading.Lock()
_DONE_LOCK = threading.Lock()
# The stall ledger is a read-modify-write file, same as done.json, so concurrent
# companies (--workers > 1) must not interleave on it.
_STALL_LOCK = threading.Lock()


def _safe_print(*args: Any, **kwargs: Any) -> None:
    """Avoid Windows cp1252 crashes on CJK/symbol robot names."""
    kwargs.setdefault("flush", True)
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"), **kwargs)


# Prefer UTF-8 stdout when the console supports reconfigure (Python 3.7+).
try:
    sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_progress(payload: dict[str, Any]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = _now()
    PROGRESS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def iter_pending_oldest_first(
    client: ResearchApiClient,
    *,
    page_size: int = 50,
) -> list[dict[str, Any]]:
    """Fetch all pending_review robots, then sort oldest → newest locally."""
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        last_exc: Exception | None = None
        data = None
        for attempt in range(5):
            try:
                data = client._get(
                    "robots/robots/",
                    params={
                        "status": "pending_review",
                        "page": page,
                        "page_size": page_size,
                    },
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = 2 ** attempt
                _safe_print(f"  scan retry page={page} attempt={attempt+1}: {exc} (sleep {wait}s)", flush=True)
                time.sleep(wait)
        if data is None:
            raise last_exc  # type: ignore[misc]
        batch = data.get("results") or []
        results.extend(batch)
        _safe_print(
            f"  scan page {page}: +{len(batch)} "
            f"(total {len(results)}/{data.get('count')})",
            flush=True,
        )
        if not data.get("next") or not batch:
            break
        page += 1
        time.sleep(0.15)
    results.sort(key=lambda r: (r.get("created_at") or "", r.get("id") or 0))
    return results


def company_id_of(robot: dict[str, Any]) -> int | None:
    cref = robot.get("company_ref")
    if isinstance(cref, dict) and cref.get("id"):
        return int(cref["id"])
    if robot.get("company_id"):
        return int(robot["company_id"])
    return None


def company_meta(robot: dict[str, Any]) -> dict[str, Any]:
    cref = robot.get("company_ref") if isinstance(robot.get("company_ref"), dict) else {}
    return {
        "id": company_id_of(robot),
        "name": (cref.get("name") if cref else None) or robot.get("company") or "Unknown",
        "slug": (cref.get("slug") if cref else None) or "",
        "website": ((cref.get("website") if cref else None) or "").strip(),
    }


def build_company_queue(robots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Companies ordered by their oldest gapped pending robot.

    Stalled robots are excluded from SELECTION, not just from processing. Filtering
    them only inside enrich_company (cycle-2 finding, 2026-07-28) left the same 8
    exhausted companies occupying every slot of the --max-companies budget with
    targets=0 — waste went away but throughput went to ~zero, because selection
    still counted their unfillable gaps. A company whose gapped robots are all
    stalled must drop out of the queue so the budget reaches fresh companies.
    """
    stalled = _load_stalled()
    buckets: "OrderedDict[int, dict[str, Any]]" = OrderedDict()
    for robot in robots:
        if _is_stalled(stalled, int(robot.get("id") or 0)):
            continue
        gaps = robot_gaps(robot)
        if not gaps:
            continue
        cid = company_id_of(robot)
        if not cid:
            continue
        meta = company_meta(robot)
        if cid not in buckets:
            buckets[cid] = {
                "company_id": cid,
                "name": meta["name"],
                "slug": meta["slug"],
                "website": meta["website"],
                "oldest_robot_id": robot.get("id"),
                "oldest_created_at": robot.get("created_at"),
                "robots": [],
            }
        buckets[cid]["robots"].append(
            {
                "id": robot.get("id"),
                "name": robot.get("name"),
                "gaps": gaps,
                "created_at": robot.get("created_at"),
            }
        )
    return list(buckets.values())


def _tag_string(robot: dict[str, Any]) -> str:
    tags = robot.get("tags") or robot.get("tag_names") or []
    if isinstance(tags, list):
        names = []
        for t in tags:
            if isinstance(t, dict):
                names.append(str(t.get("name") or t.get("label") or "").strip())
            else:
                names.append(str(t).strip())
        return "|".join(n for n in names if n)
    return str(tags).strip()


def _video_refs(robot: dict[str, Any]) -> list[VideoRef]:
    vids = robot.get("videos") or robot.get("video_urls") or []
    out: list[VideoRef] = []
    if not isinstance(vids, list):
        return out
    for v in vids:
        if isinstance(v, str) and v.strip():
            out.append(VideoRef(url=v.strip()))
        elif isinstance(v, dict) and v.get("url"):
            out.append(
                VideoRef(
                    url=str(v["url"]),
                    title=str(v.get("title") or ""),
                    description=str(v.get("description") or ""),
                )
            )
    return out


def robot_api_to_base(robot: dict[str, Any], company_slug: str, company_name: str) -> StagedRobot:
    """Preserve existing DB fields so merge only fills blanks."""
    img = (robot.get("s3_image") or robot.get("image") or robot.get("image_url") or "").strip()
    video_payload: list[Any] = []
    for v in _video_refs(robot):
        video_payload.append(v.to_dict())
    return StagedRobot.from_dict(
        {
            "name": robot.get("name") or "",
            "model_name": robot.get("model_name") or robot.get("name") or "",
            "company_slug": company_slug,
            "company_name": company_name,
            "url": robot.get("url") or "",
            "image": img,
            "description": robot.get("description") or "",
            "purpose": robot.get("purpose") or "",
            "features": robot.get("features") or "",
            "notes": robot.get("notes") or "",
            "tags": _tag_string(robot),
            "video_urls": video_payload,
            "weight_kg": robot.get("weight_kg"),
            "weight": robot.get("weight") or "",
            "dof": robot.get("dof"),
            "dimensions_mm": robot.get("dimensions_mm") or "",
            "length_mm": robot.get("length_mm"),
            "width_mm": robot.get("width_mm"),
            "height_mm": robot.get("height_mm"),
            "payload_kg": robot.get("payload_kg"),
            "reach_mm": robot.get("reach_mm"),
            "sources": [{"url": robot.get("url"), "type": "website"}] if robot.get("url") else [],
        }
    )


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                _safe_print(f"    copy-media fail {rid}: HTTP {resp.status_code}", flush=True)
        except requests.RequestException as exc:
            fail += 1
            _safe_print(f"    copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.05)
    return ok, fail


def enrich_company(
    client: ResearchApiClient,
    company_id: int,
    *,
    max_robots: int | None,
    dry_run: bool,
) -> dict[str, Any]:
    company = client.get_company(company_id)
    company_name = str(company.get("name") or "")
    company_slug = resolve_company_slug(company_name, company.get("slug"))
    website = str(company.get("website") or "").strip()
    company_country_code = ""
    if company.get("country"):
        company_country_code = str(company["country"].get("code") or "")

    pending = [
        r
        for r in client.list_robots_for_company(company_id)
        if str(r.get("status") or "").lower() == "pending_review" and robot_gaps(r)
    ]
    # Drop robots whose last pass produced nothing — their gaps are not fillable from
    # the OEM site right now, and re-researching them is the treadmill this stall
    # ledger exists to break. They come back after STALL_COOLDOWN_HOURS in case the
    # vendor publishes more, or immediately if a human clears the ledger.
    stalled = _load_stalled()
    skipped_stalled = [r.get("id") for r in pending if _is_stalled(stalled, int(r.get("id") or 0))]
    if skipped_stalled:
        pending = [r for r in pending if int(r.get("id") or 0) not in set(skipped_stalled)]
        _safe_print(f"  skipping {len(skipped_stalled)} stalled robot(s) (no progress last pass)")
    # Oldest first within company
    pending.sort(key=lambda r: (r.get("created_at") or "", r.get("id") or 0))
    if max_robots is not None:
        pending = pending[:max_robots]

    result: dict[str, Any] = {
        "company_id": company_id,
        "company_name": company_name,
        "company_slug": company_slug,
        "website": website,
        "targets": len(pending),
        "researched": 0,
        "imported": 0,
        "copy_media_ok": 0,
        "copy_media_fail": 0,
        "skipped": [],
        "errors": [],
        "robots": [],
    }

    if not pending:
        result["note"] = "no gapped pending_review robots"
        return result

    if not website:
        result["note"] = "no company website — soft skip (auto enrich needs OEM site)"
        result["skipped"] = [r.get("id") for r in pending]
        return result

    researcher = RobotAutoResearcher(grounded=False)  # never Gemini
    from evidence_store import EvidenceStore, sweep_company_evidence

    evidence = EvidenceStore(company_slug, pipeline="enrich")
    _safe_print(f"  Evidence: {evidence.relative_root}", flush=True)
    staging_dir = _RESEARCH_DIR / "staging" / "robots" / company_slug / "overnight"
    staging_dir.mkdir(parents=True, exist_ok=True)
    created_by = resolve_created_by_id(1)
    imported_ids: list[int] = []
    needs_copy: list[int] = []

    for idx, robot in enumerate(pending, 1):
        rid = int(robot["id"])
        name = robot.get("name") or f"id={rid}"
        had_image = bool(robot.get("s3_image") or robot.get("image"))
        gaps_before = robot_gaps(robot)
        _safe_print(f"  [{idx}/{len(pending)}] {rid} {name} gaps={gaps_before}", flush=True)
        try:
            researched = researcher.research_robot(
                robot,
                company_slug=company_slug,
                company_name=company_name,
                company_website=website,
                manufacturer_country_code=company_country_code,
                trust_stored_url=True,
                evidence=evidence,
            )
            if researched is None:
                _safe_print(f"    skip target_not_found: {name}", flush=True)
                result["errors"].append({"id": rid, "error": "target_not_found"})
                result["robots"].append(
                    {
                        "id": rid,
                        "name": name,
                        "gaps_before": gaps_before,
                        "skipped": "target_not_found",
                    }
                )
                continue
            base = robot_api_to_base(robot, company_slug, company_name)
            # Gap-fill only — never overwrite populated fields
            merged = _merge_staged(base, researched, force_fields=frozenset())
            # Promote existing description/purpose into features when features still blank
            # (does not invent — only copies already-stored OEM text).
            if len((merged.features or "").strip()) < 40:
                for candidate in (merged.description, merged.purpose, merged.research_notes):
                    text = (candidate or "").strip()
                    if len(text) >= 40:
                        payload = merged.to_dict()
                        payload["features"] = text[:1800]
                        merged = StagedRobot.from_dict(payload)
                        break
            validation = validate_robot(merged)
            path = staging_dir / f"robot_{rid}.json"
            path.write_text(
                json.dumps([merged.to_dict()], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            result["researched"] += 1
            row_info = {
                "id": rid,
                "name": name,
                "gaps_before": gaps_before,
                "image": bool(merged.image),
                "features_len": len(merged.features or ""),
                "videos": len(merged.video_urls or []),
                "validation_ok": validation.ok,
                "staging": str(path.relative_to(_RESEARCH_DIR)).replace("\\", "/"),
            }
            if dry_run:
                row_info["dry_run"] = True
                result["robots"].append(row_info)
                continue

            imp = import_staging(
                path,
                client=client,
                patch=True,
                force_overwrite=False,
                replace_media=False,
                status="pending_review",
                batch_size=1,
                skip_company_update=True,
                dry_run=False,
                created_by_id=created_by,
            )
            if not imp.get("ok"):
                result["errors"].append({"id": rid, "import": imp})
                row_info["import_ok"] = False
            else:
                result["imported"] += 1
                imported_ids.append(rid)
                row_info["import_ok"] = True
                if merged.image and not had_image:
                    needs_copy.append(rid)

                # Did the gap ACTUALLY close? Re-read the robot rather than trusting
                # the staged diff. The two disagree exactly when a write does not
                # persist — which is this pipeline's signature failure and the reason
                # DJI showed 21 imported with remaining_gapped 22 -> 22 -> 22 across
                # three cycles. Measuring "the merge produced a different value"
                # instead of "the gap closed" is what made the first version of this
                # ledger record nothing at all.
                try:
                    fresh = client._get(f"robots/robots/{rid}/")
                    gaps_after = robot_gaps(fresh) if isinstance(fresh, dict) else gaps_before
                except Exception:
                    gaps_after = gaps_before  # unknown -> do not penalise the robot
                row_info["gaps_after"] = gaps_after
                closed = set(gaps_before) - set(gaps_after)
                with _STALL_LOCK:
                    stalled_now = _load_stalled()
                    if closed:
                        stalled_now.pop(str(rid), None)
                    else:
                        stalled_now[str(rid)] = {
                            "at": _now(), "company_id": company_id, "gaps": gaps_after,
                        }
                    _save_stalled(stalled_now)
                if closed:
                    _safe_print(f"         gaps closed: {sorted(closed)}")
                else:
                    _safe_print(
                        f"         gaps unchanged {gaps_after} -> stalled "
                        f"({STALL_COOLDOWN_HOURS:.0f}h cooldown)"
                    )
            result["robots"].append(row_info)
            _safe_print(
                f"         img={bool(merged.image)} feat={len(merged.features or '')} "
                f"vids={len(merged.video_urls or [])} import={row_info.get('import_ok')}",
                flush=True,
            )
        except Exception as exc:
            err = f"{rid} {name}: {exc}"
            _safe_print(f"         ERROR: {exc}", flush=True)
            result["errors"].append({"id": rid, "error": str(exc), "trace": traceback.format_exc()[-800:]})
        time.sleep(0.2)

    if needs_copy and not dry_run:
        ok, fail = trigger_copy_media(needs_copy)
        result["copy_media_ok"] = ok
        result["copy_media_fail"] = fail
        _safe_print(f"  copy-media ok={ok} fail={fail}", flush=True)

    # Remaining gaps among pending (avoid huge full-company list when possible)
    remaining = 0
    try:
        for r in client.list_robots_for_company(company_id):
            if str(r.get("status") or "").lower() != "pending_review":
                continue
            if robot_gaps(r):
                remaining += 1
                if remaining > 50:
                    # Cap counting cost for mega-OEMs; still not "done"
                    break
    except Exception as exc:  # noqa: BLE001
        result["errors"].append({"remaining_check": str(exc)})
        remaining = -1
    result["remaining_gapped"] = remaining
    if remaining == 0 and not dry_run:
        # Serialize the read-modify-write so concurrent companies don't clobber done.json.
        with _DONE_LOCK:
            done = _load_done()
            ids = set(done.get("companies") or [])
            ids.add(company_id)
            done["companies"] = sorted(ids)
            notes = done.get("notes") or {}
            notes[str(company_id)] = {
                "marked_at": _now(),
                "via": "overnight_queue_enrich",
                "imported": result["imported"],
            }
            done["notes"] = notes
            _save_done(done)
        result["marked_done"] = True

    evidence.finish(
        company_id=company_id,
        researched=result["researched"],
        imported=result["imported"],
        targets=result["targets"],
        website=website,
    )
    sweep = sweep_company_evidence(company_slug)
    result["evidence_dir"] = evidence.relative_root
    result["evidence_run_id"] = evidence.run_id
    result["evidence_sweep"] = sweep
    _safe_print(
        f"  Evidence saved → {evidence.relative_root} (sweep deleted={sweep.get('deleted')})",
        flush=True,
    )
    return result


def _process_company(
    entry: dict[str, Any],
    *,
    max_robots: int | None,
    dry_run: bool,
) -> tuple[str, dict[str, Any]]:
    """Enrich one company end-to-end with its OWN API client.

    Fully isolated per call (own requests.Session; enrich_company creates its own
    researcher + evidence store), so it is safe to run concurrently across companies.
    Returns (kind, payload) with kind in {"completed", "failed"}.
    """
    cid = int(entry["company_id"])
    website = entry.get("website") or ""
    _safe_print(
        f"\n## Company {cid} {entry['name']} "
        f"({len(entry['robots'])} gapped) site={website or '(none)'} "
        f"oldest={entry.get('oldest_robot_id')}",
        flush=True,
    )
    try:
        summary = enrich_company(
            ResearchApiClient(),
            cid,
            max_robots=max_robots,
            dry_run=dry_run,
        )
        return ("completed", summary)
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"COMPANY FAIL {cid}: {exc}", flush=True)
        traceback.print_exc()
        return ("failed", {"company_id": cid, "name": entry["name"], "error": str(exc)})


def _record(progress: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    """Thread-safe append to progress + checkpoint to disk."""
    with _PROGRESS_LOCK:
        if kind == "completed":
            progress["completed"].append(payload)
        elif kind == "failed":
            progress["failed"].append(payload)
        _save_progress(progress)


def main() -> int:
    parser = argparse.ArgumentParser(description="Overnight oldest→newest gap-only enrich")
    parser.add_argument("--max-companies", type=int, default=0, help="0 = no limit")
    parser.add_argument("--max-robots-per-company", type=int, default=0, help="0 = no limit")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--include-no-website",
        action="store_true",
        help="Attempt companies without website (usually fails)",
    )
    parser.add_argument("--start-after-company-id", type=int, default=0)
    parser.add_argument(
        "--company-ids",
        type=str,
        default="",
        help="Comma-separated company IDs — skip full pending scan; enrich only these (order preserved)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Companies to enrich in parallel (default 1 = original serial behavior). "
             "Each worker is fully isolated; keep modest (e.g. 4–6) to avoid overloading "
             "prod. Forced to 1 if RESEARCH_USE_PLAYWRIGHT is set (not thread-safe).",
    )
    args = parser.parse_args()

    _safe_print("=== Overnight queue enrich (gap-only, no Gemini) ===", flush=True)
    _safe_print(f"started {_now()}", flush=True)
    client = ResearchApiClient()

    company_ids: list[int] = []
    if args.company_ids.strip():
        company_ids = [
            int(x.strip())
            for x in args.company_ids.split(",")
            if x.strip().isdigit()
        ]

    if company_ids:
        _safe_print(f"Targeted company-ids mode: {company_ids}", flush=True)
        queue = []
        for cid in company_ids:
            try:
                co = client.get_company(cid)
            except Exception as exc:  # noqa: BLE001
                _safe_print(f"  skip {cid}: company fetch failed: {exc}", flush=True)
                continue
            pending = [
                r
                for r in client.list_robots_for_company(cid)
                if str(r.get("status") or "").lower() == "pending_review" and robot_gaps(r)
            ]
            pending.sort(key=lambda r: (r.get("created_at") or "", r.get("id") or 0))
            queue.append(
                {
                    "company_id": cid,
                    "name": co.get("name") or f"company-{cid}",
                    "slug": co.get("slug") or "",
                    "website": (co.get("website") or "").strip(),
                    "oldest_robot_id": pending[0]["id"] if pending else None,
                    "oldest_created_at": pending[0].get("created_at") if pending else None,
                    "robots": [
                        {
                            "id": r.get("id"),
                            "name": r.get("name"),
                            "gaps": robot_gaps(r),
                            "created_at": r.get("created_at"),
                        }
                        for r in pending
                    ],
                }
            )
        _safe_print(f"Companies queued: {len(queue)}", flush=True)
    else:
        _safe_print("Scanning pending_review oldest→newest …", flush=True)
        robots = iter_pending_oldest_first(client)
        queue = build_company_queue(robots)
        _safe_print(f"Companies with gaps: {len(queue)}", flush=True)

    progress: dict[str, Any] = {
        "started_at": _now(),
        "mode": "gap_only_patch",
        "gemini": False,
        "company_ids_filter": company_ids or None,
        "total_companies_queued": len(queue),
        "completed": [],
        "skipped_no_website": [],
        "failed": [],
    }
    _save_progress(progress)

    max_co = args.max_companies or None
    max_robots = args.max_robots_per_company or None

    # Build the dispatch list up front (single-threaded): honor --start-after-company-id,
    # soft-skip no-website companies, then cap to --max-companies. Under parallel mode
    # --max-companies caps the companies *attempted* (those with a website).
    dispatch: list[dict[str, Any]] = []
    for entry in queue:
        cid = int(entry["company_id"])
        if args.start_after_company_id and cid <= args.start_after_company_id:
            continue
        website = entry.get("website") or ""
        if not website and not args.include_no_website:
            progress["skipped_no_website"].append(
                {"company_id": cid, "name": entry["name"], "gapped": len(entry["robots"])}
            )
            continue
        dispatch.append(entry)
        if max_co is not None and len(dispatch) >= max_co:
            break
    _save_progress(progress)

    workers = max(1, args.workers)
    # Playwright's sync API is not thread-safe — never fan out with it enabled.
    if workers > 1 and os.environ.get("RESEARCH_USE_PLAYWRIGHT", "").lower() in ("1", "true", "yes"):
        _safe_print(
            "  RESEARCH_USE_PLAYWRIGHT is set — forcing --workers 1 (playwright is not thread-safe)",
            flush=True,
        )
        workers = 1
    if workers > 8:
        _safe_print(
            f"  NOTE: --workers {workers} is high; keep it modest to avoid overloading prod.",
            flush=True,
        )
    _safe_print(f"Dispatching {len(dispatch)} companies with {workers} worker(s)…", flush=True)

    if workers == 1:
        for entry in dispatch:
            kind, payload = _process_company(entry, max_robots=max_robots, dry_run=args.dry_run)
            _record(progress, kind, payload)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_company, entry, max_robots=max_robots, dry_run=args.dry_run
                ): entry
                for entry in dispatch
            }
            for fut in as_completed(futures):
                kind, payload = fut.result()
                _record(progress, kind, payload)

    # Final rollup
    completed = progress["completed"]
    summary = {
        "finished_at": _now(),
        "started_at": progress["started_at"],
        "companies_attempted": len(completed),
        "companies_marked_done": sum(1 for c in completed if c.get("marked_done")),
        "robots_researched": sum(int(c.get("researched") or 0) for c in completed),
        "robots_imported": sum(int(c.get("imported") or 0) for c in completed),
        "copy_media_ok": sum(int(c.get("copy_media_ok") or 0) for c in completed),
        "skipped_no_website": progress["skipped_no_website"],
        "failed": progress["failed"],
        "completed": completed,
        "gemini_used": False,
        "overwrite_mode": "patch_only_fill_blanks",
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    progress["summary"] = {
        k: summary[k]
        for k in (
            "finished_at",
            "companies_attempted",
            "companies_marked_done",
            "robots_researched",
            "robots_imported",
            "copy_media_ok",
        )
    }
    _save_progress(progress)

    _safe_print("\n=== DONE ===", flush=True)
    _safe_print(json.dumps(progress["summary"], indent=2), flush=True)
    _safe_print(f"Full summary: {SUMMARY_PATH}", flush=True)
    # Nonzero when anything failed so schedulers don't treat a partial run as done.
    had_errors = bool(progress["failed"]) or any(c.get("errors") for c in completed)
    return 1 if had_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
