"""Bridge to the server's content-brief description generator.

Same pattern as verify_lib: robots/description_gen.py is deliberately
Django-free so the research scripts reuse the exact prompt, validator, and
model cascade that the admin button and the generate_descriptions command use.
One implementation of the brief on both sides of the import.
"""

from __future__ import annotations

from typing import Any

import verify_lib  # noqa: F401  — side effect: puts robotaigeek-server on sys.path
from robots import description_gen as server_description_gen  # noqa: E402


def facts_from_staged(staged: Any) -> dict:
    """Map a StagedRobot onto the brief's fact slots (see description_gen.collect_facts)."""
    robot_type = ", ".join(p for p in (
        (staged.category_slugs or "").replace("|", ", "),
        (staged.movement_type_keys or "").replace("|", ", "),
    ) if p)
    primary_task = (staged.purpose or "").strip() or (staged.use_keys or "").replace("|", ", ")
    environment = ", ".join(p for p in (
        (staged.industry_keys or "").replace("|", ", "),
        (staged.sub_category_slug or "").replace("-", " "),
    ) if p)

    spec_bits = []
    for label, value, unit in (
        ("weight", staged.weight_kg, " kg"),
        ("payload", staged.payload_kg, " kg"),
        ("reach", staged.reach_mm, " mm"),
        ("speed", staged.speed_ms, " m/s"),
        ("degrees of freedom", staged.dof, ""),
        ("runtime", staged.runtime_minutes, " min"),
    ):
        if value:
            spec_bits.append(f"{label} {value}{unit}")
    differentiator = (staged.features or "").strip() or "; ".join(spec_bits)

    facts = {
        "robot_name": staged.name,
        "company_name": staged.company_name or "",
        "robot_type": robot_type,
        "primary_task": primary_task,
        "environment": environment,
        "existing_description": (staged.description or "").strip(),
        "release_year": staged.release_year or "",
        "differentiator": differentiator,
        "deployment_evidence": (staged.availability_status_key or "").replace("_", " "),
    }
    # Extended-description narrative slots — read straight off the staged columns,
    # same as the server's collect_facts. When any is present the generator expands
    # to the fuller editorial profile instead of the short Track-A description.
    for key in server_description_gen.EXTENDED_FIELDS:
        val = getattr(staged, key, "")
        facts[key] = val.strip() if isinstance(val, str) else ""
    return facts


def generate_for_staged(staged: Any) -> dict | None:
    """Generate a brief-style description for a staged robot.

    Returns the generation result, or None when generation isn't possible —
    required fact slots empty, GEMINI_API_KEY unset, or the model/validation
    failed. Callers keep their existing fallback (scraped meta description)."""
    facts = facts_from_staged(staged)
    required = ("company_name", "robot_type", "primary_task", "environment")
    if any(not facts[k] for k in required):
        return None
    try:
        return server_description_gen.generate_from_facts(facts)
    except server_description_gen.DescriptionGenerationError:
        return None
