"""Parse citation URLs out of a robot's `url` + `notes` and sync them into
RobotInformationSource via the existing `information_source_urls` write field
on the robot API (no server deploy needed — that field already exists).

The enrichment pipeline doesn't track structured per-field provenance yet;
`notes` is the only place citations currently live (free text, e.g.
"Sources: url1 | url2" and "release_year=YYYY: \"quoted text\" (url)").
This module extracts what it can from that text as an interim reference
trail while research/discovery is still in flight.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

_SOURCES_LINE_RE = re.compile(r"Sources:\s*(.+?)(?:\n|$)")
_RELEASE_YEAR_RE = re.compile(
    r"release_year=(\d{4}):\s*(.*?)\s*\((https?://[^\s)]+)\)", re.DOTALL
)
_URL_RE = re.compile(r"https?://[^\s|]+")


def _source_type_for(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "video"
    if "github.com" in host:
        return "github"
    if any(k in host for k in ("news", "techcrunch", "roboticstomorrow", "ieee")):
        return "news"
    return "website"


def parse_citations(url: str, notes: str) -> list[dict[str, Any]]:
    """Best-effort extraction of citation entries from a robot's url/notes.

    Returns a deduplicated (by url) list of
    {url, source_type, title, description} dicts.
    """
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(u: str, source_type: str, title: str, description: str = "") -> None:
        u = (u or "").strip().rstrip(".,)")
        if not u or not u.startswith("http") or u in seen:
            return
        seen.add(u)
        entries.append({"url": u, "source_type": source_type, "title": title, "description": description})

    if url:
        add(url, _source_type_for(url), "Product page")

    notes = notes or ""

    for match in _SOURCES_LINE_RE.finditer(notes):
        for u in _URL_RE.findall(match.group(1)):
            add(u, _source_type_for(u), "Source")

    for year, quote, cite_url in _RELEASE_YEAR_RE.findall(notes):
        add(cite_url, _source_type_for(cite_url), f"Release year ({year}) citation", quote.strip())

    return entries


def sync_information_sources(client: Any, robot_id: int) -> list[dict[str, Any]] | None:
    """Fetch a robot, parse citations from its url/notes, merge them with any
    information_sources it already has (dedup by url), and PATCH the merged
    list back. Returns the merged list, or None if there was nothing to add.

    `information_source_urls` is a full-replace field server-side, so existing
    sources are read back and included rather than clobbered.
    """
    robot = client._get(f"robots/robots/{robot_id}/")
    parsed = parse_citations(robot.get("url") or "", robot.get("notes") or "")
    if not parsed:
        return None

    existing = robot.get("information_sources") or []
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in existing + parsed:
        u = (entry.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        merged.append({
            "url": u,
            "source_type": entry.get("source_type") or "website",
            "title": entry.get("title") or "",
            "description": entry.get("description") or "",
        })

    if len(merged) == len(existing) and all(
        m["url"] == e.get("url") for m, e in zip(merged, existing)
    ):
        return None  # nothing new

    client._patch(f"robots/robots/{robot_id}/", {"information_source_urls": merged})
    return merged


def dedupe_ai_research_prefix(notes: str) -> str:
    """Collapse a notes string where the "[AI Research]" boilerplate prefix
    got duplicated across repeated enrichment runs (e.g. "[AI Research]
    [AI Research] [AI Research] Auto-researched...") down to one occurrence.
    Returns the notes unchanged if there's nothing to collapse.
    """
    if not notes or notes.count("[AI Research]") <= 1:
        return notes
    collapsed = re.sub(r"(\[AI Research\]\s*)+", "[AI Research] ", notes)
    return collapsed.strip()
