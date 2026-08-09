"""Generate DISTINCT feature bullets from already-captured OEM text.

WHY (2026-08-03): "no blank features" was first implemented as a literal
description->features copy — the same shortcut the overnight path had always
used — which is exactly what the server's `features_duplicates_description`
flag (added 2026-08-01 after AgileX: 21 of 32 robots had features
byte-identical to description) exists to forbid. The drift-guard test named
that flag with "no remedy" all week; this module is the answer to both: a
generator that restructures OEM text into genuine feature bullets, and the
engine behind the `features_duplicates_description` remedy.

Rules:
  * Source-bound: bullets may only restate facts present in the supplied text
    (same no-invention rule as the extraction prompts).
  * Distinctness is VERIFIED, not assumed: output that still trips the
    server's own duplicate check is discarded — blank is better than a flag.
  * Metered via spend_guard (flash-lite: cheap), fails to "" on any error so
    callers hold/flag the row honestly instead of shipping junk.
"""

from __future__ import annotations

MODEL = "models/gemini-2.5-flash-lite"

_PROMPT = """You are writing the "Key features" list for a robotics catalog entry.

Robot: {name}

Source text (the ONLY facts you may use — do not add anything not stated here):
---
{text}
---

Write 3-6 short feature bullets. Each bullet:
- one concrete capability, spec, or differentiator FROM THE SOURCE TEXT
- 4-14 words, no marketing fluff, no bullet symbols, no trailing periods
- must NOT be a sentence copied from the source — rephrase into feature form

Respond with ONLY the bullets, one per line. If the source text contains no
usable product facts, respond with exactly: NONE"""


def features_from_text(name: str, text: str) -> str:
    """3-6 newline-joined feature bullets derived from `text`, or ''.

    '' means: no usable facts, generation failed, budget spent, or the output
    still duplicated the source — every one of those must surface as
    missing/flagged rather than as disguised duplication.
    """
    text = (text or "").strip()
    if len(text) < 40:
        return ""
    try:
        import spend_guard
        client = spend_guard.client(http_options={"api_version": "v1beta"})
        from google.genai import types as genai_types

        response = client.models.generate_content(
            model=MODEL,
            contents=_PROMPT.format(name=(name or "this robot")[:80], text=text[:2500]),
            config=genai_types.GenerateContentConfig(temperature=0.2, max_output_tokens=400),
        )
        raw = (response.text or "").strip()
    except Exception:  # noqa: BLE001 — budget spent / API error -> honest blank
        return ""

    if not raw or raw.upper().startswith("NONE"):
        return ""
    lines = [ln.strip(" -•*\t") for ln in raw.splitlines()]
    lines = [ln for ln in lines if 3 <= len(ln.split()) <= 20][:6]
    if len(lines) < 2:
        return ""
    out = "\n".join(lines)[:1500]

    # Verify with the SERVER'S OWN duplicate check — if this output would trip
    # the flag, it never leaves this function.
    try:
        from validate_staging import purpose_duplicates_description
        if purpose_duplicates_description(out, text):
            return ""
    except Exception:  # noqa: BLE001 — checker unavailable: fall back to a crude guard
        if out.lower()[:200] == text.lower()[:200]:
            return ""
    return out


# ---------------------------------------------------------------------------
# Deterministic feature cleanup (free — no model call)
# ---------------------------------------------------------------------------

import re as _re

# A page HEADING glued onto the first body sentence with no separator, e.g.
#   "A800 Lightweight Tactical Unmanned Helicopter The fuel-powered Alpha 800,
#    at less than 14 kg MTOW , is the most reliable UAV helicopter in its class."
# The Title-Case run is the product's own H1; a reviewer has to delete it by
# hand (Martti, 2026-08-09, robot 6446 — which scored 100 on AI verification
# because the text IS faithful to the source: verification measures fidelity,
# not editorial cleanliness, so this class can never be caught by the score).
_TITLE_GLUE_RE = _re.compile(
    r"^(?P<title>[A-Z0-9][\w\-/&®™]*(?:\s+[A-Z0-9][\w\-/&®™]*){1,7})\s+"
    r"(?P<rest>(?:The|This|These|A|An|It|Its|With|Designed|Powered|Built|"
    r"Featuring|Equipped|Capable|Ideal|Suitable)\b.+)$"
)
# " MTOW ," / "minutes ." — inline tags (<strong>) joined with padding spaces.
_SPACE_BEFORE_PUNCT_RE = _re.compile(r"\s+([,.;:!?])")

# Site chrome swept up by whole-page text extraction: cookie banners, footers,
# nav menus, login walls. Found on 36 live rows 2026-08-09 — including PUDU
# HolaBot (3203), whose features were a German cookie notice while its AI
# verification score was 100. Verification compares content to the source page;
# a footer IS on the source page, so the score can never catch this.
_CHROME_RE = _re.compile(
    r"privacy policy|copyright\s*©|all rights reserved|sitemap|subscribe to|"
    r"cookies?\b|terms of use|terms and conditions|follow us|newsletter|"
    r"contact us|datenschutz|abonnieren|kontakt|"
    r"please login|log ?in to|sign ?up|©\s*20\d\d|if you continue to browse",
    _re.I,
)


def _identity_tokens(*values: str) -> set[str]:
    out: set[str] = set()
    for value in values:
        for tok in _re.split(r"[^a-z0-9]+", (value or "").lower()):
            if tok and len(tok) > 1:
                out.add(tok)
    return out


def clean_feature_lines(features: str, *, name: str = "", model_name: str = "") -> str:
    """Strip scraper artifacts from feature text. Free, deterministic, lossless
    for genuine content.

    Two fixes, both observed on real rows:
      1. The product's own title glued to the front of the first bullet. Only
         removed when the Title-Case prefix shares an identity token with the
         robot's name/model — a heading that ISN'T the product name is left
         alone rather than silently deleted.
      2. Whitespace before punctuation from inline-tag joining.
    """
    if not features or not features.strip():
        return features or ""
    identity = _identity_tokens(name, model_name)
    out: list[str] = []
    for raw_line in features.splitlines():
        line = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", raw_line.strip(" -•*\t"))
        if not line:
            continue
        # Site chrome is never a product feature. Dropping it can empty the
        # field — that is the honest outcome: a blank raises `missing_features`
        # and remediation regenerates from real page text, whereas a cookie
        # banner sits in the queue looking like content.
        if _CHROME_RE.search(line):
            continue
        match = _TITLE_GLUE_RE.match(line)
        if match:
            title_tokens = _identity_tokens(match.group("title"))
            # Only a prefix that names THIS product is a heading to drop.
            if identity and (title_tokens & identity):
                line = match.group("rest").strip()
        # A bullet that is nothing but the product title carries no fact.
        elif identity:
            line_tokens = _identity_tokens(line)
            if len(line.split()) <= 8 and line_tokens and line_tokens <= (identity | _TYPE_WORDS):
                continue
        if line:
            out.append(line)
    return "\n".join(out)


# Generic product-type vocabulary — a bullet made only of these plus the
# robot's own name is a title, not a feature.
_TYPE_WORDS = {
    "robot", "robotic", "system", "systems", "series", "platform", "unmanned",
    "helicopter", "drone", "uav", "vehicle", "arm", "cobot", "lightweight",
    "compact", "tactical", "industrial", "autonomous", "mobile", "aerial",
    "the", "and", "for", "with",
}
