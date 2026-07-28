"""Classify a free-text `rejection_reason` into RejectionCategory values.

Rejections written before the structured category picker existed carry only prose.
Measured over the 545 rejected robots in prod (2026-07-26) these rules cover ~97%
of them, because reviewers already wrote semi-structured reasons — many use an
explicit `non_robot:` / `wrong_company:` prefix. Deterministic rules are preferred
over an LLM call here: they are free, reproducible, and auditable, which matters
because the category decides whether a robot is enriched or deleted.

Anything genuinely ambiguous returns ``["other"]`` rather than a guess — `other`
has no remedy, so the loop escalates it to a human instead of acting on a coin flip.
"""

from __future__ import annotations

import re

# Ordered: the first pattern that matches wins, so the most consequential and most
# specific categories are tested first. `not_real` leads because acting on it wrongly
# (enriching a phantom) is the costliest mistake — it recreates fabricated records.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("not_real", re.compile(
        r"^non[_ -]?robot|solution[_ -]?shell|non[_ -]?specific|"
        r"not a robot|not a physical robot|not robots|not an actual robot|"
        r"is (a )?softwar|is a (device|weapon|controller|platform|system|product|case|hub|radio)|"
        r"not a real|fabricat|doesn'?t exist|does not exist|no .{0,25}(series|model|product) on|"
        r"phantom|ghost|hallucinat|invented|non-existent|\bfake\b",
        re.I)),
    ("duplicate", re.compile(r"duplicate|\bdupe\b|same as|already (exists|in)|redundant", re.I)),
    ("wrong_company", re.compile(r"wrong[_ ]company|different company|company mismatch|belongs to|misfiled", re.I)),
    ("wrong_category", re.compile(r"categor|robot type|wrong[_ ]type|misclassif", re.I)),
    ("wrong_specs", re.compile(r"\bspec|payload|reach|\bdof\b|wrong data|incorrect", re.I)),
    ("bad_url", re.compile(r"\burl\b|\blink\b|\b404\b|off-domain|wrong page|source page|dead page", re.I)),
    ("wrong_image", re.compile(r"image|photo|hero|picture|render|\blogo\b", re.I)),
    ("thin_content", re.compile(r"\bthin\b|no description|low quality|empty|placeholder|lorem|no content", re.I)),
]


def classify_rejection_reason(reason: str) -> list[str]:
    """Map free-text reviewer prose onto RejectionCategory values.

    Returns every category whose rule matches (a reason can name several problems),
    ordered by the rule precedence above. Empty/unreadable prose yields ``["other"]``.
    """
    text = (reason or "").replace("�", "-").strip()
    if not text:
        return ["other"]
    hits = [name for name, pattern in _RULES if pattern.search(text)]
    return hits or ["other"]


def categories_for_robot(robot: dict) -> tuple[list[str], str]:
    """Structured categories for a robot, falling back to classifying its prose.

    Returns ``(categories, source)`` where source is "structured" (the reviewer
    picked them) or "classified" (derived from free text) — worth logging, since a
    classified category is a weaker signal than one a human selected.
    """
    stored = [c for c in (robot.get("rejection_categories") or []) if c]
    if stored:
        return stored, "structured"
    return classify_rejection_reason(robot.get("rejection_reason") or ""), "classified"
