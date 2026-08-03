"""Search-grounded release-year lookup for robot enrichment.

Launch years rarely appear on product pages — they live in press releases,
launch coverage, and dated datasheets. So this asks Gemini with Google Search
grounding (same pattern as product_url_search / YouTube search) and only
returns a year when the model can point at a dated source for THE SPECIFIC
MODEL — the RAI spec forbids using the product line's earliest generation.

Discipline mirrors fix_segway_robots.py: a year needs a citation; uncertain
stays null. The caller stages the citation into research_notes so a human can
audit it later.
"""

from __future__ import annotations

import json
import os
import re

MODEL = "models/gemini-2.5-flash"
MIN_YEAR, MAX_YEAR = 1950, 2030

# The prompt already forbids copyright/footer years, but the model does not always obey:
# on bwsensing.com it returned year=2026 with evidence "Copyright © 2026 Wuxi Bewis Sensing
# Technology LLC. All Rights Reserved." and marked it high-confidence. A copyright notice, a
# generic footer greeting, or a bare "© YYYY" only proves the page exists — never a launch.
# Reject at parse time so a disobeyed prompt rule can't stamp a wrong year on the record.
_NON_LAUNCH_EVIDENCE_RE = re.compile(
    r"copyright|\(c\)\s*\d{4}|©\s*\d{4}|\d{4}\s*©|all rights reserved|"
    r"\bwelcome to\b|\bprivacy policy\b|\bterms of (use|service)\b",
    re.IGNORECASE,
)

_PROMPT = """Search for when the robot "{name}"{model_part} made by "{company}" was FIRST \
announced or commercially launched.

Rules:
- The year must be for THIS SPECIFIC MODEL/revision, NOT the product line's first generation \
or an earlier version, and NOT a sibling/variant model with a similar name.
- Only report a year backed by a dated source: an official press release, launch news article, \
or dated manufacturer document.
- The source must state the LAUNCH/ANNOUNCEMENT itself. A trade-show or exhibition appearance, \
a demo, a review, a spec sheet/brochure/datasheet publication date, or a page's copyright year \
only proves the product already existed by then — that is NOT a launch date; return null.
- If sources conflict or you cannot find a dated source for this exact model, return null.

Respond with ONLY a JSON object, no markdown:
{{"year": <int|null>, "source_url": "<url of the dated source or empty>", \
"evidence": "<max 25 words quoting/paraphrasing the dated statement>", \
"is_specific_model": <true|false>}}"""


def _parse_lookup_response(text: str) -> dict | None:
    """Extract and validate the JSON verdict. None when unusable — a bad parse
    must never invent a year."""
    text = (text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    year = data.get("year")
    if isinstance(year, str) and re.fullmatch(r"\d{4}", year.strip()):
        year = int(year)
    if isinstance(year, bool) or not isinstance(year, int):
        return None
    if not (MIN_YEAR <= year <= MAX_YEAR):
        return None

    source_url = str(data.get("source_url") or "").strip()
    evidence = str(data.get("evidence") or "").strip()[:300]
    if not evidence:
        return None  # a year with no supporting statement is a guess
    if _NON_LAUNCH_EVIDENCE_RE.search(evidence):
        return None  # copyright/footer text proves existence, not a launch — never a year
    return {
        "year": year,
        "source_url": source_url,
        "evidence": evidence,
        # high = dated source named AND model-specific; medium = one of the two is shaky
        "confidence": "high" if (source_url and data.get("is_specific_model") is True) else "medium",
    }


def citation_line(hit: dict) -> str:
    """research_notes line for a grounded hit — the auditable trail a staged year
    must always carry: 'release_year=YYYY: <evidence> (<source url>)'."""
    line = f"release_year={hit['year']}: {hit['evidence']}"
    if hit.get("source_url"):
        line += f" ({hit['source_url']})"
    return line


def lookup_release_year(
    robot_name: str,
    company_name: str,
    *,
    model_name: str = "",
) -> dict | None:
    """Return {"year", "source_url", "evidence", "confidence"} or None.
    Fail-open: no API key, quota exhaustion, or any API error returns None."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or not robot_name:
        return None

    from google import genai
    from google.genai import types as genai_types

    model_part = f" (model {model_name})" if model_name and model_name != robot_name else ""
    prompt = _PROMPT.format(name=robot_name, model_part=model_part, company=company_name)

    try:
        import spend_guard
        client = spend_guard.client(api_key=api_key, http_options={"api_version": "v1beta"})
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=500,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                # Google Search grounding can't be combined with JSON response mode,
                # so the prompt demands bare JSON and _parse_lookup_response is defensive.
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
            ),
        )
    except Exception:
        return None

    result = _parse_lookup_response(response.text or "")
    if result and not result["source_url"]:
        # Model gave a year but no URL — try to salvage one from grounding metadata
        # so research_notes always carries something auditable.
        try:
            chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if web and web.uri:
                    result["source_url"] = web.uri
                    break
        except Exception:
            pass
    return result
