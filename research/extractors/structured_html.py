"""Strategies 2 and 3: JSON-LD, then spec tables read AS tables.

Neither needs per-site configuration, which is what makes them worth having:
they apply to every manufacturer immediately, whereas an API config has to be
written per domain.

Today the pipeline has neither. `web_extract.py` reads `og:image` and
`og:description` and nothing else structured; there is no `application/ld+json`
handling anywhere, and no HTML `<table>` parsing in any production path. Specs
come from regex over page prose — `_PAYLOAD_KG_RE` is a bare ``(\\d+)\\s*kg``
whose FIRST match anywhere on the page wins, with no requirement that the
number be labelled as payload. A page mentioning "handles up to 50 kg pallets"
in marketing copy will hand back 50 kg as the robot's payload.
"""
from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from .base import ExtractedProduct, ExtractionResult, to_number

_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def _iter_ld_nodes(html: str):
    for block in _LD_RE.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if "@graph" in node:
                    stack.extend(node["@graph"] if isinstance(node["@graph"], list)
                                 else [node["@graph"]])
                yield node


def _types_of(node: dict[str, Any]) -> set[str]:
    t = node.get("@type") or node.get("type") or ""
    vals = t if isinstance(t, list) else [t]
    return {str(v).lower() for v in vals}


class JsonLdExtractor:
    """schema.org/Product markup — standardised, and common on real storefronts."""

    name = "json_ld"

    def can_handle(self, url: str, html: str | None = None) -> bool:
        return bool(html and "application/ld+json" in html)

    def extract(self, url: str, html: str | None = None) -> ExtractionResult:
        if not html:
            return ExtractionResult(strategy=self.name, declined_reason="no html supplied")
        products: list[ExtractedProduct] = []
        seen: set[str] = set()
        for node in _iter_ld_nodes(html):
            if "product" not in _types_of(node):
                continue
            name = str(node.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            p = ExtractedProduct(name=name, source_url=url, via=self.name,
                                 product_type=str(node.get("category") or "").strip())
            img = node.get("image")
            if isinstance(img, str):
                p.image_urls.append(img)
            elif isinstance(img, list):
                p.image_urls.extend(str(i) for i in img if isinstance(i, str))
            elif isinstance(img, dict) and img.get("url"):
                p.image_urls.append(str(img["url"]))

            # additionalProperty is schema.org's typed spec channel — a
            # name/value list, which is exactly what we want and exactly what
            # prose regex has to guess at.
            for prop in (node.get("additionalProperty") or []):
                if not isinstance(prop, dict):
                    continue
                pname = str(prop.get("name") or "").strip().lower()
                pval = prop.get("value")
                if not pname or pval in (None, ""):
                    continue
                if "payload" in pname or "load capacity" in pname:
                    p.payload_kg = to_number(pval)
                elif "reach" in pname or "working radius" in pname:
                    p.reach_mm = to_number(pval)
                elif "axes" in pname or pname in {"dof", "degrees of freedom"}:
                    d = to_number(pval)
                    p.dof = int(d) if d else None
                else:
                    p.extra[pname] = pval

            desc = str(node.get("description") or "").strip()
            if desc:
                p.extra["description"] = desc
            products.append(p)

        if not products:
            return ExtractionResult(strategy=self.name,
                                    declined_reason="ld+json present but no Product nodes")
        return ExtractionResult(products=products, strategy=self.name)


# Header text -> the measure it denotes. Matching is on the ROW LABEL, so a
# number is only ever recorded as payload when its own row says payload.
_ROW_PATTERNS: list[tuple[str, str]] = [
    (r"payload|load capacity|rated load|max(?:imum)?\s+load", "payload_kg"),
    (r"reach|working radius|arm span|max(?:imum)?\s+radius", "reach_mm"),
    (r"repeat(?:ability)?|position repeat", "repeatability_mm"),
    (r"axes|degrees of freedom|\bdof\b", "dof"),
    (r"weight|mass", "weight_kg"),
]


def _measure_for(label: str) -> str | None:
    lab = re.sub(r"\s+", " ", (label or "")).strip().lower()
    if not lab:
        return None
    for pat, measure in _ROW_PATTERNS:
        if re.search(pat, lab):
            return measure
    return None


class SpecTableExtractor:
    """Read a spec table as a table: label column governs the value.

    Handles the two real layouts — vertical (label | value per row) and
    horizontal (models across the header, measures down the first column),
    the latter being how a manufacturer presents a whole variant family on one
    page. That horizontal case is precisely the "family we only captured one
    member of" problem: the page lists every variant, and prose scraping sees
    one blob of numbers.
    """

    name = "spec_table"

    def can_handle(self, url: str, html: str | None = None) -> bool:
        return bool(html and "<table" in html.lower())

    def extract(self, url: str, html: str | None = None) -> ExtractionResult:
        if not html:
            return ExtractionResult(strategy=self.name, declined_reason="no html supplied")
        soup = BeautifulSoup(html, "html.parser")
        products: list[ExtractedProduct] = []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            grid = [[c.get_text(" ", strip=True) for c in r.find_all(["th", "td"])]
                    for r in rows]
            grid = [r for r in grid if any(c for c in r)]
            if not grid:
                continue

            width = max(len(r) for r in grid)
            # Horizontal: >=3 columns and several label-bearing first cells.
            labelled = sum(1 for r in grid if len(r) > 1 and _measure_for(r[0]))
            if width >= 3 and labelled >= 2:
                products.extend(self._horizontal(grid, width, url))
            elif labelled >= 2:
                p = self._vertical(grid, url)
                if p:
                    products.append(p)

        if not products:
            return ExtractionResult(strategy=self.name,
                                    declined_reason="tables present but none carried recognisable spec labels")
        return ExtractionResult(products=products, strategy=self.name)

    def _horizontal(self, grid: list[list[str]], width: int, url: str) -> list[ExtractedProduct]:
        header = grid[0]
        # Column 0 holds measure labels; columns 1..n are model names.
        models = [(i, header[i]) for i in range(1, min(width, len(header)))
                  if header[i] and not _measure_for(header[i])]
        if not models:
            return []
        out = []
        for idx, model_name in models:
            p = ExtractedProduct(name=model_name.strip(), source_url=url, via=self.name)
            got = False
            for row in grid[1:]:
                if len(row) <= idx:
                    continue
                measure = _measure_for(row[0])
                if not measure:
                    continue
                val = to_number(row[idx])
                if val is None:
                    continue
                got = True
                if measure == "dof":
                    p.dof = int(val)
                elif measure in {"payload_kg", "reach_mm", "repeatability_mm", "weight_kg"}:
                    setattr(p, measure, val) if hasattr(p, measure) else p.extra.__setitem__(measure, val)
            if got:
                out.append(p)
        return out

    def _vertical(self, grid: list[list[str]], url: str) -> ExtractedProduct | None:
        p = ExtractedProduct(name="", source_url=url, via=self.name)
        got = False
        for row in grid:
            if len(row) < 2:
                continue
            measure = _measure_for(row[0])
            if not measure:
                continue
            val = to_number(row[1])
            if val is None:
                continue
            got = True
            if measure == "dof":
                p.dof = int(val)
            elif hasattr(p, measure):
                setattr(p, measure, val)
            else:
                p.extra[measure] = val
        # A vertical table describes the page's own product; the caller supplies
        # the name, since the table itself rarely repeats it.
        return p if got else None
