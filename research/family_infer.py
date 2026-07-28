"""Infer robot family / variant from a company's own catalogue.

Family metadata has full plumbing — `StagedRobot` carries the six fields, and the
bulk import normalises them via `robots.family.resolve_import_family_metadata`
(deriving `family_key` as ``{company_slug}:{slug(family_name)}`` when blank) — but
NOTHING populates it: neither `discover_robots` nor `robot_auto_research` sets a
family field, so every value in the DB so far came from a hand-written retrofit
script. UBTech is 0/19 despite Walker x6, Cruzr x4, uKit x2, Alpha x2.

The inference rule is deliberately evidence-based rather than clever: a family is
asserted only when **two or more robots of the same company share a leading token**.
That keeps it grounded in the vendor's actual model line-up instead of inventing a
series from one ambiguous name — a singleton like "Yanshee" or "UGOT" correctly
gets nothing. It is a floor, not a replacement for the vendor's own series
taxonomy: when a page states the series explicitly, that should win.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

# Leading words that are never a family on their own — they would group unrelated
# models under a meaningless banner.
_GENERIC_HEADS = {
    "robot", "robotic", "robotics", "the", "new", "smart", "ai", "auto",
    "mobile", "industrial", "collaborative", "service", "humanoid",
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9\-\.]+")

MIN_FAMILY_MEMBERS = 2


def _tokens(name: str) -> list[str]:
    return _TOKEN_RE.findall((name or "").strip())


def _head_candidates(name: str) -> list[str]:
    """Possible family labels for a name, most specific first.

    Two naming conventions have to work, because both are everywhere:
      * space-separated  "Walker S2"    -> "Walker"
      * hyphenated       "TP6-30SGH"    -> "TP6"   (the model code IS one token)
    Taking only the first whitespace token handles the first and silently fails the
    second — measured on Hikrobot, where 21 robots forming obvious TP5/TP6/C3/Q3
    families all came back as singletons because "TP6-30SGH" shares no token with
    "TP6-50SCH". Most industrial catalogues are hyphenated, so that is the common case.
    """
    toks = _tokens(name)
    if not toks:
        return []
    head = toks[0]
    if head.lower() in _GENERIC_HEADS:
        # "Robot X1" alone is meaningless; try a two-word head instead.
        return [" ".join(toks[:2])] if len(toks) > 1 else []
    out = [head]
    if "-" in head:
        prefix = head.split("-", 1)[0]
        # A one-character prefix ("F-500") groups far too loosely to mean anything.
        if len(prefix) >= 2 and prefix.lower() not in _GENERIC_HEADS:
            out.append(prefix)
    return out


def _head(name: str) -> str:
    """Most specific candidate — kept for callers that want a single label."""
    cands = _head_candidates(name)
    return cands[0] if cands else ""


def _variant_for(name: str, family: str) -> str:
    """Whatever distinguishes this model within its family ("Walker S2" -> "S2").

    Empty when the robot IS the base model (a bare "Cruzr" in a Cruzr family) —
    that is meaningful, not a failure.
    """
    n, f = (name or "").strip(), (family or "").strip()
    if not f or not n.lower().startswith(f.lower()):
        return ""
    return n[len(f):].strip(" -–—:")


def infer_families(
    robots: Iterable[dict[str, Any]],
    *,
    min_members: int = MIN_FAMILY_MEMBERS,
) -> dict[int, dict[str, str]]:
    """Map robot id -> {"family_name", "variant_label"} for robots in a real family.

    Pass the company's WHOLE catalogue (not just the review queue): a model whose
    siblings are already approved still belongs to the family, and slicing the
    input by status would hide that.
    """
    robots = list(robots)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for robot in robots:
        for cand in _head_candidates(str(robot.get("name") or "")):
            groups[cand.lower()].append(robot)

    # A robot can match several candidates ("TP6-30SGH" -> "TP6-30SGH" and "TP6").
    # Prefer the MOST SPECIFIC label that still has real siblings, so near-identical
    # variants group tightly instead of collapsing into one giant vendor-wide family.
    out: dict[int, dict[str, str]] = {}
    for key in sorted(groups, key=len, reverse=True):
        members = groups[key]
        if len(members) < min_members:
            continue
        # Most common surface form sets the casing, so it follows the vendor
        # ("uKit", not "ukit").
        surfaces = [
            c for m in members for c in _head_candidates(str(m.get("name") or ""))
            if c.lower() == key
        ]
        family = max(set(surfaces), key=surfaces.count) if surfaces else key
        for member in members:
            rid = member.get("id")
            if rid is None or int(rid) in out:
                continue  # a more specific family already claimed this robot
            name = str(member.get("name") or "")
            out[int(rid)] = {
                "family_name": family,
                "variant_label": _variant_for(name, family),
            }
    return out


def describe(robots: Iterable[dict[str, Any]], inferred: dict[int, dict[str, str]]) -> str:
    """Human-readable grouping, for dry-run review before anything is written."""
    by_family: dict[str, list[str]] = defaultdict(list)
    singles: list[str] = []
    for robot in robots:
        rid = robot.get("id")
        name = str(robot.get("name") or "")
        hit = inferred.get(int(rid)) if rid is not None else None
        if hit:
            by_family[hit["family_name"]].append(f"{name} [{hit['variant_label'] or 'base'}]")
        else:
            singles.append(name)
    lines = []
    for family, members in sorted(by_family.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {family} ({len(members)}): " + ", ".join(sorted(members)))
    if singles:
        lines.append(f"  (no family — singletons): {', '.join(sorted(singles))}")
    return "\n".join(lines)
