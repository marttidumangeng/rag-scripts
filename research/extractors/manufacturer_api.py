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

import html
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
    to_number,
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


# Key sets that mark a list as navigation/menu rather than a product feed.
# Zoox's __NEXT_DATA__ yielded "How To Ride" / "Know Your Ride" / "Support" /
# "Where to Ride" — a nav menu whose entries have a label and a link and
# nothing else. Shape-matching on "has a name-ish key" alone cannot tell that
# apart from a catalogue, so the discriminator is what ELSE the record carries.
_NAV_KEY_RE = re.compile(r"^(href|url|path|slug|link|target|children|submenu|"
                         r"icon|order|isExternal|newTab)$", re.I)
_PRODUCT_KEY_RE = re.compile(
    r"(price|sku|spec|payload|reach|weight|dimension|model|variant|stock|"
    r"category|image|thumb|photo|media|capacity|voltage|series|partNumber|"
    r"prdBscSpec|prdDtlSpec|prdTypeCd)", re.I)


def _looks_like_navigation(rows: list[dict]) -> bool:
    keys = set().union(*(set(r.keys()) for r in rows[:5]))
    nav_hits = sum(1 for k in keys if _NAV_KEY_RE.match(k))
    prod_hits = sum(1 for k in keys if _PRODUCT_KEY_RE.search(k))
    # Nav-shaped and carrying no product-shaped field at all.
    return prod_hits == 0 and nav_hits >= 1


def _walk_for_product_list(node: Any, depth: int = 0) -> list[dict] | None:
    """Find the first list-of-dicts that looks like a product collection.

    JSON envelopes vary wildly (`data.content`, `results`, `items`,
    `props.pageProps.products`), so shape-match rather than hard-code a path —
    but naming alone is far too weak a signal: a navigation menu, a breadcrumb
    trail and a footer link list are all "lists of dicts with a name". A
    candidate must therefore ALSO carry at least one product-shaped key, or
    not be nav-shaped.
    """
    if depth > 6:
        return None
    if isinstance(node, list):
        if len(node) >= 2 and all(isinstance(i, dict) for i in node[:3]):
            keys = set().union(*(set(i.keys()) for i in node[:3]))
            named = any(re.search(r"(name|title|nm|model|prd)", k, re.I) for k in keys)
            if named and not _looks_like_navigation(node):
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


def _plain_text(value: Any) -> str:
    """Strip tags/entities from a CMS rich-text field. WooCommerce ships
    `description` as rendered HTML."""
    if isinstance(value, dict):
        value = value.get("rendered") or value.get("raw") or ""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value)))


def _attr_lookup(raw: dict[str, Any], cfg: dict[str, Any]) -> dict[str, str]:
    """Flatten a WooCommerce-style attribute array into {lowercased label: value}.

    WooCommerce publishes specs as `attributes: [{name, terms: [{name}]}]`
    rather than as flat fields, so SpecMapping's field-name lookup cannot see
    them at all. That array is Nachi's entire machine-readable spec layer.
    """
    path = cfg.get("attributes_path")
    if not path:
        return {}
    items = raw.get(path)
    if not isinstance(items, list):
        return {}
    out: dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        label = str(it.get(cfg.get("attribute_name_key", "name")) or "").strip()
        if not label:
            continue
        terms = it.get(cfg.get("attribute_terms_key", "terms"))
        if isinstance(terms, list):
            vals = [str((t or {}).get("name") or "").strip()
                    for t in terms if isinstance(t, dict)]
            vals = [v for v in vals if v]
            if vals:
                out[label.lower()] = ", ".join(vals)
        elif it.get("value") not in (None, ""):
            out[label.lower()] = str(it["value"]).strip()
    return out


def _drop_shared_images(products: list[ExtractedProduct]) -> int:
    """Remove any image URL that more than one product in the batch claims.

    Not a placeholder filter — the images this catches are usually real product
    photos. Nachi's `robotproductspage.ai_.png` is a clean studio shot captioned
    "MZ35S", and the feed serves it for four different models: correct for one,
    wrong for three. Since the feed gives no way to tell which one owns it, the
    only safe reading is that a shared reference identifies nothing. Dropping it
    leaves the robot imageless, which the media sweep can fix; keeping it plants
    a confidently mislabelled hero, which nothing downstream will question.
    """
    counts: dict[str, int] = {}
    for p in products:
        for u in set(p.image_urls):
            counts[u] = counts.get(u, 0) + 1
    shared = {u for u, n in counts.items() if n > 1}
    if not shared:
        return 0
    removed = 0
    for p in products:
        keep = [u for u in p.image_urls if u not in shared]
        removed += len(p.image_urls) - len(keep)
        p.image_urls = keep
    return removed


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

    def _get_json(self, url: str, params: dict[str, Any] | None, referer: str,
                  extra_headers: dict[str, str] | None = None) -> Any:
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = referer
        # A browser UA + Referer is required on WAF-fronted sites that 403 bare
        # clients. This is the same request the site's own front-end makes.
        # extra_headers covers per-site requirements that are NOT blocks and
        # must not be mistaken for one: Techman's API answers 406 with
        # "missing Content-Language header" until that header is supplied.
        if extra_headers:
            headers.update(extra_headers)
        r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _extract_registered(self, url: str, cfg: dict[str, Any]) -> ExtractionResult:
        products: list[ExtractedProduct] = []
        referer = cfg.get("referer") or f"https://{domain_of(url) or url}/"
        for tmpl, spec in self._endpoints_from_config(cfg):
            data = self._get_json(tmpl, spec["params"], referer, cfg.get("extra_headers"))
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
                cfg=cfg,
            ))
        if not products:
            return ExtractionResult(strategy=self.name,
                                    declined_reason="registered endpoint returned no product-shaped rows")
        dropped = 0
        if cfg.get("drop_shared_images"):
            dropped = _drop_shared_images(products)
        note = f"registered config for {domain_of(url)}"
        if dropped:
            note += f"; dropped {dropped} shared image reference(s)"
        return ExtractionResult(products=products, strategy=self.name, notes=note)

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
                          label: str,
                          cfg: dict[str, Any] | None = None) -> list[ExtractedProduct]:
        cfg = cfg or {}
        out: list[ExtractedProduct] = []
        for raw in rows:
            raw_name = _first_str(raw, _NAME_PATTERNS)
            if not raw_name and isinstance(raw.get("bdContent"), dict):
                raw_name = str(raw["bdContent"].get("bdcTitle") or "")
            for pat, repl in (cfg.get("name_replace") or []):
                raw_name = re.sub(pat, repl, raw_name)
            name, alias = split_alias(raw_name)
            if not name:
                # Draft/placeholder rows are normal in CMS-backed catalogues
                # (HD Hyundai ships one with an empty name); skip quietly.
                continue

            # Per-product page URL. Falling back to the company page is what
            # `url_content_mismatch` punishes: verification checks that the
            # robot is NAMED in the body text of its own source URL, and a
            # homepage names none of them. Techman rows scored 63-71 against
            # the homepage; against their own product pages they name the
            # robot outright.
            product_url = page_url
            if cfg.get("product_url_field"):
                v = raw.get(cfg["product_url_field"])
                if isinstance(v, str) and v.startswith("http"):
                    product_url = v
            elif cfg.get("product_url_builder"):
                built = cfg["product_url_builder"](raw)
                if built:
                    product_url = built

            p = ExtractedProduct(name=name, alias=alias, source_url=product_url,
                                 product_type=label, via=self.name)

            mapping = next((m for m in mappings if m.applies_to(raw)), None)
            if mapping:
                mapping.apply(raw, p)

            # Attribute-array specs (WooCommerce shape). Applied after the
            # field mapping so a flat field always wins over an attribute of
            # the same meaning.
            attrs = _attr_lookup(raw, cfg)
            for label_key, field in (cfg.get("attribute_map") or {}).items():
                val = attrs.get(label_key.lower())
                if val in (None, ""):
                    continue
                if field in ("payload_kg", "reach_mm"):
                    if getattr(p, field) is None:
                        setattr(p, field, to_number(val))
                elif field == "dof":
                    if p.dof is None:
                        n = to_number(val)
                        p.dof = int(n) if n else None
                else:
                    p.extra.setdefault(field, val)

            mass = raw.get("prdMassYn")
            if isinstance(mass, str) and mass.strip():
                p.in_production = mass.strip().upper() == "Y"

            # Images: template (Hyundai file-seq) or straight URL lists.
            if image_url_template:
                seq = self._thumb_seq(raw)
                if seq:
                    p.image_urls.append(image_url_template.format(seq=seq))
            for key in (cfg.get("image_fields") or []):
                v = raw.get(key)
                if isinstance(v, str) and v.startswith("http"):
                    p.image_urls.append(v)
                elif isinstance(v, list):
                    for i in v:
                        if isinstance(i, str) and i.startswith("http"):
                            p.image_urls.append(i)
                        elif isinstance(i, dict):
                            for k2 in ("src", "url", "thumbnail"):
                                if isinstance(i.get(k2), str) and i[k2].startswith("http"):
                                    p.image_urls.append(i[k2]); break
            bad_img = cfg.get("exclude_image_matches")
            if bad_img:
                p.image_urls = [u for u in p.image_urls if not re.search(bad_img, u, re.I)]
            p.image_urls = list(dict.fromkeys(p.image_urls))[:4]

            # Named sub-objects (applicationCategories -> "Assembly, Inspection").
            # Kept because uses/industries must be filled from data we already
            # have rather than re-derived later from prose.
            for out_name, src_key in (cfg.get("list_name_fields") or {}).items():
                vals = [str((i or {}).get("name") or "").strip()
                        for i in (raw.get(src_key) or []) if isinstance(i, dict)]
                vals = [v for v in vals if v]
                if vals:
                    p.extra[out_name] = ", ".join(dict.fromkeys(vals))

            # Axis count stated in the copy but not typed as a field. Only a
            # match ANCHORED to this product's own name counts: an unanchored
            # `(\d)-axis` on the same page happily matches "J2-axis encoder"
            # and yielded 1- and 7-axis readings for 6-axis arms.
            if p.dof is None and cfg.get("dof_from_text_fields"):
                blob = " ".join(_plain_text(raw.get(k)) for k in cfg["dof_from_text_fields"])
                m = re.search(re.escape(p.name) + r"\b[^.]{0,80}?\b(\d)-axis", blob, re.I)
                if m:
                    p.dof = int(m.group(1))

            for fld, val in (cfg.get("constants") or {}).items():
                if getattr(p, fld, None) in (None, "", []):
                    setattr(p, fld, val)

            # Exclusions: a catalogue endpoint often mixes non-robots in
            # (Nachi's product feed carries 5 controllers alongside 62 robots).
            skip = cfg.get("exclude_if_name_matches")
            if skip and re.search(skip, p.name, re.I):
                continue
            req = cfg.get("require_field")
            if req and not (getattr(p, req, None) or p.extra.get(req)):
                continue
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


def make_nachi_config() -> dict[str, Any]:
    """Nachi Robotics — WooCommerce Store API.

    Nachi runs its catalogue on WooCommerce, whose Store API is public and
    unauthenticated. Specs live in the `attributes` array rather than as flat
    fields, which is why `attribute_map` exists.

    Only four measures are machine-readable (reach, payload, application,
    mount); everything deeper is baked into the JPEGs on the product pages, so
    this config deliberately claims no more than the API actually types.
    """
    return {
        "endpoint": "https://www.nachirobotics.com/wp-json/wc/store/v1/products",
        "referer": "https://www.nachirobotics.com/",
        "params": {"per_page": 100},
        # WooCommerce publishes the canonical product page per row.
        "product_url_field": "permalink",
        "attributes_path": "attributes",
        "attribute_map": {
            "payload": "payload_kg",
            "reach": "reach_mm",
            "application": "applications",
            "mount": "mounting",
        },
        "image_fields": ["images"],
        # Nine models point at three images that other models also claim.
        "drop_shared_images": True,
        # Axis count is not an attribute, but the copy states it for 10 models
        # ("The MZ35S is a high-performance 6-axis industrial robot").
        "dof_from_text_fields": ["short_description", "description"],
        # The feed mixes 5 controllers (CFD/CFDQ/CFDS/FD11/FD18) in with the
        # robots. They are the only rows with no payload attribute, so the
        # requirement doubles as the discriminator — no name blocklist to rot.
        "require_field": "payload_kg",
    }


def make_techman_config() -> dict[str, Any]:
    """Techman Robot — the Nuxt front-end's own products API.

    The endpoint answers 406, not 403, until `Content-Language` is sent. That
    distinction matters: a 406 here looks exactly like a bot block and would
    otherwise trigger a pointless Playwright escalation against a site that is
    serving clean JSON to anyone who asks correctly.
    """
    def always(_raw: dict[str, Any]) -> bool:
        return True

    def product_url(raw: dict[str, Any]) -> str:
        """The product path segment depends on the series: the S line lives
        under tm-ai-cobot-s-series, everything else under tm-ai-cobot-series.
        All 14 verified 200 + name the robot in the page body."""
        route = str(raw.get("routeName") or "").strip()
        if not route:
            return ""
        seg = "tm-ai-cobot-s-series" if raw.get("typeName") == "S" else "tm-ai-cobot-series"
        return f"https://www.tm-robot.com/en/product/{seg}/{route}"

    return {
        "endpoint": "https://www.tm-robot.com/be/api/v1/products/arms",
        "product_url_builder": product_url,
        "referer": "https://www.tm-robot.com/",
        "extra_headers": {"Content-Language": "en"},
        # The API prints display names with spaces around the hyphen
        # ("TM5 - 700"); the designation everyone else uses is "TM5-700".
        "name_replace": [(r"\s*-\s*", "-")],
        "image_fields": ["images"],
        "list_name_fields": {"applications": "applicationCategories"},
        # Every TM arm is a 6-axis collaborative arm; the API does not type
        # axis count at all, and leaving DOF blank on all 14 would be losing
        # information we hold with certainty.
        "constants": {"dof": 6},
        "spec_mappings": [
            SpecMapping(
                name="tm_arm", applies_to=always,
                payload_field="payload", reach_field="reach",
                passthrough={"weight_kg": "weight", "ip_rating": "ipiv",
                             "variant_line": "typeName", "tagline": "feature"},
            ),
        ],
    }


registry.register_site("hd-hyundairobotics.com", make_hyundai_config())
registry.register_site("hyundai-robotics.com", make_hyundai_config())  # 301s to the above
registry.register_site("nachirobotics.com", make_nachi_config())
registry.register_site("tm-robot.com", make_techman_config())
