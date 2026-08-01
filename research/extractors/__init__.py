"""Structured-first catalogue extraction.

WHY THIS EXISTS
---------------
The existing discovery path is prose-first: fetch HTML -> hand it to Gemini ->
regex the leftovers for specs. That works on simple sites and fails badly on
modern storefronts. Measured on HD Hyundai Robotics: link mining produced 23
records of which ~9 were real robots (two were CONTROLLERS, three were the same
page heading in three spellings, two were the literal phrase "Industrial
Robot"). The company's own JSON API returned 69 real models with payload,
reach, DOF, drive type, controller compatibility and production status.

The lesson is not "Hyundai is special". It is that most catalogues are backed
by structured data — a JSON API, JSON-LD, or a spec table — and prose scraping
throws that structure away and then tries to reconstruct it with a language
model. Reading the structure directly is both cheaper and more accurate.

DESIGN
------
A ladder of strategies, tried best-evidence-first. Each returns
``list[ExtractedProduct]`` or an empty list to fall through:

    1. ManufacturerAPI  — the site's own JSON product endpoint (best: typed
                          fields, complete catalogue, no parsing)
    2. JsonLd           — schema.org/Product markup (structured, standardised)
    3. SpecTable        — an HTML spec table read AS a table, header-mapped
    4. (existing prose/Gemini path stays the fallback — this package does not
       replace it, it runs in front of it)

Strategies are per-site *capabilities*, not per-company scripts. A registry maps
a domain to any site-specific configuration (an API endpoint template, product
type codes) so that adding a company is data, not a new 300-line script. Where
no config exists the generic strategies still apply — JSON-LD and spec tables
need no per-site knowledge.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
* It does not translate. Where a site's narrative is not in English we compose
  factual English prose from the structured fields instead, because a catalogue
  claiming sourced data must not carry machine-translated marketing copy.
* It does not invent. A field absent from the source stays absent; there is no
  "reasonable default" for payload.
* It does not assume a spec slot means the same thing on every product type.
  HD Hyundai's second basic-spec slot is reach in mm for industrial arms and
  *glass generation* ("5G", "8G") for panel-transfer robots; a type-blind
  mapping recorded "a maximum reach of 5 mm". Type-awareness is a first-class
  concept here (see ``SpecMapping``), not a patch.
"""

from .base import (  # noqa: F401
    ExtractedProduct,
    ExtractionResult,
    Extractor,
    SpecMapping,
    registry,
)

__all__ = [
    "ExtractedProduct",
    "ExtractionResult",
    "Extractor",
    "SpecMapping",
    "registry",
]
