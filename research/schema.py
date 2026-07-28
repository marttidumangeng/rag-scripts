"""Staging JSON schemas for the robot research agent."""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Literal

ConfidenceLevel = Literal["high", "medium", "low"]


@dataclass
class SourceRef:
    url: str
    type: str = "website"
    title: str = ""

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {"url": self.url, "type": self.type}
        if self.title:
            d["title"] = self.title
        return d


@dataclass
class ImageCandidate:
    url: str
    source_page_url: str = ""
    source_tier: str = ""
    source_publisher: str = ""
    source_domain: str = ""
    media_class: str = ""
    image_scope: str = ""
    confidence_score: int | None = None
    confidence_breakdown: dict | None = None
    match_reason: str = ""
    rights_status: str = ""
    content_hash: str = ""
    retrieved_at: str = ""  # ISO8601 optional

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"url": self.url}
        for key in (
            "source_page_url",
            "source_tier",
            "source_publisher",
            "source_domain",
            "media_class",
            "image_scope",
            "match_reason",
            "rights_status",
            "content_hash",
            "retrieved_at",
        ):
            val = getattr(self, key)
            if val:
                d[key] = val
        if self.confidence_score is not None:
            d["confidence_score"] = self.confidence_score
        if self.confidence_breakdown is not None:
            d["confidence_breakdown"] = self.confidence_breakdown
        return d

    @classmethod
    def from_item(cls, item: Any) -> ImageCandidate | None:
        if isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            if not url:
                return None
            score = item.get("confidence_score")
            parsed_score: int | None = None
            if score not in (None, ""):
                try:
                    parsed_score = max(0, min(100, int(score)))
                except (TypeError, ValueError):
                    parsed_score = None
            breakdown = item.get("confidence_breakdown")
            if breakdown is not None and not isinstance(breakdown, dict):
                breakdown = None
            return cls(
                url=url,
                source_page_url=str(item.get("source_page_url") or "").strip(),
                source_tier=str(item.get("source_tier") or "").strip(),
                source_publisher=str(item.get("source_publisher") or "").strip(),
                source_domain=str(item.get("source_domain") or "").strip(),
                media_class=str(item.get("media_class") or "").strip(),
                image_scope=str(item.get("image_scope") or "").strip(),
                confidence_score=parsed_score,
                confidence_breakdown=breakdown,
                match_reason=str(item.get("match_reason") or "").strip(),
                rights_status=str(item.get("rights_status") or "").strip(),
                content_hash=str(item.get("content_hash") or "").strip(),
                retrieved_at=str(item.get("retrieved_at") or "").strip(),
            )
        url = str(item).strip()
        return cls(url=url) if url else None


def normalize_image_candidates(items: list[Any]) -> list[ImageCandidate]:
    """Coerce strings or dicts into ``ImageCandidate`` instances."""
    normalized: list[ImageCandidate] = []
    for item in items:
        if isinstance(item, ImageCandidate):
            normalized.append(item)
            continue
        candidate = ImageCandidate.from_item(item)
        if candidate:
            normalized.append(candidate)
    return normalized


_PRIMARY_ELIGIBLE_MEDIA = frozenset(
    {"product_photo", "official_render", "application_photo", "family_photo"}
)
_RIGHTS_STATUSES = frozenset(
    {"official_source", "permission_confirmed", "review_required", "restricted"}
)

_confidence_level_fn: Callable[[int], str] | None = None
_is_primary_eligible_fn: Callable[..., bool] | None = None


def _ensure_server_path() -> None:
    server_dir = Path(__file__).resolve().parents[2] / "robotaigeek-server"
    if server_dir.is_dir():
        server_path = str(server_dir)
        if server_path not in sys.path:
            sys.path.insert(0, server_path)


def _local_confidence_level(score: int | None) -> str:
    if score is None:
        return "medium"
    value = max(0, min(100, int(score)))
    if value >= 85:
        return "high"
    if value >= 70:
        return "medium"
    if value >= 50:
        return "low"
    return "reject"


def _local_is_primary_eligible(
    *,
    media_class: str,
    image_scope: str,
    rights_status: str,
    level: str,
) -> bool:
    """Conservative mirror of ``robots.image_confidence.is_primary_eligible``."""
    if level not in {"high", "medium"}:
        return False

    rights = (rights_status or "").strip().lower()
    if rights in {"review_required", "restricted"} or not rights or rights not in _RIGHTS_STATUSES:
        return False

    if media_class not in _PRIMARY_ELIGIBLE_MEDIA:
        return False
    if media_class == "application_photo" and image_scope != "exact_variant":
        return False
    if media_class == "family_photo" and image_scope != "family":
        return False
    return True


def _load_primary_eligibility_helpers() -> None:
    global _confidence_level_fn, _is_primary_eligible_fn
    if _confidence_level_fn is not None and _is_primary_eligible_fn is not None:
        return

    _ensure_server_path()
    try:
        from robots.image_confidence import confidence_level as server_confidence_level
        from robots.image_confidence import is_primary_eligible as server_is_primary_eligible

        _confidence_level_fn = server_confidence_level
        _is_primary_eligible_fn = server_is_primary_eligible
        return
    except ImportError:
        pass

    try:
        from image_confidence import confidence_level as shim_confidence_level
        from image_confidence import is_primary_eligible as shim_is_primary_eligible

        _confidence_level_fn = shim_confidence_level
        _is_primary_eligible_fn = shim_is_primary_eligible
        return
    except ImportError:
        pass

    _confidence_level_fn = lambda score: _local_confidence_level(score)  # noqa: E731
    _is_primary_eligible_fn = _local_is_primary_eligible


def _confidence_level(score: int | None) -> str:
    _load_primary_eligibility_helpers()
    assert _confidence_level_fn is not None
    return _confidence_level_fn(int(score or 0))


def _is_primary_eligible_candidate(candidate: ImageCandidate) -> bool:
    _load_primary_eligibility_helpers()
    assert _is_primary_eligible_fn is not None
    level = _confidence_level(candidate.confidence_score)
    return _is_primary_eligible_fn(
        media_class=candidate.media_class,
        image_scope=candidate.image_scope,
        rights_status=candidate.rights_status,
        level=level,
    )


def _best_hero_url(candidates: list[ImageCandidate]) -> str:
    """Highest-confidence primary-eligible URL, or empty when none qualify."""
    if not candidates:
        return ""
    ranked = sorted(
        candidates,
        key=lambda c: c.confidence_score if c.confidence_score is not None else -1,
        reverse=True,
    )
    for candidate in ranked:
        if _is_primary_eligible_candidate(candidate):
            return candidate.url
    return ""


@dataclass
class VideoRef:
    url: str
    title: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {"url": self.url}
        if self.title:
            d["title"] = self.title
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_item(cls, item: Any) -> VideoRef | None:
        if isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            if not url:
                return None
            return cls(
                url=url,
                title=str(item.get("title") or "").strip(),
                description=str(item.get("description") or "").strip(),
            )
        url = str(item).strip()
        return cls(url=url) if url else None


@dataclass
class StagedRobot:
    """One robot record produced by AI research before bulk-import."""

    name: str
    id: int | None = None
    company_slug: str = ""
    company_name: str = ""
    model_name: str = ""
    family_name: str = ""
    family_key: str = ""
    variant_code: str = ""
    variant_label: str = ""
    family_url: str = ""
    product_url_scope: str = ""
    manufacturer_country_code: str = ""
    manufacturer_country_codes: str = ""
    image: str = ""
    images: list[ImageCandidate] = field(default_factory=list)
    video_urls: list[VideoRef] = field(default_factory=list)
    url: str = ""
    description: str = ""
    purpose: str = ""
    features: str = ""
    strengths: str = ""
    weaknesses: str = ""
    notes: str = ""
    availability_status_key: str = ""
    movement_type_keys: str = ""
    industry_keys: str = ""
    industries_other: str = ""
    use_keys: str = ""
    uses_other: str = ""
    category_slugs: str = ""
    sub_category_slug: str = ""
    tags: str = ""
    release_year: int | None = None
    source_locale: str = "en"
    price_range: str = ""
    price_min: float | None = None
    price_max: float | None = None
    price_currency: str = ""
    price_notes: str = ""
    weight: str = ""
    weight_kg: float | None = None
    height: str = ""
    height_mm: float | None = None
    width: str = ""
    width_mm: float | None = None
    length: str = ""
    length_mm: float | None = None
    speed: float | None = None
    speed_ms: float | None = None
    walking_speed: float | None = None
    payload_kg: float | None = None
    reach_mm: float | None = None
    repeatability_mm: float | None = None
    ip_rating: str = ""
    operating_temp_min_c: str = ""
    operating_temp_max_c: str = ""
    dimensions_mm: str = ""
    dof: int | None = None
    manipulation: str = ""
    battery_capacity: str = ""
    battery_wh: float | None = None
    voltage: str = ""
    runtime: str = ""
    runtime_minutes: int | None = None
    charging_type: str = ""
    charging_time: str = ""
    charging_time_minutes: int | None = None
    joint_torque: str = ""
    joint_torque_nm: float | None = None
    torque_density: str = ""
    torque_density_nm_per_kg: float | None = None
    actuation_mechanism: str = ""
    computation: str = ""
    connectivity: str = ""
    software: str = ""
    movement_engine: str = ""
    environment: str = ""
    sensors: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    confidence: dict[str, ConfidenceLevel] = field(default_factory=dict)
    research_notes: str = ""
    # Company enrichment (optional, applied during bulk-import)
    company_website: str = ""
    company_hq_country_code: str = ""
    company_description: str = ""
    # Narrative fields for the extended (long-form) description; blank when not stated.
    programming_interface: str = ""
    safety_fencing: str = ""
    mounting_options: str = ""
    deployment_context: str = ""
    ecosystem_compatibility: str = ""

    def __post_init__(self) -> None:
        # Coerce the narrative fields to plain strings (from_dict may pass None).
        for _narr in ("programming_interface", "safety_fencing", "mounting_options",
                      "deployment_context", "ecosystem_compatibility"):
            if not isinstance(getattr(self, _narr), str):
                setattr(self, _narr, "")
        self.images = normalize_image_candidates(self.images)
        if not self.image and self.images:
            self.image = _best_hero_url(self.images)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StagedRobot:
        sources_raw = data.get("sources") or []
        sources: list[SourceRef] = []
        for item in sources_raw:
            if isinstance(item, str):
                sources.append(SourceRef(url=item))
            elif isinstance(item, dict) and item.get("url"):
                sources.append(SourceRef(
                    url=str(item["url"]),
                    type=str(item.get("type") or "website"),
                    title=str(item.get("title") or ""),
                ))

        sensors = data.get("sensors") or []
        if isinstance(sensors, str):
            sensors = [s.strip() for s in sensors.replace("|", ",").split(",") if s.strip()]

        materials = data.get("materials") or []
        if isinstance(materials, str):
            materials = [m.strip() for m in materials.replace("|", ",").split(",") if m.strip()]

        images_raw = data.get("images") or []
        if isinstance(images_raw, str):
            images_raw = [u.strip() for u in images_raw.replace("|", ",").split(",") if u.strip()]
        images = normalize_image_candidates(list(images_raw))

        image = str(data.get("image") or "").strip()

        videos_raw = data.get("video_urls") or []
        if isinstance(videos_raw, str):
            videos_raw = [u.strip() for u in videos_raw.replace("|", ",").split(",") if u.strip()]
        video_urls: list[VideoRef] = []
        for item in videos_raw:
            ref = VideoRef.from_item(item)
            if ref:
                video_urls.append(ref)

        field_names = {f.name for f in fields(cls)}
        skip = {"sources", "sensors", "materials", "confidence", "images", "video_urls", "image"}
        kwargs = {k: v for k, v in data.items() if k in field_names and k not in skip}
        return cls(
            sources=sources,
            sensors=list(sensors),
            materials=list(materials),
            images=images,
            image=image,
            video_urls=video_urls,
            confidence=dict(data.get("confidence") or {}),
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sources"] = [s.to_dict() for s in self.sources]
        d["images"] = [c.to_dict() for c in self.images]
        d["video_urls"] = [v.to_dict() for v in self.video_urls]
        return d


@dataclass
class StagedCompany:
    """Company patch record for backfill."""

    name: str
    id: int | None = None
    slug: str = ""
    description: str = ""
    website: str = ""
    hq_address: str = ""
    country_code: str = ""
    country_id: int | None = None
    contact_info: str = ""
    leaders_roles: str = ""
    employee_count: str = ""
    employee_min: int | None = None
    employee_max: int | None = None
    notes: str = ""
    company_status: str = ""
    product_stage: str = ""
    company_maturity: str = ""
    product_type: str = ""
    primary_focus: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    research_notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StagedCompany:
        sources_raw = data.get("sources") or []
        sources: list[SourceRef] = []
        for item in sources_raw:
            if isinstance(item, str):
                sources.append(SourceRef(url=item))
            elif isinstance(item, dict) and item.get("url"):
                sources.append(SourceRef(
                    url=str(item["url"]),
                    type=str(item.get("type") or "website"),
                    title=str(item.get("title") or ""),
                ))
        field_names = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in field_names and k not in ("sources", "primary_focus")}
        primary_focus = data.get("primary_focus") or []
        if isinstance(primary_focus, str):
            primary_focus = [p.strip() for p in primary_focus.replace("|", ",").split(",") if p.strip()]
        return cls(sources=sources, primary_focus=list(primary_focus), **kwargs)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sources"] = [s.to_dict() for s in self.sources]
        return d


@dataclass
class ProcessedIds:
    companies: list[int] = field(default_factory=list)
    robots: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ProcessedIds:
        if not data:
            return cls()
        return cls(
            companies=[int(x) for x in data.get("companies", [])],
            robots=[int(x) for x in data.get("robots", [])],
        )

    def to_dict(self) -> dict[str, list[int]]:
        return {"companies": self.companies, "robots": self.robots}

    def exclude_ids_param(self, entity: Literal["company", "robot"]) -> str:
        ids = self.companies if entity == "company" else self.robots
        return ",".join(str(i) for i in ids)
