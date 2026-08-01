"""Display-readiness census: how many robots would actually LOOK acceptable
on a browse card, as distinct from how complete their data is.

Why this is a different question from catalog_quality_metrics.py:
RobotCard.vue renders only image, family eyebrow, name, company, ONE category
pill, ONE tag pill, "Made in" country, and `purpose` (2-line clamp). It does
NOT render `description`, and its spec-chip computed (`cardDetails`) is dead
code that no template references. So specs/description completeness — the
scariest numbers in the data-quality report — have zero effect on card
appearance. This measures the bar that actually governs the UI.

Hero resolution mirrors the component exactly (RobotCard.vue:426-439):
    pickBestVariant(image_variants) -> s3_image -> placeholder
Note it never consults the legacy `image` CharField, which is precisely why
the API's `no_image` filter (filters.py, checks `image` only) is NOT a
reliable "has a renderable hero" gate.

Read-only. Uses lite=1 (RobotLiteListSerializer) — every field needed is in
that list, and it is far cheaper than the full serializer.
"""
from __future__ import annotations

import json
import sys
import time
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

OUT = _HERE / "staging" / "reports" / "display-readiness.json"


def nonempty(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict, tuple)):
        return len(v) > 0
    return True


def has_hero(r: dict[str, Any]) -> bool:
    """Exactly what RobotCard.vue can actually render as a hero."""
    if nonempty(r.get("image_variants")) or nonempty(r.get("image_variants_webp")):
        return True
    return nonempty(r.get("s3_image"))


def has_company(r: dict[str, Any]) -> bool:
    if nonempty(r.get("company")):
        return True
    ref = r.get("company_ref")
    return bool(ref and (ref.get("name") if isinstance(ref, dict) else ref))


def has_country(r: dict[str, Any]) -> bool:
    ref = r.get("manufacturer_country_ref")
    return bool(ref and (ref.get("name") if isinstance(ref, dict) else ref))


def tier(r: dict[str, Any]) -> str:
    """Card-quality tiers, strictly by what renders."""
    hero = has_hero(r)
    cat = nonempty(r.get("categories"))
    pur = nonempty(r.get("purpose"))
    co = has_company(r)
    if not hero:
        return "D_no_hero"
    if hero and co and cat and pur:
        return "A_display_ready"
    if hero and co and (cat or pur):
        return "B_acceptable"
    return "C_thin"


def fetch_all(client: ResearchApiClient, page_size: int = 100) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        for attempt in range(4):
            try:
                data = client._get(
                    "robots/robots/",
                    params={"page": page, "page_size": page_size, "lite": "1"},
                )
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        out.extend(data.get("results", []))
        if page % 10 == 0:
            print(f"  fetched {len(out)} ...", flush=True)
        if not data.get("next"):
            break
        page += 1
    return out


def main() -> None:
    client = ResearchApiClient()
    print("Fetching robots (lite, read-only) ...", flush=True)
    robots = fetch_all(client)
    print(f"fetched {len(robots)}", flush=True)

    groups = {
        "published": [r for r in robots if r.get("status") == "published"],
        "pending_review": [r for r in robots if r.get("status") == "pending_review"],
    }

    def census(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        if not n:
            return {}
        tiers = Counter(tier(r) for r in rows)
        def pc(k: int) -> float:
            return round(100.0 * k / n, 1)
        return {
            "count": n,
            "tiers": {k: {"n": v, "pct": pc(v)} for k, v in sorted(tiers.items())},
            "card_fields_pct": {
                "renderable_hero": pc(sum(1 for r in rows if has_hero(r))),
                "company":         pc(sum(1 for r in rows if has_company(r))),
                "category":        pc(sum(1 for r in rows if nonempty(r.get("categories")))),
                "purpose":         pc(sum(1 for r in rows if nonempty(r.get("purpose")))),
                "tag":             pc(sum(1 for r in rows if nonempty(r.get("tags")))),
                "country":         pc(sum(1 for r in rows if has_country(r))),
                "family_eyebrow":  pc(sum(1 for r in rows if nonempty(r.get("family_name")))),
            },
            # Legacy `image` vs what the card really uses — quantifies how wrong
            # the existing no_image filter is as a display gate.
            "legacy_image_field_pct": pc(sum(1 for r in rows if nonempty(r.get("image")))),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tier_definitions": {
            "A_display_ready": "hero + company + category + purpose",
            "B_acceptable":    "hero + company + (category OR purpose)",
            "C_thin":          "hero but no category AND no purpose",
            "D_no_hero":       "no renderable image (card falls back to placeholder)",
        },
        "groups": {k: census(v) for k, v in groups.items()},
        "heat_score": {
            "nonzero": sum(1 for r in robots if (r.get("heat_score") or 0) != 0),
            "total": len(robots),
            "note": "heat_score is sortable and already offered in the browse sort "
                    "dropdown, but is never computed server-side. If it is ~all zero "
                    "it is a free, already-wired slot for a completeness rank.",
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
