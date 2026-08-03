"""Bridge to the server's AI-verification module for research-side use.

The server's `robots/verification.py` (and its only internal dependency,
`robots/quality.py`) are deliberately Django-free, so the research scripts can
reuse the exact same grounded-scoring mechanics — page fetch, image grounding,
video metadata checks, dimension weights, composite confidence — that the
`verify_content` management command uses post-import. One implementation, one
notion of "does this belong to this robot", on both sides of the import.

This module owns the sys.path plumbing plus the adapters that make a
`StagedRobot` (research staging JSON) look like a Robot row to `verify_robot`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVER_DIR = _REPO_ROOT / "robotaigeek-server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

# Django-free by design (see module docstrings) — safe to import without settings.
from robots import quality as server_quality  # noqa: E402
from robots import verification as server_verification  # noqa: E402

DEFAULT_MODEL = server_verification.DEFAULT_MODEL


def gemini_client():
    """genai.Client for verification calls, or None when GEMINI_API_KEY is unset
    (callers fall back to heuristics — grounding is an upgrade, never a requirement)."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    from google import genai

    # SDK-default API version (v1beta): the stable v1 endpoint rejects
    # response_mime_type, which JSON-mode verification calls need.
    # Metered: every generate_content charges the daily budget (spend_guard.py).
    import spend_guard
    return spend_guard.client(api_key=api_key)


class _CompanyShim:
    def __init__(self, name: str, website: str):
        self.name = name
        self.website = website


class _PhotoShim:
    def __init__(self, photo_id: int, url: str, is_primary: bool = False):
        self.id = photo_id
        self.url = url
        self.s3_image = None
        self.is_primary = is_primary


class _VideoShim:
    def __init__(self, video_id: int, url: str, title: str = ""):
        self.id = video_id
        self.url = url
        self.title = title


class StagedRobotAdapter:
    """Duck-types a StagedRobot as the robot-like object `verify_robot` expects."""

    def __init__(self, staged: Any, *, company_name: str = "", company_website: str = ""):
        self.name = staged.name or ""
        self.model_name = getattr(staged, "model_name", "") or ""
        self.description = getattr(staged, "description", "") or ""
        self.purpose = getattr(staged, "purpose", "") or ""
        self.features = getattr(staged, "features", "") or ""
        self.url = getattr(staged, "url", "") or ""
        self.url_verified_at = None
        self.image = getattr(staged, "image", "") or ""
        self.s3_image = None
        company_name = company_name or getattr(staged, "company_name", "") or ""
        self.company_ref = _CompanyShim(company_name, company_website) if company_name else None
        self.company_ref_id = 1 if self.company_ref else None

        gallery = [
            u for u in (
                (getattr(c, "url", None) if hasattr(c, "url") else c)
                for c in (getattr(staged, "images", None) or [])
            )
            if u and u != self.image
        ]
        self.photos = [_PhotoShim(i + 1, url, is_primary=(i == 0 and not self.image)) for i, url in enumerate(gallery)]

        self.videos = []
        for i, ref in enumerate(getattr(staged, "video_urls", None) or []):
            url = getattr(ref, "url", None) if hasattr(ref, "url") else (ref.get("url") if isinstance(ref, dict) else str(ref))
            title = getattr(ref, "title", "") if hasattr(ref, "title") else (ref.get("title", "") if isinstance(ref, dict) else "")
            if url:
                self.videos.append(_VideoShim(i + 1, url, title))


def verify_staged_robot(
    staged: Any,
    *,
    client,
    session,
    company_name: str = "",
    company_website: str = "",
    model: str = DEFAULT_MODEL,
    timeout: int = 15,
    page_snapshot: Any | None = None,
    evidence_ref: str = "",
) -> dict:
    """Run the server's full verification against one StagedRobot.
    Returns the same verification dict shape `verify_content` stores on Robot rows.
    Raises server_verification.VerificationError when the model call fails.

    Pass `page_snapshot` (server_verification.PageContent) + `evidence_ref` to
    verify against saved evidence text. Snapshot mode is labeled and does not
    treat URL reachability as a successful live fetch.
    """
    adapter = StagedRobotAdapter(staged, company_name=company_name, company_website=company_website)
    return server_verification.verify_robot(
        adapter,
        photos=adapter.photos,
        videos=adapter.videos,
        client=client,
        session=session,
        model=model,
        timeout=timeout,
        page_snapshot=page_snapshot,
        evidence_ref=evidence_ref,
    )


def page_snapshot_from_evidence_text(
    *,
    title: str = "",
    text: str = "",
    status: int | None = None,
) -> Any:
    """Build a verification PageContent from lean evidence text (not a live fetch)."""
    return server_verification.PageContent(
        fetched=True,
        status=status,
        title=title or "",
        text=text or "",
        image_urls=[],
        detail="evidence snapshot",
    )


def verification_flags(verification: dict) -> list[dict]:
    """Same chip flags the admin queue shows, computed research-side."""
    return server_quality.verification_quality_flags(verification)
