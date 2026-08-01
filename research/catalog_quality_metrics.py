"""Read-only catalog quality & completeness metrics.

Produces the numbers needed for a management-facing quality report:
status mix, field-level completeness, AI-verification score distribution,
quality-flag incidence, rejection reasons, and publish velocity.

READ-ONLY BY DESIGN. This deliberately does NOT call the server's
`audit_content_quality` management command, even though that command is the
"official" flag computer, because:

  1. It WRITES (`bulk_update` of quality_flags/quality_checked_at) across
     every robot it touches — a whole-catalog mutation just to produce a
     report is the wrong trade.
  2. There is a known false-positive in it ("No video" wrongly stamped)
     whose fix is written but NOT deployed. Running it today would stamp
     that false flag catalog-wide.

So completeness here is computed DIRECTLY from field values returned by the
API, which is ground truth as of right now and needs no recompute. Stored
`quality_flags` are reported separately, alongside their staleness, rather
than trusted as the completeness source.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402

OUT = _HERE / "staging" / "reports" / "catalog-quality-metrics.json"

# Verification bands, per robots/quality.py:468-475 (calibrated 2026-07-13).
VERIFIED_THRESHOLD = 70
LIKELY_WRONG_THRESHOLD = 40

# Spec fields that count as "has specs" — any one present is enough, since
# which specs are meaningful varies by robot type (an arm has reach, a
# drone has flight time).
SPEC_FIELDS = [
    "payload_kg", "reach_mm", "repeatability_mm", "weight_kg", "height_mm",
    "width_mm", "length_mm", "speed", "speed_ms", "dof", "battery_wh",
    "runtime_minutes", "voltage", "ip_rating",
]


def has(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def fetch_all(client: ResearchApiClient, page_size: int = 50) -> list[dict[str, Any]]:
    """Page through every robot. Small pages + retries: prod intermittently
    500s on large serialized pages (same reason list_robots_for_company uses 50)."""
    import time
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        for attempt in range(4):
            try:
                data = client._get("robots/robots/", params={"page": page, "page_size": page_size})
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        batch = data.get("results", [])
        out.extend(batch)
        if page % 10 == 0:
            print(f"  fetched {len(out)} ...", flush=True)
        if not data.get("next"):
            break
        page += 1
    return out


def main() -> None:
    client = ResearchApiClient()
    print("Fetching all robots (read-only) ...", flush=True)
    robots = fetch_all(client)
    total = len(robots)
    print(f"fetched {total} robots", flush=True)

    status_mix = Counter(r.get("status") or "unknown" for r in robots)

    # Completeness is reported for the PUBLISHED set and the PENDING set
    # separately — a published robot with no image is a live quality defect,
    # a pending one is just unfinished work. Mixing them hides both.
    groups = {
        "published": [r for r in robots if r.get("status") == "published"],
        "pending_review": [r for r in robots if r.get("status") == "pending_review"],
        "all": robots,
    }

    def completeness(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        if not n:
            return {}
        def pct(k: int) -> float:
            return round(100.0 * k / n, 1)
        img = sum(1 for r in rows if has(r.get("image")) or has(r.get("image_url")) or has(r.get("photos")))
        desc = sum(1 for r in rows if has(r.get("description")))
        desc_rich = sum(1 for r in rows if len((r.get("description") or "")) >= 200)
        specs = sum(1 for r in rows if any(has(r.get(f)) for f in SPEC_FIELDS))
        cat = sum(1 for r in rows if has(r.get("categories")))
        tags = sum(1 for r in rows if has(r.get("tags")) or has(r.get("tags_m2m")))
        vids = sum(1 for r in rows if has(r.get("videos")) or has(r.get("video_urls")) or has(r.get("linked_videos")))
        url = sum(1 for r in rows if has(r.get("url")))
        country = sum(1 for r in rows if has(r.get("manufacturer_country")) or has(r.get("manufacturer_country_code")))
        feats = sum(1 for r in rows if has(r.get("features")))
        year = sum(1 for r in rows if has(r.get("release_year")))
        return {
            "count": n,
            "image": pct(img), "description": pct(desc),
            "description_200ch_plus": pct(desc_rich),
            "specs_any": pct(specs), "category": pct(cat), "tags": pct(tags),
            "video": pct(vids), "source_url": pct(url), "country": pct(country),
            "features": pct(feats), "release_year": pct(year),
        }

    comp = {k: completeness(v) for k, v in groups.items()}

    # ---- AI verification bands -------------------------------------------
    def bands(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        scored = [r for r in rows if r.get("verification_confidence") is not None]
        never = n - len(scored)
        verified = sum(1 for r in scored if r["verification_confidence"] >= VERIFIED_THRESHOLD)
        review = sum(1 for r in scored if LIKELY_WRONG_THRESHOLD <= r["verification_confidence"] < VERIFIED_THRESHOLD)
        wrong = sum(1 for r in scored if r["verification_confidence"] < LIKELY_WRONG_THRESHOLD)
        avg = round(sum(r["verification_confidence"] for r in scored) / len(scored), 1) if scored else None
        return {
            "total": n, "never_scored": never,
            "never_scored_pct": round(100.0 * never / n, 1) if n else 0,
            "scored": len(scored), "mean_score": avg,
            "verified_70plus": verified, "review_40_69": review, "likely_wrong_under40": wrong,
            "verified_pct_of_scored": round(100.0 * verified / len(scored), 1) if scored else None,
        }

    verif = {k: bands(v) for k, v in groups.items()}

    # ---- stored quality flags (reported WITH staleness, not trusted) ------
    flag_counts: Counter = Counter()
    flag_sev: dict[str, str] = {}
    never_audited = 0
    audited_dates: list[str] = []
    for r in robots:
        if not r.get("quality_checked_at"):
            never_audited += 1
        else:
            audited_dates.append(r["quality_checked_at"][:10])
        for f in (r.get("quality_flags") or []):
            if isinstance(f, dict) and f.get("flag"):
                flag_counts[f["flag"]] += 1
                if f.get("severity"):
                    flag_sev[f["flag"]] = f["severity"]

    # ---- rejection reasons ------------------------------------------------
    rejected = [r for r in robots if r.get("status") == "rejected"]
    rej_cats: Counter = Counter()
    rej_uncategorized = 0
    for r in rejected:
        cats = r.get("rejection_categories") or []
        if not cats:
            rej_uncategorized += 1
        for c in cats:
            rej_cats[c] += 1

    # ---- velocity ---------------------------------------------------------
    def week(ts: str | None) -> str | None:
        if not ts:
            return None
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    pub_weeks = Counter(w for w in (week(r.get("published_at")) for r in robots) if w)
    created_weeks = Counter(w for w in (week(r.get("created_at")) for r in robots) if w)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_robots": total,
        "status_mix": dict(status_mix),
        "completeness_pct": comp,
        "ai_verification": verif,
        "quality_flags": {
            "never_audited": never_audited,
            "never_audited_pct": round(100.0 * never_audited / total, 1) if total else 0,
            "audit_dates_seen": dict(Counter(audited_dates).most_common(8)),
            "flag_incidence": {k: {"count": v, "severity": flag_sev.get(k, "?")}
                               for k, v in flag_counts.most_common()},
            "caveat": "Stored flags are only as fresh as each robot's quality_checked_at. "
                      "Robots never audited carry no flags — absence is NOT a pass. "
                      "Completeness above is computed from live field values instead.",
        },
        "rejections": {
            "total_rejected": len(rejected),
            "uncategorized": rej_uncategorized,
            "by_category": dict(rej_cats.most_common()),
        },
        "velocity": {
            "published_per_week_last12": dict(sorted(pub_weeks.items())[-12:]),
            "created_per_week_last12": dict(sorted(created_weeks.items())[-12:]),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT}")
    print(json.dumps(report, indent=2, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main()
