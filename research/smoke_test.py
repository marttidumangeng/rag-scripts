"""Pre-flight smoke test: is the research pipeline actually alive?

Read-only. Run before any unattended/VM run and gate on the exit code.

Every check here exists because something failed SILENTLY in a way that looked like
a clean negative result. The pipeline is full of fail-open paths — `_generate_json`
swallows every exception into None, `lookup_release_year` fail-opens without an API
key, a field missing from RobotSerializer.Meta.fields reads as absent rather than
erroring — so "0 robots fixed" is indistinguishable from "the whole grounded layer
is dead" unless something asserts liveness explicitly. That is this file's job.

The sharpest example: `max_output_tokens=1200` against a *thinking* model left ~130
tokens for the answer, so every grounded call returned None for weeks while
appearing to simply "find nothing". `grounded_json` below catches that in one call.

  python -u smoke_test.py            # all checks
  python -u smoke_test.py --quick    # skip the paid model calls
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

RESULTS: list[tuple[str, bool, str]] = []
# A page that is stable, public, and known to exercise the messy paths (CMS-named
# images, an option-list widget, a nav carrying other products).
PROBE_URL = "https://www.ubtrobot.com/en/ai-education/products/ukit-ai"


def check(name: str, *, skip: bool = False):
    """Decorator: run a check, record PASS/FAIL/SKIP, never let one abort the run."""
    def wrap(fn):
        if skip:
            RESULTS.append((name, True, "skipped"))
            return fn
        started = time.monotonic()
        try:
            detail = fn() or "ok"
            RESULTS.append((name, True, f"{detail} ({time.monotonic() - started:.1f}s)"))
        except AssertionError as exc:
            RESULTS.append((name, False, str(exc)))
        except Exception as exc:  # noqa: BLE001
            RESULTS.append((name, False, f"{type(exc).__name__}: {exc} | {traceback.format_exc()[-160:]}"))
        return fn
    return wrap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip paid model calls")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    import os

    @check("env: required secrets")
    def _env():
        required = ["IMPORT_SYNC_API_BASE_URL", "IMPORT_SYNC_API_KEY", "GEMINI_API_KEY", "SERPER_API_KEY"]
        missing = [k for k in required if not os.environ.get(k, "").strip()]
        assert not missing, f"missing env: {missing}"
        base = os.environ["IMPORT_SYNC_API_BASE_URL"]
        assert base.startswith("http"), f"bad base url {base!r}"
        return f"{len(required)} present, base={base.split('//')[-1][:28]}"

    from api_client import ResearchApiClient
    client = ResearchApiClient()

    @check("prod api: authenticated read")
    def _api():
        # 401/403 = bad key; 429 = throttled (the shared-bucket bug). Both are fatal
        # for an unattended run and must not be mistaken for "no work to do".
        data = client._get("robots/robots/", params={"status": "pending_review", "page": 1, "page_size": 1})
        assert isinstance(data, dict) and "results" in data, f"unexpected shape: {str(data)[:80]}"
        assert data.get("count", 0) > 0, "no pending_review robots visible — key scoped wrong?"
        return f"count={data['count']}"

    @check("serializer contract: loop-critical fields")
    def _fields():
        data = client._get("robots/robots/", params={"status": "pending_review", "page": 1, "page_size": 1})
        robot = (data.get("results") or [None])[0]
        assert robot, "no robot to inspect"
        # Absent != null here: a field missing from Meta.fields reads as None and is
        # silently dropped on write, which is how the fix loop ran blind for a day.
        required = ["quality_flags", "auto_fix_attempts", "auto_fix_status",
                    "rejection_categories", "family_name", "status"]
        missing = [f for f in required if f not in robot]
        assert not missing, f"NOT serialized (silently unreadable/unwritable): {missing}"
        return f"{len(required)} fields exposed"

    from web_extract import WebFetcher, parse_page
    fetcher = WebFetcher()

    @check("web fetch: page + main_images")
    def _fetch():
        page = parse_page(fetcher, PROBE_URL)
        assert page is not None, "probe page fetch returned None"
        assert len(page.text) > 2000, f"suspiciously short text ({len(page.text)}) — bot-walled?"
        assert page.main_images, "main_images empty — image scoping broken"
        # Regression guard for the option-list bug: main_text must not open with a
        # country picker, or every truncated-prefix consumer is poisoned.
        assert "afghanistan albania" not in (page.main_text or "").lower()[:400], \
            "main_text starts with a country dropdown — _scrub_noise regressed"
        return f"text={len(page.text)} main_images={len(page.main_images)}"

    @check("search: serper product-url lookup", skip=args.quick)
    def _serper():
        from product_url_search import search_product_url_for_robot
        url = search_product_url_for_robot("uKit AI", "UBTech Robotics", company_website="https://ubtrobot.com")
        assert url, "serper returned no product URL (key exhausted?)"
        return str(url)[:56]

    @check("grounded: json call survives a long answer", skip=args.quick)
    def _grounded_json():
        # Liveness AND truncation canary. The output-budget failure is INTERMITTENT —
        # it depends on how many tokens the model spends thinking, so a one-line
        # answer usually squeezes through and proves nothing. Demand a long structured
        # answer, which is what actually overflowed a tight budget in the real bug.
        from verify_lib import gemini_client
        import grounded_select as gs
        gclient = gemini_client()
        assert gclient is not None, "gemini_client() is None — GEMINI_API_KEY unusable"
        out = gs._generate_json(gclient, [
            "Return ONLY a JSON array of 12 objects, index 1..12, each "
            '{"index": <int>, "score": <int 0-100>, "reason": "<10-15 words of plain prose>"}.'
        ])
        assert out is not None, "_generate_json returned None — grounded layer is DEAD (token budget? API?)"
        assert isinstance(out, list), f"expected list, got {type(out).__name__}"
        # A truncated array parses to fewer items than asked; that is the failure mode.
        assert len(out) >= 10, f"only {len(out)}/12 items — output truncated (budget too tight?)"
        return f"{len(out)} items parsed"

    @check("grounded: vision scores real images", skip=args.quick)
    def _vision():
        from verify_lib import gemini_client
        from grounded_select import pick_hero_image
        from robot_auto_research import _clean_vision_pool
        page = parse_page(fetcher, PROBE_URL)
        pool = _clean_vision_pool(page.main_images, limit=6)
        assert pool, "vision pool empty after cleaning"
        res = pick_hero_image(gemini_client(), fetcher.session, name="uKit AI", model_name="uKit AI",
                              company_name="UBTech Robotics", description="", candidates=pool)
        assert res is not None, "pick_hero_image returned None — could not run (not a rejection)"
        assert res.get("scores"), "no scores returned"
        best = max(res["scores"].values())
        assert best >= 60, f"best score {best} — vision sees nothing on a known-good product page"
        return f"best={best}/100 pool={len(pool)}"

    @check("grounded: release-year control", skip=args.quick)
    def _year():
        # Control, not a probe: a well-documented launch. None here means the lookup
        # is broken, which would otherwise be misread as "no year exists" and get
        # permanently ledgered as a no-op.
        from release_year_lookup import lookup_release_year
        hit = lookup_release_year("Spot", "Boston Dynamics")
        assert hit and hit.get("year"), "control lookup failed — release-year path broken"
        return f"Spot={hit['year']} ({hit.get('confidence')})"

    @check("remedy library: planner + ledger")
    def _planner():
        from remedies import plan_remedies, is_terminal
        plan = plan_remedies(quality_flags=[{"flag": "missing_image", "severity": "error"},
                                            {"flag": "url_dead", "severity": "error"}])
        assert [f for f, _ in plan] == ["url_dead", "missing_image"], f"bad order: {[f for f,_ in plan]}"
        assert plan_remedies(quality_flags=["missing_image"],
                             attempts=[{"action": "refresh_media", "outcome": "no_op"}]) == [], \
            "ledger no-op blocking broken — the loop would repeat failed fixes forever"
        assert is_terminal(["not_real"]), "terminal category not honoured"
        return "order + blocking + terminal ok"

    @check("family: inference + vendor hint")
    def _family():
        from family_infer import infer_families
        out = infer_families([{"id": 1, "name": "Walker S2"}, {"id": 2, "name": "Walker X"},
                              {"id": 3, "name": "Yanshee"}])
        assert out.get(1, {}).get("family_name") == "Walker", f"inference broken: {out}"
        assert 3 not in out, "singleton wrongly assigned a family"
        return "infer ok"

    ok = all(passed for _, passed, _ in RESULTS)
    print("\n=== SMOKE TEST ===")
    for name, passed, detail in RESULTS:
        print(f"  {'PASS' if passed else 'FAIL'}  {name:42} {detail[:90]}")
    failed = [n for n, p, _ in RESULTS if not p]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed" + (f"  FAILED: {failed}" if failed else ""))
    if not ok:
        print("\nDo NOT start an unattended run — the pipeline would produce silent no-ops.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
