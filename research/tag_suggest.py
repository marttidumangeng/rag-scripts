"""Suggest robot tags from existing platform Tag records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from api_client import ResearchApiClient

# Extra keyword hints → prefer these tag slugs/names when present in catalog
_KEYWORD_HINTS: dict[str, tuple[str, ...]] = {
    "amr": ("amr", "mobile robot", "autonomous mobile"),
    "agv": ("agv", "guided vehicle"),
    "warehouse": ("warehouse", "fulfillment", "logistics", "distribution"),
    "manufacturing": ("manufacturing", "factory", "industrial"),
    "wheeled": ("wheeled", "mobile"),
    "legged": ("legged", "quadruped", "biped", "humanoid"),
    "collaborative": ("cobot", "collaborative"),
    "surgical": ("surgical", "medical", "healthcare"),
    "delivery": ("delivery", "last mile"),
    "inspection": ("inspection", "surveillance"),
    "research": ("research", "education"),
}


@dataclass
class TagCatalog:
    tags: list[dict[str, Any]] = field(default_factory=list)
    _by_slug: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _by_name: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        for tag in self.tags:
            slug = str(tag.get("slug") or "").lower()
            name = str(tag.get("name") or "").lower()
            if slug:
                self._by_slug[slug] = tag
            if name:
                self._by_name[name] = tag

    @classmethod
    def load(cls, client: ResearchApiClient | None = None, *, page_size: int = 200) -> TagCatalog:
        client = client or ResearchApiClient()
        tags = client.list_tags(page_size=page_size)
        return cls(tags=tags)

    def suggest(
        self,
        *,
        name: str = "",
        description: str = "",
        purpose: str = "",
        features: str = "",
        movement_type_keys: str = "",
        industry_keys: str = "",
        use_keys: str = "",
        sub_category_slug: str = "",
        max_tags: int = 8,
    ) -> list[str]:
        """Return tag *names* from the catalog that best match robot text."""
        blob = " ".join([
            name, description, purpose, features,
            movement_type_keys.replace("|", " "),
            industry_keys.replace("|", " "),
            use_keys.replace("|", " "),
            sub_category_slug.replace("-", " "),
        ]).lower()

        scores: dict[str, float] = {}

        for tag in self.tags:
            tag_name = str(tag.get("name") or "")
            tag_slug = str(tag.get("slug") or "")
            if not tag_name:
                continue
            score = 0.0
            name_l = tag_name.lower()
            slug_l = tag_slug.lower()
            # Whole-word / slug match in blob
            if slug_l and slug_l.replace("-", " ") in blob:
                score += 12
            if name_l in blob:
                score += 10
            for part in re.split(r"[^a-z0-9]+", name_l):
                if len(part) >= 3 and part in blob:
                    score += 4
            robots_count = tag.get("robots_count") or 0
            if robots_count:
                score += min(float(robots_count), 20) * 0.05
            if score > 0:
                scores[tag_name] = score

        # Keyword hint boost for known catalog tags
        for hint_key, phrases in _KEYWORD_HINTS.items():
            if not any(p in blob for p in phrases):
                continue
            for tag in self.tags:
                tag_name = str(tag.get("name") or "")
                slug_l = str(tag.get("slug") or "").lower()
                name_l = tag_name.lower()
                if hint_key in slug_l or hint_key in name_l or hint_key in blob:
                    scores[tag_name] = scores.get(tag_name, 0) + 6

        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0].lower()))
        return [name for name, _ in ranked[:max_tags]]


def suggest_robot_tags(
    robot: dict[str, Any] | Any,
    catalog: TagCatalog | None = None,
    *,
    client: ResearchApiClient | None = None,
    max_tags: int = 8,
) -> str:
    """Return pipe-separated tag names for bulk-import `tags` field."""
    catalog = catalog or TagCatalog.load(client=client)
    if isinstance(robot, dict):
        kwargs = {
            "name": robot.get("name") or "",
            "description": robot.get("description") or "",
            "purpose": robot.get("purpose") or "",
            "features": robot.get("features") or "",
            "movement_type_keys": robot.get("movement_type_keys") or "",
            "industry_keys": robot.get("industry_keys") or "",
            "use_keys": robot.get("use_keys") or "",
            "sub_category_slug": robot.get("sub_category_slug") or "",
        }
    else:
        kwargs = {
            "name": getattr(robot, "name", "") or "",
            "description": getattr(robot, "description", "") or "",
            "purpose": getattr(robot, "purpose", "") or "",
            "features": getattr(robot, "features", "") or "",
            "movement_type_keys": getattr(robot, "movement_type_keys", "") or "",
            "industry_keys": getattr(robot, "industry_keys", "") or "",
            "use_keys": getattr(robot, "use_keys", "") or "",
            "sub_category_slug": getattr(robot, "sub_category_slug", "") or "",
        }
    names = catalog.suggest(**kwargs, max_tags=max_tags)
    return "|".join(names)
