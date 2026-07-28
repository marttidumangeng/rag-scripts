"""Fetch YouTube video title/description (no API key required)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

import requests

_OEMBED = "https://www.youtube.com/oembed"
_SHORT_DESC_RE = re.compile(r'"shortDescription"\s*:\s*"((?:\\.|[^"\\])*)"')
_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{11})",
    re.I,
)


def extract_youtube_video_id(url: str) -> str | None:
    m = _VIDEO_ID_RE.search(url or "")
    return m.group(1) if m else None


def fetch_youtube_metadata(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = 20,
) -> dict[str, str]:
    """
    Return {url, title, description} for a YouTube watch URL.
    Title via oEmbed; description from embedded player JSON or meta tag.
    """
    url = (url or "").strip()
    result = {"url": url, "title": "", "description": ""}
    if not url:
        return result

    sess = session or requests.Session()
    sess.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (compatible; RobotAIGeek-ResearchAgent/1.0)",
    )

    try:
        resp = sess.get(
            _OEMBED,
            params={"url": url, "format": "json"},
            timeout=timeout,
        )
        if resp.ok:
            data = resp.json()
            result["title"] = str(data.get("title") or "").strip()
    except (requests.RequestException, ValueError):
        pass

    vid = extract_youtube_video_id(url)
    watch_url = f"https://www.youtube.com/watch?v={vid}" if vid else url
    try:
        page = sess.get(watch_url, timeout=timeout)
        if page.ok:
            desc = _parse_description_from_watch_html(page.text)
            if desc:
                result["description"] = desc
    except requests.RequestException:
        pass

    return result


def _parse_description_from_watch_html(html: str) -> str:
    if not html:
        return ""
    m = _SHORT_DESC_RE.search(html)
    if m:
        try:
            return json.loads(f'"{m.group(1)}"').strip()
        except json.JSONDecodeError:
            return m.group(1).replace("\\n", "\n").strip()
    for pat in (
        r'<meta\s+name="description"\s+content="([^"]+)"',
        r'<meta\s+property="og:description"\s+content="([^"]+)"',
    ):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return ""


# Titles that mean the clip is software/training, not the physical robot.
_REJECT_TITLE_RE = re.compile(
    r"(?i)\b("
    r"drastudio|project\s+management|power\s+quality|"
    r"servo\s+press|screwdriver|compact\s+drive|"
    r"quick\s+start|online\s+training|frames?\s+and\s+singularity"
    r")\b"
)

# Hex digests / UUIDs / opaque ids used as the start of a "title" (common on
# poorly titled OEM shorts that paste a file hash or asset id).
_HASHY_TITLE_RE = re.compile(
    r"(?i)^\s*("
    r"[0-9a-f]{32}"  # md5
    r"|[0-9a-f]{40}"  # sha1
    r"|[0-9a-f]{64}"  # sha256
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # uuid
    r"|0x[0-9a-f]{20,}"  # wallet-ish
    r"|wechat\s+\d{8,}"  # WeChat export filenames used as titles
    r")\b"
)


def is_reject_robot_video_title(title: str) -> bool:
    """True if oEmbed/title is unusable or clearly not a product/demo robot video.

    Rejects:
    - empty titles (private / unavailable)
    - known software/training title patterns
    - titles that open with a hex hash / UUID / wallet-like id
    - titles that are mostly hashtags with no readable product words
    """
    t = (title or "").strip()
    if not t:
        return True  # private / unavailable often returns empty title
    if _REJECT_TITLE_RE.search(t):
        return True
    if _HASHY_TITLE_RE.search(t):
        return True
    # Strip hashtags / mentions; if almost nothing readable remains, reject.
    without_tags = re.sub(r"(?i)[#@][\w\u4e00-\u9fff.]+", " ", t)
    without_tags = re.sub(r"\s+", " ", without_tags).strip(" -_|")
    if len(without_tags) < 8 and t.count("#") >= 3:
        return True
    # Mostly punctuation/hashtags by character share
    alnum = sum(1 for ch in t if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"))
    if alnum and t.count("#") >= 5 and alnum < 12:
        return True
    return False


def enrich_video_list(
    video_urls: list[Any],
    *,
    session: requests.Session | None = None,
    skip_rejected: bool = True,
) -> list[dict[str, str]]:
    """Convert URL strings to {url, title, description} dicts with metadata.

    When skip_rejected=True (default), drops YouTube URLs with empty titles
    (often private) or software/training titles that are not robot demos.
    """
    sess = session or requests.Session()
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in video_urls:
        if isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            description = str(item.get("description") or "").strip()
        else:
            url = str(item).strip()
            title = ""
            description = ""
        if not url or url in seen:
            continue
        seen.add(url)
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            if not title or not description:
                meta = fetch_youtube_metadata(url, session=sess)
                title = title or meta.get("title", "")
                description = description or meta.get("description", "")
            if skip_rejected and is_reject_robot_video_title(title):
                continue
        entry: dict[str, str] = {"url": url}
        if title:
            entry["title"] = title[:255]
        if description:
            entry["description"] = description[:2000]
        out.append(entry)
    return out
