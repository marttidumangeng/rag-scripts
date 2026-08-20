"""Flag -> remedy registry, and the ledger-aware planner.

ONE vocabulary drives the loop: `robots.quality.FLAG_REGISTRY` keys. Reviewer
rejection categories are mapped onto those same keys (REJECTION_CATEGORY_TO_FLAGS)
so the QA path and the rejection path share every remedy instead of maintaining
two parallel taxonomies that drift.

`plan_remedies` is the anti-waste brain: it reads the robot's attempt ledger and
refuses to re-run an action that already came back NO_OP, or that has burned its
retry budget — which is what turns "re-run enrichment and hope" into "try the
next thing, then escalate".
"""

from __future__ import annotations

from typing import Any

from . import engine
from .base import FAILED, FIXED, NO_OP, RemedyFn

# ---------------------------------------------------------------------------
# flag key (robots.quality.FLAG_REGISTRY) -> remedy
# ---------------------------------------------------------------------------
REMEDY_REGISTRY: dict[str, RemedyFn] = {
    # media
    "missing_image": engine.remedy_missing_image,
    "image_mismatch": engine.remedy_image_mismatch,
    "image_dead": engine.remedy_image_dead,
    "few_photos": engine.remedy_few_photos,
    # source url
    "missing_url": engine.remedy_missing_url,
    "url_dead": engine.remedy_url_dead,
    "malformed_url": engine.remedy_malformed_url,
    "url_domain_mismatch": engine.remedy_url_domain_mismatch,
    "url_content_mismatch": engine.remedy_url_content_mismatch,
    # narrative
    "missing_description": engine.remedy_missing_description,
    "short_description": engine.remedy_short_description,
    "content_contradiction": engine.remedy_content_contradiction,
    "missing_purpose": engine.remedy_missing_purpose,
    "purpose_duplicates_description": engine.remedy_purpose_duplicates_description,
    "missing_features": engine.remedy_missing_features,
    "features_duplicates_description": engine.remedy_features_duplicates_description,
    "image_not_uploaded": engine.remedy_image_not_uploaded,
    # video
    "missing_video": engine.remedy_missing_video,
    "video_mismatch": engine.remedy_video_mismatch,
    # structured
    "missing_specs": engine.remedy_missing_specs,
    # "missing_release_year": quarantined — see UNFIXABLE_FLAGS (non-deterministic lookup)
    "missing_tags": engine.remedy_missing_tags,
    "missing_category": engine.remedy_missing_category,
    "missing_taxonomy": engine.remedy_missing_taxonomy,
    "missing_family": engine.remedy_missing_family,
    "missing_manufacturer_country": engine.remedy_missing_manufacturer_country,
}

MEDIA_FLAGS: frozenset[str] = frozenset({
    "missing_image", "image_mismatch", "image_dead", "few_photos",
})
"""Flags whose remedy re-fetches a page fresh every pass and naturally varies
run to run (different query-string params, source ordering) even when nothing
meaningful changed — so they can register as FIXED indefinitely without ever
satisfying the underlying flag (e.g. a site with only 2 real product photos
can never clear `few_photos`'s "want 4+"). Callers must NOT let a FIXED result
on one of these stop the pass the way a real content change should — found
live on Estun (2026-07-31): `few_photos` re-"fixed" every single run, which
under the normal "stop after one real change" rule permanently starved
`missing_features`/`missing_specs` of ever being attempted in the same pass.
"""

# Flags no remedy can fix automatically — they need a human or a different
# pipeline (dedupe, company reassignment, translation).
UNFIXABLE_FLAGS: frozenset[str] = frozenset({
    "duplicate_suspect", "shared_url", "non_english_content", "unverifiable",
    # `missing_manufacturer_country` was here until 2026-07-31 and should never
    # have been: it is an ERROR-severity flag with a deterministic source (the
    # company's HQ country), and parking it here left 351 pending robots with a
    # permanent red chip. It now has `remedy_missing_manufacturer_country`,
    # which also backfills the Company so its siblings are fixed for free.
    "missing_price", "missing_availability",
    # Duplicate/variant photos within one robot's gallery. Deliberately NOT wired to
    # refresh_media: many OEMs publish only FAMILY-level images (measured on Hikrobot
    # 2026-07-26 — sibling models return byte-identical image sets), so re-researching
    # tends to re-attach the same duplicates. Belongs to the hash-based dedupe pass
    # (scripts/research/detect_duplicate_heroes.py), not to a blind media refresh.
    "duplicate_images",
    # QUARANTINED 2026-07-26, not permanently unfixable. `lookup_release_year` is
    # non-deterministic: three calls for uKit AI (robot 3514) in one run returned
    # 2024, 2025, 2025 — every one "high" confidence and each carrying its own
    # citation, so the citation gate does not catch it. Re-enable (move back to
    # REMEDY_REGISTRY + REMEDY_ORDER, and drop from QUARANTINED_FIELDS) once a year
    # must be confirmed by two agreeing lookups before it can be staged.
    "missing_release_year",
})

QUARANTINED_FIELDS: frozenset[str] = frozenset({
    # Never written by a remedy — not even as a gap-fill side effect. `_merge_staged`
    # fills EVERY blank field from the research result, not just the remedy's target,
    # so without this a "fix purpose" run would quietly stamp an unreliable
    # release_year too, and the ledger would only record "purpose fixed".
    "release_year",
})

# ---------------------------------------------------------------------------
# Reviewer rejection categories (robots.models.RejectionCategory)
# ---------------------------------------------------------------------------
TERMINAL_CATEGORIES: frozenset[str] = frozenset({"not_real", "duplicate"})
"""Never enrich these. `not_real` re-enriched just recreates the phantom (the
Estun ER-DB signature); `duplicate` belongs to the dedupe pipeline."""

REJECTION_CATEGORY_TO_FLAGS: dict[str, list[str]] = {
    "wrong_image": ["image_mismatch"],
    "wrong_specs": ["missing_specs"],
    "bad_url": ["url_content_mismatch"],
    "thin_content": ["short_description", "missing_features"],
    "wrong_category": ["missing_category"],
    # routed to humans/other pipelines, no auto-remedy:
    "wrong_company": [],
    "not_real": [],
    "duplicate": [],
    "other": [],
}

# Order matters for two reasons:
#  1. IMPORT-BLOCKING fixes go first. Server-side validation rejects the WHOLE
#     staged row, so one bad field vetoes unrelated repairs: measured 2026-07-26 on
#     Cruzr 1S (3517), `few_photos` and `missing_features` both came back
#     "import failed: purpose: purpose repeats description" purely because the
#     stale purpose was still in place. Clearing that first unblocks the rest.
#  2. Then cheap/structural fixes: a correct source URL improves everything
#     researched from it, so repair the anchor before the content drawn from it.
#  3. `missing_manufacturer_country` runs FIRST of all: it is the only
#     error-severity flag with a remedy, it usually needs no network (the value
#     comes off the Company), and when it does resolve one it writes the Company
#     too — so every later robot from that manufacturer takes the free path.
REMEDY_ORDER: list[str] = [
    "missing_manufacturer_country",
    "purpose_duplicates_description", "missing_purpose",
    "missing_url", "malformed_url", "url_dead", "url_domain_mismatch", "url_content_mismatch",
    "missing_image", "image_dead", "image_mismatch", "few_photos",
    "image_not_uploaded",
    "missing_description", "short_description", "content_contradiction",
    "missing_features", "features_duplicates_description",
    "missing_specs",
    "missing_category", "missing_taxonomy", "missing_family", "missing_tags",
    "missing_video", "video_mismatch",
]

MAX_ATTEMPTS_PER_ACTION = 2
"""A hard failure earns one retry; NO_OP earns none."""

import os as _os

MAX_TOTAL_ATTEMPTS_PER_ROBOT = int(
    _os.environ.get("REMEDY_MAX_TOTAL_ATTEMPTS") or 12
)
"""Global per-robot remediation budget — the cap the per-ACTION limits miss.

Per-action caps stop one remedy looping, but a robot carries many flags, and
flags recompute after every write, so a row can keep qualifying for a
DIFFERENT remedy indefinitely. Measured 2026-08-09: 334 pending/draft robots
had >=6 logged attempts and 60 had >=10 (worst: 35), while 1,576 attempts were
logged in two days at ~$30/day of Gemini — with the queue's approvable count
barely moving. That is Martti's "repeatedly spending API calls on the same
item with not much progress", quantified.

Past this budget the robot is not improving under automation: stop spending
and let a human look. Escalation is what plan_remedies returning [] already
triggers in every caller."""

MEDIA_ACTIONS: frozenset[str] = frozenset({"refresh_media"})
"""The action behind every MEDIA_FLAGS remedy — kept separate from MEDIA_FLAGS
(flag names) because blocked_actions() works on actions, not flags."""

MAX_MEDIA_FIXED_ATTEMPTS = 3
"""Media remedies almost never return NO_OP or FAILED — the researcher
re-fetches fresh every pass and minor variation (query params, source
ordering) registers as a real change even when nothing meaningful improved,
so the normal no-op/failure circuit breaker never trips. Confirmed live on
Estun (2026-08-01): individual robots hit 26 "fixed" media attempts with no
real convergence, at Gemini VISION cost (the most expensive call type) every
single time — a direct, quantifiable driver of an unexplained cost spike.
This caps repeated FIXED outcomes too, specifically for media, so a company
whose site genuinely doesn't have more photos gets escalated instead of
re-billed forever."""

WEBSITE_FREE_FLAGS: frozenset[str] = frozenset({
    # `missing_category` derives from the robot's own stored taxonomy — no page
    # fetch at all. `missing_manufacturer_country` has a company fast path and,
    # failing that, a search tier that works from the company NAME.
    "missing_category", "missing_manufacturer_country",
})
"""Flags whose remedies do not need the company's OEM site.

Callers that skip website-less companies (every remedy that re-researches SKIPs
for them) must still let these through, or a manufacturer whose site can never
be resolved keeps a permanently unfixable "No category"/"No country" chip on
every robot it owns."""


def is_terminal(categories: list[str] | None) -> bool:
    """True when the robot must not be enriched at all."""
    return bool(TERMINAL_CATEGORIES & set(categories or []))


def flags_from_categories(categories: list[str] | None) -> list[str]:
    """Map reviewer rejection categories onto quality-flag keys."""
    out: list[str] = []
    for cat in categories or []:
        out.extend(REJECTION_CATEGORY_TO_FLAGS.get(cat, []))
    return list(dict.fromkeys(out))


# `triage_content_queue.robot_gaps()` key -> quality-flag key.
# Needed because the research API does NOT serialize `quality_flags` (server-side
# only), so client-side gap detection is the loop's flag source until the
# serializer exposes it.
GAP_TO_FLAG: dict[str, str] = {
    "no_image": "missing_image",
    "no_features": "missing_features",
    "no_videos": "missing_video",
    "no_tags": "missing_tags",
    "no_url": "missing_url",
    "no_specs": "missing_specs",
    "no_country": "missing_manufacturer_country",
    "no_category": "missing_category",
    "no_company": "",  # wrong company is a human/dedupe call, not a remedy
}


def flags_from_gaps(gaps: list[str] | None) -> list[str]:
    """Translate client-side `robot_gaps()` output into quality-flag keys."""
    out = [GAP_TO_FLAG.get(g, "") for g in (gaps or [])]
    return [f for f in dict.fromkeys(out) if f]


def _flag_keys(flags: Any) -> list[str]:
    """Accept either raw keys or `quality_flags` dicts ({flag, severity, detail})."""
    out: list[str] = []
    for f in flags or []:
        key = f.get("flag") if isinstance(f, dict) else f
        if key:
            out.append(str(key))
    return out


def blocked_actions(attempts: list[dict[str, Any]] | None) -> set[str]:
    """Actions the ledger says must not run again.

    - any action that returned NO_OP -> the pipeline cannot currently do better
    - any action that failed >= MAX_ATTEMPTS_PER_ACTION times
    - a MEDIA_ACTIONS action that returned FIXED >= MAX_MEDIA_FIXED_ATTEMPTS
      times -> it keeps "succeeding" without the flag ever actually clearing
      (see MAX_MEDIA_FIXED_ATTEMPTS), which normal failure/no-op counting
      can't catch since it never fails or no-ops
    """
    blocked: set[str] = set()
    failures: dict[str, int] = {}
    media_fixed: dict[str, int] = {}
    for entry in attempts or []:
        action = str(entry.get("action") or "")
        outcome = str(entry.get("outcome") or "")
        if not action:
            continue
        if outcome == NO_OP:
            blocked.add(action)
        elif outcome == FAILED:
            failures[action] = failures.get(action, 0) + 1
            if failures[action] >= MAX_ATTEMPTS_PER_ACTION:
                blocked.add(action)
        elif outcome == FIXED and action in MEDIA_ACTIONS:
            media_fixed[action] = media_fixed.get(action, 0) + 1
            if media_fixed[action] >= MAX_MEDIA_FIXED_ATTEMPTS:
                blocked.add(action)
    return blocked


def plan_remedies(
    *,
    quality_flags: Any = None,
    rejection_categories: list[str] | None = None,
    attempts: list[dict[str, Any]] | None = None,
    errors_only: bool = False,
) -> list[tuple[str, RemedyFn]]:
    """Ordered [(flag, remedy)] to run for this robot, ledger-aware.

    Returns [] when the robot is terminal, over its total attempt budget, has
    no fixable flags, or every applicable remedy is already blocked — the
    caller escalates instead of re-running a pass that would change nothing.
    """
    if is_terminal(rejection_categories):
        return []
    # Global spend ceiling per robot (see MAX_TOTAL_ATTEMPTS_PER_ROBOT).
    if len(attempts or []) >= MAX_TOTAL_ATTEMPTS_PER_ROBOT:
        return []

    keys: list[str] = []
    if errors_only:
        for f in quality_flags or []:
            if isinstance(f, dict) and f.get("severity") == "error" and f.get("flag"):
                keys.append(str(f["flag"]))
    else:
        keys = _flag_keys(quality_flags)
    keys.extend(flags_from_categories(rejection_categories))

    seen = set(keys)
    blocked = blocked_actions(attempts)
    plan: list[tuple[str, RemedyFn]] = []
    for flag in REMEDY_ORDER:
        if flag not in seen:
            continue
        fn = REMEDY_REGISTRY.get(flag)
        if fn is None:
            continue
        # Remedies share actions (all url_* -> refresh_url); block by action so a
        # NO_OP on one URL flag doesn't get retried under a sibling flag's name.
        action = getattr(fn, "__name__", "")
        probe = _action_for_flag(flag)
        if probe in blocked or action in blocked:
            continue
        plan.append((flag, fn))
    return plan


_ACTION_BY_FLAG = {
    **{f: "refresh_url" for f in ("missing_url", "url_dead", "malformed_url", "url_domain_mismatch", "url_content_mismatch")},
    **{f: "refresh_media" for f in ("missing_image", "image_mismatch", "image_dead", "few_photos")},
    **{f: "refresh_description" for f in ("missing_description", "short_description", "content_contradiction", "missing_purpose", "purpose_duplicates_description")},
    "missing_features": "refresh_features",
    "features_duplicates_description": "refresh_features",
    "image_not_uploaded": "copy_media_upload",
    **{f: "refresh_video" for f in ("missing_video", "video_mismatch")},
    "missing_specs": "refresh_specs",
    "missing_release_year": "refresh_release_year",
    "missing_tags": "refresh_tags",
    # `missing_category` gets its OWN action, not the shared `refresh_taxonomy`.
    # Blocking is by action, so while they shared one a NO_OP from either flag
    # suppressed the other — and they are no longer the same operation at all
    # (category is an offline derivation, taxonomy re-researches the page).
    # The rename also retires every stale `refresh_taxonomy` ledger entry left by
    # the broken category remedy, which is what un-sticks the robots it blocked.
    "missing_category": "refresh_category",
    "missing_taxonomy": "refresh_taxonomy",
    "missing_family": "refresh_family",
    "missing_manufacturer_country": "refresh_country",
}


def _action_for_flag(flag: str) -> str:
    return _ACTION_BY_FLAG.get(flag, flag)
