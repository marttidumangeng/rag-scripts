"""Core types for the remedy library.

A *remedy* is a deterministic fix for ONE quality flag. Every remedy shares the
signature ``remedy(robot: dict, ctx: RemedyContext) -> RemedyResult`` so the
rejection/QA loop can look one up by flag key and run it without special-casing.

The important guarantee here is the **no-op detector**: a remedy compares the
fields it is allowed to touch before and after re-research and reports
``NO_OP`` when nothing actually changed — *before* writing anything. That is what
stops the loop from burning repeated enrichment passes on a robot whose problem
the pipeline cannot currently solve (the failure mode that made every previous
fix attempt a hand-written one-off script).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Allow `import remedies...` to work when the package is imported from anywhere:
# every sibling module (api_client, robot_auto_research, ...) lives one level up.
_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------
FIXED = "fixed"        # fields actually changed and were written
NO_OP = "no_op"        # research produced nothing new -> do NOT retry this action
FAILED = "failed"      # the attempt errored (network, target_not_found, import error)
SKIPPED = "skipped"    # precondition not met (e.g. company has no website)
TERMINAL = "terminal"  # robot must not be enriched at all (not_real / duplicate)

RETRYABLE_OUTCOMES = {FAILED}
"""Only hard failures are worth a second attempt; NO_OP never is."""


@dataclass
class RemedyResult:
    """Outcome of a single remedy run — also the row appended to the
    ``Robot.auto_fix_attempts`` ledger."""

    action: str
    outcome: str
    flag: str = ""
    changed_fields: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def changed(self) -> bool:
        return self.outcome == FIXED and bool(self.changed_fields)

    def to_attempt(self) -> dict[str, Any]:
        """Serialize for the server-side attempt ledger."""
        return {
            "at": datetime.now(timezone.utc).isoformat(),
            "flag": self.flag,
            "action": self.action,
            "outcome": self.outcome,
            "changed_fields": list(self.changed_fields),
            "detail": self.detail[:500],
        }


@dataclass
class RemedyContext:
    """Everything a remedy needs that is not the robot itself.

    Built once per company so a batch of robots reuses one researcher/client.
    """

    company_id: int
    company_name: str = ""
    company_slug: str = ""
    company_website: str = ""
    country_code: str = ""
    client: Any = None                 # ResearchApiClient
    researcher: Any = None             # RobotAutoResearcher
    evidence: Any = None               # EvidenceStore | None
    staging_dir: Path | None = None
    created_by_id: int | None = None
    dry_run: bool = True
    status: str = "pending_review"

    hints: dict[int, dict[str, Any]] = field(default_factory=dict)
    """robot_id -> hand-verified field overrides, loaded from
    remedies/hints/<company_id>.json when present. See hints/README.md."""

    _vision_researcher: Any = None
    _hints_loaded: bool = False

    _country_lookup: Any = None
    """Memo for `remedy_missing_manufacturer_country`: `(code, how)` or None.

    HQ country is a property of the COMPANY, and this context is built once per
    company, so the web lookup must happen once — not once per robot. Without
    this a 40-robot company with a blank country row would make 40 identical
    serper/Gemini calls, and 40 in dry-run mode where nothing is ever written
    back to short-circuit them."""

    def get_researcher(self, *, vision: bool = False) -> Any:
        """Researcher for this remedy.

        Most remedies stay deterministic (grounded=False) — cheaper and reproducible.
        Media remedies ask for `vision=True`, because on OEMs that serve CMS/date/hash
        image filenames there is no textual signal to match and looking at the pixels
        is the only way to identify the photo. Cached so a batch pays one client setup.
        """
        if not vision:
            return self.researcher
        if self._vision_researcher is None:
            from robot_auto_research import RobotAutoResearcher
            self._vision_researcher = RobotAutoResearcher(grounded=True)
        return self._vision_researcher

    def ensure(self) -> "RemedyContext":
        """Lazily build the client/researcher/staging dir (keeps imports cheap
        for callers that only want the registry)."""
        if self.client is None:
            from api_client import ResearchApiClient
            self.client = ResearchApiClient()
        if self.researcher is None:
            from robot_auto_research import RobotAutoResearcher
            # grounded=False by default: remedies are deterministic first.
            self.researcher = RobotAutoResearcher(grounded=False)
        if self.staging_dir is None:
            self.staging_dir = _RESEARCH_DIR / "staging" / "robots" / (self.company_slug or "unknown") / "remedies"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        if not self._hints_loaded:
            self.hints = _load_hints(self.company_id) if self.company_id else {}
            self._hints_loaded = True
        return self

    def hint_for(self, robot_id: int) -> dict[str, Any] | None:
        """Hand-verified field overrides for this robot, if a hints file supplied any."""
        return self.hints.get(int(robot_id))


_HINTS_DIR = _RESEARCH_DIR / "remedies" / "hints"


def _load_hints(company_id: int) -> dict[int, dict[str, Any]]:
    """Load remedies/hints/<company_id>.json — hand-verified per-robot field
    overrides for companies where automated discovery underperforms (wrong nav,
    attribution landmines, non-standard taxonomy). Absent file = no hints, zero
    behavior change. See hints/README.md for the format.
    """
    path = _HINTS_DIR / f"{company_id}.json"
    if not path.exists():
        return {}
    import json
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[int, dict[str, Any]] = {}
    for key, val in (raw or {}).items():
        try:
            rid = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(val, dict):
            out[rid] = {k: v for k, v in val.items() if not k.startswith("_")}
    return out


RemedyFn = Callable[[dict, RemedyContext], RemedyResult]


# ---------------------------------------------------------------------------
# Field comparison (the no-op detector)
# ---------------------------------------------------------------------------

def _norm_scalar(val: Any) -> Any:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return val


def _norm_media(val: Any) -> Any:
    """Normalize image/video collections to a comparable, order-insensitive shape."""
    if not val:
        return ()
    out: list[str] = []
    for item in val if isinstance(val, (list, tuple)) else [val]:
        if isinstance(item, dict):
            out.append(str(item.get("url") or item.get("image") or "").strip())
        elif hasattr(item, "to_dict"):
            d = item.to_dict()
            out.append(str(d.get("url") or "").strip())
        else:
            out.append(str(item).strip())
    return tuple(sorted(u for u in out if u))


_MEDIA_FIELDS = {"images", "video_urls", "sources", "sensors", "materials"}


def normalize_field(name: str, val: Any) -> Any:
    return _norm_media(val) if name in _MEDIA_FIELDS else _norm_scalar(val)


def snapshot(payload: dict[str, Any], fields: list[str] | frozenset[str]) -> dict[str, Any]:
    """Comparable snapshot of just the fields a remedy is allowed to touch."""
    return {f: normalize_field(f, payload.get(f)) for f in fields}


def diff_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Names of fields whose normalized value actually changed."""
    return sorted(k for k in after if before.get(k) != after.get(k))
