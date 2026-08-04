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
