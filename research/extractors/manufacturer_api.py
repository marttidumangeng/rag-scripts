"""Strategy 1: read the manufacturer's own JSON product endpoint.

This is the highest-value rung of the ladder. A site that renders its catalogue
client-side is *already* serving structured JSON to its own front-end; scraping
the rendered DOM to recover fields the server handed out as typed values is
strictly worse. Proven on HD Hyundai Robotics: 69 complete models with payload,
reach, DOF, drive and production status, against 23 mostly-junk records from
link mining the same site.

Endpoint discovery is deliberately conservative. Guessing URLs against a live
manufacturer site is impolite and unreliable (see `_jaten_api_probe.py`, which
fires seven hand-written guesses at one host and mostly 404s). So:

  * a REGISTERED site config is used directly — no guessing;
  * otherwise we look for an endpoint the page itself reveals: an inline config
    block, a Next.js data island, or an obvious same-origin JSON path.

If neither yields anything the strategy declines and the ladder moves on.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

import requests

from .base import (
    ExtractedProduct,
    ExtractionResult,
    SpecMapping,
    domain_of,
    registry,
)

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}

# Inline config patterns that expose an API base. Hyundai's page carries
# `serverHost` + `serverApiVer`; Next.js sites carry a __NEXT_DATA__ island.
_INLINE_HOST_RE = re.compile(r"""serverHost\s*[:=]\s*["']([^"']+)["']""")
_INLINE_VER_RE = re.compile(r"""serverApiVer\s*[:=]\s*["']([^"']+)["']""")
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _walk_for_product_list(node: Any, depth: int = 0) -> list[dict] | None:
    """Find the first list-of-dicts that looks like a product collection.

    JSON envelopes vary wildly (`data.content`, `results`, `items`,
    `props.pageProps.products`), so shape-match rather than hard-code a path.
    """
    if depth > 6:
        return None
    if isinstance(node, list):
        if len(node) >= 2 and all(isinstance(i, dict) for i in node[:3]):
            keys = set().union(*(set(i.keys()) for i in node[:3]))
            # A product record names itself somehow.
            if any(re.search(r"(name|title|nm|model|prd)", k, re.I) for k in keys):
                return node
        return None
    if isinstance(node, dict):
        for value in node.values():
            found = _walk_for_product_list(value, depth + 1)
            if found:
                return found
    return None


def _first_str(raw: dict[str, Any], patterns: tuple[str, ...]) -> str:
    for pat in patterns:
        for k, v in raw.items():
            if re.fullmatch(pat, k, re.I) and isinstance(v, str) and v.strip():
                return v.strip()
    return ""


_NAME_PATTERNS = (r"prdNm", r"name", r"title", r"modelName", r"model", r"bdcTitle")
_CMS_PREFIX_RE = re.compile(r"^(제품관리_|PRODUCT_|상품_)\s*", re.I)
_ALIAS_RE = re.compile(r"^(.*?)\s*\(([^)]+)\)\s*$")


def split_alias(raw_name: str) -> tuple[str, str]:
    """'HDR220-26(HS220)' -> ('HDR220-26', 'HS220').

    Manufacturers that rename a line often keep the legacy code in parentheses.
    Importing both halves as separate products is a real and common failure —
    31 of HD Hyundai's 46 industrial records carry a dual name.
    """
    name = _CMS_PREFIX_RE.sub("", (raw_name or "").strip())
    m = _ALIAS_RE.match(name)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return name, ""


class ManufacturerAPIExtractor:
    """Pull a catalogue from a JSON endpoint, registered or page-declared."""

    name = "manufacturer_api"

    def __init__(self, session: requests.Session | None = None, timeout: int = 40) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    # -- discovery ---------------------------------------------------------
    def can_handle(self, url: str, html: str | None = None) -> bool:
        if registry.site_config(url):
            return True
        return bool(html and (_INLINE_HOST_RE.search(html) or _NEXT_DATA_RE.search(html)))

    def _endpoints_from_config(self, cfg: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        """Registered config -> concrete (url, params) pairs."""
        tmpl = cfg["endpoint"]
        variants = cfg.get("variants") or [{}]
        out = []
        for v in variants:
            params = dict(cfg.get("params") or {})
            params.update(v.get("params") or {})
            out.append((tmpl, {"params": params, "meta": v}))
        return out

    def _endpoint_from_page(self, url: str, html: str) -> str | None:
        host = _INLINE_HOST_RE.search(html)
        ver = _INLINE_VER_RE.search(html)
        if host:
            base = host.group(1).rstrip("/")
            if not base.startswith("http"):
                base = f"https://{domain_of(url)}{'' if base.startswith('/') else '/'}{base}"
            v = ver.group(1) if ver else "v1"
            return f"{base}/api/{v}/product/page"
        return None

    # -- extraction --------------------------------------------------------
    def extract(self, url: str, html: str | None = None) -> ExtractionResult:
        cfg = registry.site_config(url)
        if cfg:
            return self._extract_registered(url, cfg)
        if html:
            ep = self._endpoint_from_page(url, html)
            if ep:
                return self._extract_generic(ep, url)
            nd = _NEXT_DATA_RE.search(html)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                except json.JSONDecodeError:
                    return ExtractionResult(strategy=self.name,
                                            declined_reason="__NEXT_DATA__ present but unparseable")
                rows = _walk_for_product_list(data)
                if rows:
                    return self._rows_to_result(rows, url, None, "next_data")
        return ExtractionResult(strategy=self.name,
                                declined_reason="no registered config and no endpoint declared by the page")

    def _get_json(self, url: str, params: dict[str, Any] | None, referer: str) -> Any:
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = referer
        # A browser UA + Referer is required on WAF-fronted sites that 403 bare
        # clients. This is the same request the site's own front-end makes.
        r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _extract_registered(self, url: str, cfg: dict[str, Any]) -> ExtractionResult:
        products: list[ExtractedProduct] = []
        referer = cfg.get("referer") or f"https://{domain_of(url) or url}/"
        for tmpl, spec in self._endpoints_from_config(cfg):
            data = self._get_json(tmpl, spec["params"], referer)
            rows = _walk_for_product_list(data)
            if not rows:
                continue
            meta = spec["meta"]
            products.extend(self._rows_to_products(
                rows,
                page_url=meta.get("page_url") or url,
                mappings=cfg.get("spec_mappings") or [],
                image_url_template=cfg.get("image_url_template"),
                label=meta.get("label", ""),
            ))
        if not products:
            return ExtractionResult(strategy=self.name,
                                    declined_reason="registered endpoint returned no product-shaped rows")
        return ExtractionResult(products=products, strategy=self.name,
                                notes=f"registered config for {domain_of(url)}")

    def _extract_generic(self, endpoint: str, page_url: str) -> ExtractionResult:
        try:
            data = self._get_json(endpoint, None, page_url)
        except (requests.RequestException, ValueError) as exc:
            return ExtractionResult(strategy=self.name,
                                    declined_reason=f"page-declared endpoint unusable: {exc}")
        rows = _walk_for_product_list(data)
        if not rows:
            return ExtractionResult(strategy=self.name,
                                    declined_reason="page-declared endpoint returned no product-shaped rows")
        return self._rows_to_result(rows, page_url, None, "inline_config")

    def _rows_to_result(self, rows: list[dict], page_url: str,
                        mappings: list[SpecMapping] | None, how: str) -> ExtractionResult:
        return ExtractionResult(
            products=self._rows_to_products(rows, page_url, mappings or [], None, ""),
            strategy=self.name,
            notes=f"endpoint discovered via {how}",
        )

    def _rows_to_products(self, rows: list[dict], page_url: str,
                          mappings: list[SpecMapping],
                          image_url_template: str | None,
                          label: str) -> list[ExtractedProduct]:
        out: list[ExtractedProduct] = []
        for raw in rows:
            raw_name = _first_str(raw, _NAME_PATTERNS)
            if not raw_name and isinstance(raw.get("bdContent"), dict):
                raw_name = str(raw["bdContent"].get("bdcTitle") or "")
            name, alias = split_alias(raw_name)
            if not name:
                # Draft/placeholder rows are normal in CMS-backed catalogues
                # (HD Hyundai ships one with an empty name); skip quietly.
                continue

            p = ExtractedProduct(name=name, alias=alias, source_url=page_url,
                                 product_type=label, via=self.name)

            mapping = next((m for m in mappings if m.applies_to(raw)), None)
            if mapping:
                mapping.apply(raw, p)

            mass = raw.get("prdMassYn")
            if isinstance(mass, str) and mass.strip():
                p.in_production = mass.strip().upper() == "Y"

            if image_url_template:
                seq = self._thumb_seq(raw)
                if seq:
                    p.image_urls.append(image_url_template.format(seq=seq))
            out.append(p)
        return out

    @staticmethod
    def _thumb_seq(raw: dict[str, Any]) -> Any:
        bd = raw.get("bdContent")
        if isinstance(bd, dict):
            return bd.get("bdcThumbFile1Seq") or (bd.get("bdcThumbFile1") or {}).get("fileSeq") \
                if isinstance(bd.get("bdcThumbFile1"), dict) else bd.get("bdcThumbFile1Seq")
        return None


def make_hyundai_config() -> dict[str, Any]:
    """HD Hyundai Robotics — the reference site config.

    Everything site-specific lives here as DATA: which product-type codes are
    robots, and how each type's spec slots map. Adding another manufacturer
    should look like this function, not like a new script.
    """
    def is_fpd(raw: dict[str, Any]) -> bool:
        return str(raw.get("prdTypeCd")) == "60010002"

    def is_arm(raw: dict[str, Any]) -> bool:
        return str(raw.get("prdTypeCd")) in {"60010001", "60010007"}

    return {
        "endpoint": "https://www.hd-hyundairobotics.com/api/v1/product/page",
        "referer": "https://www.hd-hyundairobotics.com/",
        "params": {"page": 0, "size": 300},
        "image_url_template": "https://www.hd-hyundairobotics.com/api/v1/file/ck/view/{seq}",
        # Robot product types only. 60010003 (controllers) and 60010004
        # (positioners) are deliberately excluded — they are equipment, not
        # robots, and link mining previously imported two controllers (Hi5a,
        # Hi6) as robots for exactly this reason.
        "variants": [
            {"label": "industrial articulated", "params": {"prdTypeCd": "60010001"},
             "page_url": "https://www.hd-hyundairobotics.com/biz/product/60010001"},
            {"label": "FPD glass transfer", "params": {"prdTypeCd": "60010002"},
             "page_url": "https://www.hd-hyundairobotics.com/biz/product/60010002"},
            {"label": "collaborative", "params": {"prdTypeCd": "60010007"},
             "page_url": "https://www.hd-hyundairobotics.com/biz/product/60010007"},
        ],
        "spec_mappings": [
            # Panel-transfer robots FIRST: their slot-2 is a glass-generation
            # rating ("5G"), not millimetres. Mapping it as reach yielded
            # "a maximum reach of 5 mm" before this guard existed.
            SpecMapping(
                name="fpd", applies_to=is_fpd,
                controller_field="prdBscSpec3",
                dof_field="prdDtlSpec2", drive_field="prdDtlSpec3",
                passthrough={"glass_generation": "prdBscSpec2"},
            ),
            SpecMapping(
                name="articulated", applies_to=is_arm,
                payload_field="prdBscSpec1", reach_field="prdBscSpec2",
                controller_field="prdBscSpec3",
                dof_field="prdDtlSpec2", drive_field="prdDtlSpec3",
            ),
        ],
    }


registry.register_site("hd-hyundairobotics.com", make_hyundai_config())
registry.register_site("hyundai-robotics.com", make_hyundai_config())  # 301s to the above
