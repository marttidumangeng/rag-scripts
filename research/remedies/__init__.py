"""Tier-1 deterministic remedy library.

One tested function per quality flag, instead of one hand-written ``fix_*.py``
per company. The QA/rejection loop resolves flags -> remedies through
``plan_remedies`` and never has to know how any individual fix works.

    from remedies import RemedyContext, plan_remedies

    ctx = RemedyContext(company_id=220, company_name="Estun", company_slug="estun",
                        company_website="https://www.estun.com", dry_run=True)
    for flag, remedy in plan_remedies(quality_flags=robot["quality_flags"],
                                      attempts=robot["auto_fix_attempts"]):
        result = remedy(robot, ctx)
        ledger.append(result.to_attempt())
        if result.changed and flag not in MEDIA_FLAGS:
            break   # re-run QA before trying the next flag — media flags are
                     # noisy on re-fetch and must not eat the pass alone
                     # (Estun 2026-07-31: few_photos re-"fixed" every run and
                     # permanently starved missing_features/missing_specs)
"""

from .base import (  # noqa: F401
    FAILED,
    FIXED,
    NO_OP,
    SKIPPED,
    TERMINAL,
    RemedyContext,
    RemedyFn,
    RemedyResult,
    diff_fields,
    snapshot,
)
from .classify import categories_for_robot, classify_rejection_reason  # noqa: F401
from .engine import run_reresearch  # noqa: F401
from .registry import (  # noqa: F401
    GAP_TO_FLAG,
    MAX_ATTEMPTS_PER_ACTION,
    MEDIA_FLAGS,
    REJECTION_CATEGORY_TO_FLAGS,
    REMEDY_ORDER,
    REMEDY_REGISTRY,
    TERMINAL_CATEGORIES,
    UNFIXABLE_FLAGS,
    WEBSITE_FREE_FLAGS,
    blocked_actions,
    flags_from_categories,
    flags_from_gaps,
    is_terminal,
    plan_remedies,
)

__all__ = [
    "RemedyContext", "RemedyResult", "RemedyFn",
    "FIXED", "NO_OP", "FAILED", "SKIPPED", "TERMINAL",
    "REMEDY_REGISTRY", "REMEDY_ORDER", "UNFIXABLE_FLAGS", "MEDIA_FLAGS",
    "TERMINAL_CATEGORIES", "REJECTION_CATEGORY_TO_FLAGS", "MAX_ATTEMPTS_PER_ACTION",
    "plan_remedies", "is_terminal", "flags_from_categories", "flags_from_gaps",
    "GAP_TO_FLAG", "WEBSITE_FREE_FLAGS", "blocked_actions",
    "run_reresearch", "snapshot", "diff_fields",
]
