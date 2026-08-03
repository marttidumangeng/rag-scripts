"""Gemini-grounded selection for the robot researcher.

The heuristic pickers in web_extract.py choose by URL tokens and filename
patterns — they never look at the pixels or read the page. These helpers add a
grounded second opinion using the same scoring conventions as the server's
verifier (0-100, one-line rationale):

  pick_hero_image      — downloads the candidate images and has the model pick
                         which actually SHOW this robot (kills the
                         sibling-model / banner / logo hero problem)
  confirm_product_url  — reads already-fetched page text and scores whether the
                         page is this robot's own product page vs a catalog,
                         news article, or different model
  filter_videos        — scores enriched video metadata (title/channel/
                         description) for whether each video belongs to this
                         robot

Every function is fail-open: any API/network error returns None and the caller
keeps the heuristic result. Grounding upgrades accuracy; it never blocks
research.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

MODEL = "models/gemini-2.5-flash"
MATCH_THRESHOLD = 50  # same convention as robots/quality.py VERIFICATION_MISMATCH_THRESHOLD
MAX_IMAGE_CANDIDATES = 8


def _generate_json(client, parts: list, *, max_output_tokens: int = 4096) -> Any | None:
    """One JSON-mode call; None on any failure (callers fall back to heuristics).

    `thinking_budget=0` is load-bearing, not an optimisation. MODEL is a *thinking*
    model, and reasoning tokens are billed against `max_output_tokens`: an 8-image
    `pick_hero_image` call spent 1067 tokens thinking and had ~130 left for the
    answer, so the JSON array was truncated mid-element, `json.loads` raised, and
    this function returned None — which callers read as "grounding unavailable".
    Grounded selection therefore looked broken while the model was actually scoring
    the images correctly (95/90/90/90 on the run that exposed this). These are
    perception/scoring calls with a fixed output shape; they do not need a reasoning
    budget, and disabling it is also cheaper and faster. The raised ceiling is a
    second belt: enough room for scores over the full candidate set.
    """
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=parts,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": max_output_tokens,
                "thinking_config": {"thinking_budget": 0},
            },
        )
        text = (response.text or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        start, end = text.find("["), text.rfind("]")
        if start == -1:
            start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def _clamp_score(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def _robot_blurb(name: str, model_name: str, company_name: str, description: str) -> str:
    blurb = f'Robot: "{name}"'
    if model_name and model_name != name:
        blurb += f" (model {model_name})"
    if company_name:
        blurb += f' by "{company_name}"'
    if description:
        blurb += f"\nDescription: {description[:1200]}"
    return blurb


def pick_hero_image(
    client,
    session,
    *,
    name: str,
    model_name: str = "",
    company_name: str = "",
    description: str = "",
    candidates: list[str],
    max_gallery: int = 5,
    timeout: int = 15,
) -> dict[str, Any] | None:
    """Visually score candidate image URLs and pick hero + gallery.

    Returns {"hero": url|"", "gallery": [urls], "scores": {url: score}} or None
    when grounding couldn't run (no client, no downloadable images, API failure).
    A returned dict with hero="" means the model looked and REJECTED everything —
    callers should treat that as "no confident image", not fall back.
    """
    if client is None or not candidates:
        return None

    # Deferred import: verify_lib puts robotaigeek-server on sys.path at import time.
    from verify_lib import server_verification

    loaded: list[tuple[str, tuple[bytes, str]]] = []
    for url in dict.fromkeys(candidates):
        if len(loaded) >= MAX_IMAGE_CANDIDATES:
            break
        payload = server_verification.fetch_image_bytes(session, url, timeout=timeout)
        if payload:
            loaded.append((url, payload))
    if not loaded:
        return None

    from google.genai import types

    parts: list = [
        "You are selecting product photos for a robotics directory.\n"
        + _robot_blurb(name, model_name, company_name, description)
        + "\n\nScore each numbered image 0-100 for whether it clearly shows THIS robot "
        "(100 = definitely this robot, 0 = definitely not). Logos, banners, icons, team "
        "photos, diagrams, and DIFFERENT robot models score under 30. Respond with ONLY a "
        'JSON array: [{"index": <int>, "score": <int>, "reason": "<max 15 words>"}, ...]'
    ]
    for i, (_url, (data, mime)) in enumerate(loaded, 1):
        parts.append(f"IMAGE {i}:")
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))

    raw = _generate_json(client, parts)
    if not isinstance(raw, list):
        return None

    scores: dict[str, int] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        score = _clamp_score(item.get("score"))
        if isinstance(idx, int) and 1 <= idx <= len(loaded) and score is not None:
            scores[loaded[idx - 1][0]] = score

    if not scores:
        return None

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    passing = [url for url, score in ranked if score >= MATCH_THRESHOLD]
    return {
        "hero": passing[0] if passing else "",
        "gallery": passing[1:1 + max_gallery],
        "scores": scores,
        # The bytes were downloaded for scoring anyway — hash them here for free
        # so callers can stamp ImageCandidate.content_hash and the server's
        # hash-first photo dedupe (image_candidates._find_existing_photo) can
        # actually fire at attach time. md5 = detect_duplicate_heroes convention.
        "hashes": {url: hashlib.md5(data).hexdigest() for url, (data, _mime) in loaded},
    }


def confirm_product_url(
    client,
    *,
    name: str,
    model_name: str = "",
    company_name: str = "",
    page_url: str,
    page_title: str = "",
    page_text: str = "",
) -> tuple[int, str] | None:
    """Score whether an already-fetched page is this robot's own product page.
    Returns (score, reason) or None when grounding couldn't run."""
    if client is None or not (page_text or page_title):
        return None

    prompt = (
        _robot_blurb(name, model_name, company_name, "")
        + f"\n\nPage URL: {page_url}\nPage title: {page_title or '(none)'}\n"
        f"Page text (extract): {page_text[:6000]}\n\n"
        "Score 0-100 whether this page is the DEDICATED product page for exactly this robot "
        "model. A company homepage, product catalog/listing, news article, blog post, or a "
        "different model's page scores under 40. Respond with ONLY JSON: "
        '{"score": <int>, "reason": "<max 20 words>"}'
    )
    raw = _generate_json(client, [prompt], max_output_tokens=200)
    if not isinstance(raw, dict):
        return None
    score = _clamp_score(raw.get("score"))
    if score is None:
        return None
    return score, str(raw.get("reason") or "")[:200]


def filter_videos(
    client,
    *,
    name: str,
    model_name: str = "",
    company_name: str = "",
    videos: list[dict],
    max_count: int = 3,
) -> list[dict] | None:
    """Score enriched video dicts (title/description/channel from youtube_metadata)
    and keep the ones that belong to this robot. Returns the filtered list, or None
    when grounding couldn't run. An empty list is a real answer: nothing matched."""
    if client is None or not videos:
        return None

    lines = []
    for i, video in enumerate(videos, 1):
        lines.append(
            f"VIDEO {i}: url={video.get('url', '')} | title={video.get('title', '')} | "
            f"channel={video.get('channel') or video.get('author') or ''} | "
            f"description={str(video.get('description') or '')[:200]}"
        )
    prompt = (
        _robot_blurb(name, model_name, company_name, "")
        + "\n\nScore each video 0-100 for whether it is about THIS specific robot (demo, "
        "launch, review, or the manufacturer showing this model). Generic company intros, "
        "other models, and unrelated content score under 40.\n\n"
        + "\n".join(lines)
        + '\n\nRespond with ONLY a JSON array: [{"index": <int>, "score": <int>}, ...]'
    )
    raw = _generate_json(client, [prompt])
    if not isinstance(raw, list):
        return None

    scored: list[tuple[int, dict]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        score = _clamp_score(item.get("score"))
        if isinstance(idx, int) and 1 <= idx <= len(videos) and score is not None and score >= MATCH_THRESHOLD:
            scored.append((score, videos[idx - 1]))
    scored.sort(key=lambda kv: -kv[0])
    return [video for _score, video in scored[:max_count]]
