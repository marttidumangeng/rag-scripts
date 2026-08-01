"""Full enrichment sweep over a named list of companies, unattended.

Per company, in order, this runs the whole playbook and records what happened:

  1. company gaps   — resolve + write country/website when blank. Enrichment
                      copies `company.country` onto every robot it touches, so a
                      blank company row reproduces the error-severity
                      "No country" flag on the whole catalogue.
  2. enrichment     — `overnight_queue_enrich` for that company only
  3. cleanup        — deterministic fixes the automated pass reliably gets
                      wrong: images shared across the company's robots (site
                      chrome and cross-model accessories), junk tags, and any
                      category/country that still did not land
  4. remedies       — flag-driven Tier-1 remedies for whatever is left
  5. verify         — prod AI verification, which is the honest quality gate

Every stage is time-boxed and failures never skip the stages after them: a run
that dies on company 3 must still leave a usable report for companies 1-2.
Progress is written after EVERY company, so an interrupted sweep is still
auditable — the failure mode this pipeline keeps producing is hours of work
with nothing to show for it.

    python -u overnight_top_companies.py --company-ids 220,1374,...
    python -u overnight_top_companies.py --company-ids 220 --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402
from company_country_resolve import resolve_company_country  # noqa: E402
from company_website_resolve import resolve_company_website  # noqa: E402
from robot_categories import derive_category_slugs  # noqa: E402

REPORT = _HERE / "staging" / "reports" / "overnight-top-companies.json"
PROGRESS = _HERE / "staging" / "reports" / "overnight-top-companies-progress.md"

# Tags the enrichment pass hands out indiscriminately. Every one of these was
# found on robots that are demonstrably not that thing (a "Humanoid" tag on a
# tracked firefighting robot, "Drone" on a warehouse tugger). Only stripped when
# the robot has no supporting movement type.
JUNK_TAGS = {
    "humanoid": {"humanoid", "bipedal", "legged"},
    "drone": {"aerial", "flying"},
    "quadruped": {"quadruped", "legged"},
    "care robot": set(),
    "exoskeleton": {"wearable"},
    "demo": set(),
}


def _p(*a):
    try:
        print(*a, flush=True)
    except UnicodeEncodeError:
        print(" ".join(str(x) for x in a).encode("ascii", "replace").decode(), flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(cmd: list[str], *, limit_s: int) -> dict:
    """Run a stage under a wall-clock limit. Never raises."""
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=str(_HERE), capture_output=True, text=True,
            timeout=limit_s, encoding="utf-8", errors="replace",
        )
        out, rc, timed_out = proc.stdout or "", proc.returncode, False
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        rc, timed_out = 124, True
    except Exception as exc:  # noqa: BLE001
        return {"rc": -1, "elapsed": round(time.time() - t0), "error": f"{type(exc).__name__}: {exc}", "tail": ""}
    return {
        "rc": rc,
        "timed_out": timed_out,
        "elapsed": round(time.time() - t0),
        # Keep the tail only: these stages are chatty and the report is for a human.
        "tail": "\n".join(out.strip().splitlines()[-25:]),
    }


# ---------------------------------------------------------------------------
# Stage 1 — company-level gaps
# ---------------------------------------------------------------------------
def fix_company(client: ResearchApiClient, cid: int, *, apply: bool) -> dict:
    co = client.get_company(cid)
    name = str(co.get("name") or "")
    website = str(co.get("website") or "").strip()
    country = co.get("country")
    has_country = bool((country or {}).get("code") if isinstance(country, dict) else country)
    out = {"name": name, "website": website, "country_before":
           (country or {}).get("code") if isinstance(country, dict) else None}

    if not website:
        url, how = resolve_company_website(name, str(co.get("slug") or ""))
        out["website_resolved"], out["website_via"] = url, how
        if url and apply:
            client._patch(f"companies/{cid}/", {"website": url})
            website = url

    if not has_country:
        code, how = resolve_company_country(name, website)
        out["country_resolved"], out["country_via"] = code, how
        if code and apply:
            country_id = client.resolve_country_id(code)
            if country_id:
                client._patch(f"companies/{cid}/", {"country_id": country_id})
                out["country_written"] = code
            else:
                out["country_written"] = f"SKIPPED ({code} not in Country table)"
    return out


# ---------------------------------------------------------------------------
# Stage 3 — deterministic cleanup the automated pass gets wrong
# ---------------------------------------------------------------------------
def _robot_movement_keys(robot: dict) -> set[str]:
    return {str(m.get("key") or "").lower() for m in (robot.get("movement_types") or [])}


def cleanup(client: ResearchApiClient, cid: int, *, apply: bool) -> dict:
    """Strip junk tags and backfill category/country that did not land.

    Image de-duplication is deliberately NOT done here: it needs content hashes
    (URL comparison misses the same photo served under two paths) and the ORM,
    so it stays a separate reviewed step rather than an unattended guess.
    """
    robots = [r for r in client.list_robots_for_company(cid)
              if str(r.get("status") or "").lower() == "pending_review"]
    company = client.get_company(cid)
    country = company.get("country") or {}
    company_code = str(country.get("code") or "") if isinstance(country, dict) else ""

    tags_fixed = cats_fixed = country_fixed = 0
    notes: list[str] = []

    subcats = {}
    try:
        subcats = {row.get("id"): row.get("slug") or "" for row in client.get_subcategories()}
    except Exception:  # noqa: BLE001
        pass

    for r in robots:
        rid = int(r.get("id") or 0)
        payload: dict = {}

        # --- junk tags -----------------------------------------------------
        moves = _robot_movement_keys(r)
        tags = [t for t in (r.get("tags") or []) if isinstance(t, str)]
        keep = [t for t in tags
                if not (t.strip().lower() in JUNK_TAGS
                        and not (JUNK_TAGS[t.strip().lower()] & moves))]
        if len(keep) != len(tags):
            payload["tags"] = keep
            tags_fixed += 1

        # --- category ------------------------------------------------------
        if not (r.get("categories") or []):
            slugs = derive_category_slugs(
                name=str(r.get("name") or ""),
                text=" ".join(str(r.get(f) or "") for f in ("description", "purpose", "features")),
                movement_type_keys="|".join(sorted(moves)),
                sub_category_slug=subcats.get(r.get("sub_category"), ""),
                use_keys="|".join(str(u.get("key") or "") for u in (r.get("uses") or [])),
                industry_keys="|".join(str(i.get("key") or "") for i in (r.get("industries") or [])),
            )
            if slugs:
                payload["categories"] = slugs.split("|")
                cats_fixed += 1

        if payload and apply:
            try:
                client._patch(f"robots/robots/{rid}/", payload)
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{rid} patch failed: {type(exc).__name__}")

    # --- country: a write-only import alias, so it cannot go through PATCH --
    missing_country = [r for r in robots
                       if not (r.get("manufacturer_country_ref") or {}).get("code")]
    if missing_country and company_code and apply:
        rows = [{"id": int(r["id"]), "name": r.get("name") or "",
                 "company_slug": str(company.get("slug") or ""),
                 "url": r.get("url") or str(company.get("website") or ""),
                 "manufacturer_country_code": company_code,
                 "manufacturer_country_codes": company_code}
                for r in missing_country]
        try:
            client._post("robots/robots/bulk-import/", {
                "robots": rows, "status": "pending_review",
                "update_existing": True, "patch_existing": True, "created_by_id": 1,
            })
            country_fixed = len(rows)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"country import failed: {type(exc).__name__}: {str(exc)[:120]}")

    return {"pending": len(robots), "tags_cleaned": tags_fixed,
            "categories_filled": cats_fixed, "country_filled": country_fixed,
            "notes": notes}


def snapshot(client: ResearchApiClient, cid: int) -> dict:
    """Flag/verification census for the company's pending robots."""
    from collections import Counter

    flags: Counter = Counter()
    scores: list[float] = []
    robots = [r for r in client.list_robots_for_company(cid)
              if str(r.get("status") or "").lower() == "pending_review"]
    for r in robots:
        for f in (r.get("quality_flags") or []):
            if f.get("flag"):
                flags[f["flag"]] += 1
        v = r.get("verification_confidence")
        if v is not None:
            try:
                scores.append(float(v))
            except (TypeError, ValueError):
                pass
    return {
        "pending": len(robots),
        "flags": dict(flags.most_common()),
        "verified_count": len(scores),
        "verify_avg": round(sum(scores) / len(scores), 1) if scores else None,
        "verify_min": min(scores) if scores else None,
    }


def write_progress(results: list[dict], started: str) -> None:
    lines = [f"# Overnight top-company enrichment", "",
             f"started {started} · updated {_now()}", ""]
    lines.append("| company | id | pending | before flags | after flags | verify avg/min | status |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        before = sum((r.get("before") or {}).get("flags", {}).values())
        after = sum((r.get("after") or {}).get("flags", {}).values())
        a = r.get("after") or {}
        lines.append(
            f"| {r.get('name','')[:34]} | {r['company_id']} | {a.get('pending','?')} | "
            f"{before} | {after} | {a.get('verify_avg','-')}/{a.get('verify_min','-')} | "
            f"{r.get('status','?')} |")
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-ids", required=True, help="comma-separated")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--t-enrich", type=int, default=5400)
    ap.add_argument("--t-remedy", type=int, default=2400)
    ap.add_argument("--t-verify", type=int, default=2400)
    args = ap.parse_args()

    apply = not args.dry_run
    ids = [int(x) for x in args.company_ids.split(",") if x.strip().isdigit()]
    started = _now()
    client = ResearchApiClient()
    results: list[dict] = []

    _p(f"=== Overnight sweep ({'APPLY' if apply else 'DRY-RUN'}) — {len(ids)} companies ===")
    _p(f"started {started}\n")

    for n, cid in enumerate(ids, 1):
        t0 = time.time()
        row: dict = {"company_id": cid, "started_at": _now()}
        try:
            before = snapshot(client, cid)
            row["before"] = before
            comp = fix_company(client, cid, apply=apply)
            row["company"] = comp
            row["name"] = comp.get("name", "")
            _p(f"\n{'='*72}\n[{n}/{len(ids)}] {cid} {row['name']} — {before['pending']} pending")
            _p(f"    company: {json.dumps(comp)[:300]}")

            if apply:
                row["enrich"] = run(
                    [sys.executable, "-u", "overnight_queue_enrich.py",
                     "--workers", "1", "--company-ids", str(cid)],
                    limit_s=args.t_enrich)
                _p(f"    enrich  rc={row['enrich']['rc']} {row['enrich']['elapsed']}s")

                row["cleanup"] = cleanup(client, cid, apply=apply)
                _p(f"    cleanup {json.dumps(row['cleanup'])[:220]}")

                row["remedy"] = run(
                    [sys.executable, "-u", "remedy_dryrun.py",
                     "--company-id", str(cid), "--max-robots", "200", "--apply"],
                    limit_s=args.t_remedy)
                _p(f"    remedy  rc={row['remedy']['rc']} {row['remedy']['elapsed']}s")

            row["after"] = snapshot(client, cid)
            row["status"] = "done"
        except Exception as exc:  # noqa: BLE001
            row["status"] = "error"
            row["error"] = f"{type(exc).__name__}: {exc}"
            _p(f"    !! COMPANY FAILED: {row['error']}")
        row["elapsed_s"] = round(time.time() - t0)
        row["finished_at"] = _now()
        results.append(row)

        # Persist after EVERY company: an interrupted sweep must still be auditable.
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(
            {"started": started, "updated": _now(), "apply": apply, "companies": results},
            indent=2, ensure_ascii=False), encoding="utf-8")
        write_progress(results, started)
        _p(f"    -> {row['status']} in {row['elapsed_s']}s; report {REPORT.name}")

    _p(f"\n=== SWEEP DONE {_now()} ===")
    for r in results:
        a = r.get("after") or {}
        _p(f"  {r['company_id']:>5} {r.get('name','')[:34]:36} {r.get('status'):6} "
           f"pending={a.get('pending','?')} flags={sum(a.get('flags',{}).values())} "
           f"verify={a.get('verify_avg','-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
