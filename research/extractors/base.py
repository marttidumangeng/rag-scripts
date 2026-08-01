"""Core types for structured catalogue extraction.

`ExtractedProduct` is deliberately NOT `schema.StagedRobot`. Extraction should
report what a source actually says; mapping that onto our catalogue's taxonomy
(categories, availability keys, family keys) is a separate concern with its own
failure modes. Keeping them apart means a strategy can be unit-tested against a
captured payload without knowing anything about our DB.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Protocol
from urllib.parse import urlparse


def domain_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").replace("www.", "").lower()
    except ValueError:
        return ""


def to_number(value: Any) -> float | None:
    """Parse a leading numeric quantity: '1,425 mm' -> 1425.0, '5G' -> 5.0.

    Callers must NOT use this on a field whose meaning they have not confirmed
    — '5G' parses to 5.0 perfectly happily, which is how a glass-generation
    rating became "5 mm of reach". Guard the field first (see SpecMapping),
    then parse.
    """
    if value is None:
        return None
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(value))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


@dataclass
class ExtractedProduct:
    """One product as the SOURCE describes it, before catalogue mapping."""

    name: str
    source_url: str
    # Legacy/alternate designation, where a manufacturer renames a line and
    # keeps the old code alongside (HD Hyundai: "HDR220-26(HS220)"). Carrying
    # this is what lets dedupe recognise that HS220 and HDR220-26 are one
    # machine rather than importing both.
    alias: str = ""
    product_type: str = ""          # source's own type label, verbatim
    payload_kg: float | None = None
    reach_mm: float | None = None
    dof: int | None = None
    drive: str = ""
    controllers: str = ""
    in_production: bool | None = None
    image_urls: list[str] = field(default_factory=list)
    # Anything typed the source gave us that has no first-class slot. Kept so a
    # mapper can use it and so nothing is silently discarded.
    extra: dict[str, Any] = field(default_factory=dict)
    # Which strategy produced this, for provenance in research_notes.
    via: str = ""

    def key(self) -> str:
        return re.sub(r"[^a-z0-9]", "", self.name.lower())

    def alias_key(self) -> str:
        return re.sub(r"[^a-z0-9]", "", self.alias.lower()) if self.alias else ""


@dataclass
class ExtractionResult:
    products: list[ExtractedProduct] = field(default_factory=list)
    strategy: str = ""
    notes: str = ""
    # Populated when a strategy declines rather than fails, so a caller can log
    # WHY the ladder fell through instead of seeing a silent empty list.
    declined_reason: str = ""

    def __bool__(self) -> bool:
        return bool(self.products)


@dataclass
class SpecMapping:
    """How one product type's spec slots map onto real measures.

    Exists because spec slots are not stable across a single manufacturer's own
    catalogue. On HD Hyundai's API, basic-spec slot 2 is reach in millimetres
    for industrial arms but the glass-generation rating for panel-transfer
    robots. A type-blind mapping produced "a maximum reach of 5 mm" from "5G".

    `applies_to` decides whether this mapping governs a given raw record, so a
    site with several product families declares one mapping per family rather
    than one mapping and a pile of special cases.
    """

    name: str
    applies_to: Callable[[dict[str, Any]], bool]
    payload_field: str | None = None
    reach_field: str | None = None
    dof_field: str | None = None
    drive_field: str | None = None
    controller_field: str | None = None
    # Fields to carry through verbatim into ExtractedProduct.extra, as
    # {output_name: source_field}. Use for measures with no first-class slot
    # (glass generation, print width) rather than forcing them into a numeric
    # column where they will be misread.
    passthrough: dict[str, str] = field(default_factory=dict)

    def apply(self, raw: dict[str, Any], product: ExtractedProduct) -> None:
        if self.payload_field:
            product.payload_kg = to_number(raw.get(self.payload_field))
        if self.reach_field:
            product.reach_mm = to_number(raw.get(self.reach_field))
        if self.dof_field:
            d = to_number(raw.get(self.dof_field))
            product.dof = int(d) if d else None
        if self.drive_field:
            product.drive = str(raw.get(self.drive_field) or "").strip()
        if self.controller_field:
            product.controllers = str(raw.get(self.controller_field) or "").strip()
        for out_name, src in self.passthrough.items():
            val = raw.get(src)
            if val not in (None, "", []):
                product.extra[out_name] = val


class Extractor(Protocol):
    """A catalogue-extraction strategy.

    Contract: `extract` returns an empty ExtractionResult (ideally with
    `declined_reason` set) when this strategy does not apply, so the caller can
    fall through to the next rung. It raises only on genuine faults — a network
    error is not "no products found", and conflating the two is how a broken
    run looks identical to a quiet one.
    """

    name: str

    def can_handle(self, url: str, html: str | None = None) -> bool: ...

    def extract(self, url: str, html: str | None = None) -> ExtractionResult: ...


class ExtractorRegistry:
    """Domain -> site config, plus the ordered generic strategy ladder.

    Per-company knowledge is CONFIG (an endpoint template, product-type codes,
    spec mappings), not code. The 67 bespoke `discover_<company>_robots.py`
    scripts in this repo are the counterfactual: each is a standalone program
    with its own fetch loop, its own parsing and its own staging, sharing
    nothing, so a fix to one benefits none of the others.
    """

    def __init__(self) -> None:
        self._sites: dict[str, dict[str, Any]] = {}
        self._strategies: list[Extractor] = []

    def register_site(self, domain: str, config: dict[str, Any]) -> None:
        self._sites[domain.replace("www.", "").lower()] = config

    def site_config(self, url_or_domain: str) -> dict[str, Any] | None:
        d = domain_of(url_or_domain) or url_or_domain.replace("www.", "").lower()
        if d in self._sites:
            return self._sites[d]
        # Allow a config registered on the registrable domain to serve its
        # subdomains (en.example.com -> example.com).
        parts = d.split(".")
        for i in range(1, len(parts) - 1):
            cand = ".".join(parts[i:])
            if cand in self._sites:
                return self._sites[cand]
        return None

    def register_strategy(self, strategy: Extractor) -> None:
        self._strategies.append(strategy)

    def strategies(self) -> Iterable[Extractor]:
        return tuple(self._strategies)

    def known_domains(self) -> list[str]:
        return sorted(self._sites)


registry = ExtractorRegistry()
