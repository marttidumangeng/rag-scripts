"""Estun English catalog: parse en.estun.com list pages for model URLs and hero images.

No Gemini required — list pages are server-rendered and include per-model cards with
`/upload/image/` assets. Detail pages (`?list_NNN/ID.html`) are JS shells over HTTP fetch.
"""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse

from web_extract import (
    WebFetcher,
    is_junk_image_url,
    is_product_upload_image,
    parse_page,
    search_model_name_aliases,
)

ESTUN_ENGLISH_LIST_URLS = [
    "https://en.estun.com/?list_13/",    # ER series
    "https://en.estun.com/?list_161/",   # UNO series
    "https://en.estun.com/?list_191/",  # Collaborative robots
    "https://en.estun.com/?list_162/",   # Specialized series
]

# list page → family metadata (list pages are family/series scopes)
ESTUN_LIST_FAMILY = {
    "list_13": ("estun:er", "ER Series"),
    "list_161": ("estun:uno", "UNO Series"),
    "list_191": ("estun:collaborative", "Collaborative Robots"),
    "list_162": ("estun:specialized", "Specialized Series"),
}

ESTUN_ENGLISH_SITE = "https://en.estun.com"


def is_estun_website(website: str) -> bool:
    netloc = urlparse(website or "").netloc.lower().removeprefix("www.")
    return netloc in ("estun.com", "en.estun.com")


def _normalize_model(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower()).removeprefix("i")


def _abs_image_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("/"):
        return ESTUN_ENGLISH_SITE + raw
    return raw


def _list_key(list_url: str) -> str:
    m = re.search(r"list_(\d+)", list_url or "")
    return f"list_{m.group(1)}" if m else ""


def derive_estun_family_metadata(name: str, *, list_key: str = "") -> dict[str, str]:
    """Flat family fields from model name (preferred) or catalog list page."""
    n = re.sub(r"^estun\s+", "", (name or "").strip(), flags=re.I)
    upper = n.upper()

    if re.search(r"\bER-?DB\b", upper) or upper.startswith("ER-DB"):
        key, label = "estun:er-db", "ER-DB Series"
    elif re.match(r"^IER", upper) or re.match(r"^iER", n):
        key, label = "estun:ier", "iER Series"
    elif re.match(r"^ECR", upper):
        key, label = "estun:ecr", "ECR Series"
    elif re.match(r"^UNO", upper) or "UNO-" in upper:
        key, label = "estun:uno", "UNO Series"
    elif "M-SERIES" in upper or re.match(r"^M-\d", n, re.I):
        key, label = "estun:m-series", "M-Series Mobile Manipulator"
    elif any(x in upper for x in ("COLLABORATIVE", "EMR-", "CO-RAY", "CO-PALLETIZER", "CO-ARC")):
        key, label = "estun:collaborative", "Collaborative Robots"
    elif re.match(r"^S\d", upper) or re.match(r"^S\d", n):
        key, label = "estun:s-series", "S Series"
    elif re.match(r"^ER[\d/]", upper) or re.match(r"^ER\d", n, re.I):
        key, label = "estun:er", "ER Series"
    elif list_key in ESTUN_LIST_FAMILY:
        key, label = ESTUN_LIST_FAMILY[list_key]
    else:
        key, label = "estun:other", "Estun Other"

    # variant differentiator: strip family label words, keep model code
    variant_code = n
    for prefix in ("Estun Collaborative Robot ", "Estun ", "Collaborative Robot "):
        if variant_code.startswith(prefix):
            variant_code = variant_code[len(prefix) :]
    return {
        "family_key": key,
        "family_name": label,
        "variant_code": variant_code.strip()[:255],
        "variant_label": "",
        "product_url_scope": "exact_variant",
    }


def build_structured_estun_image(
    *,
    image_url: str,
    source_page_url: str,
    list_url: str = "",
) -> dict:
    """Phase-1 structured candidate from English catalog hero."""
    page = (source_page_url or list_url or "").strip()
    # Catalog card heroes are series-list assets tied to a detail URL when present.
    exact = bool(re.search(r"list_\d+/\d+\.html", page))
    return {
        "url": image_url,
        "source_page_url": page,
        "source_tier": "official_exact" if exact else "official_family",
        "source_publisher": "Estun",
        "media_class": "product_photo",
        "image_scope": "exact_variant" if exact else "family",
        "rights_status": "review_required",
        "match_reason": "English catalog list/detail card hero from en.estun.com.",
    }


@lru_cache(maxsize=1)
def build_estun_english_catalog() -> dict[str, dict[str, str]]:
    """model name -> {url, image, list_url, list_key} from English series list pages.

    Plain HTTP to en.estun.com often returns 502; use stealth (browser UA / curl_cffi).
    """
    fetcher = WebFetcher(timeout=30, stealth=True)
    catalog: dict[str, dict[str, str]] = {}
    for list_url in ESTUN_ENGLISH_LIST_URLS:
        page = parse_page(fetcher, list_url, rendered=False)
        if not page:
            continue
        html = page.html
        list_key = _list_key(list_url)
        for m in re.finditer(r"\?list_(\d+)/(\d+)\.html", html):
            start = max(0, m.start() - 800)
            chunk = html[start : m.end() + 400]
            names = re.findall(r"(?:i?ER\d[\w-]+|UNO-[\w-]+|ECR\d[\w-]*)", chunk)
            if not names:
                continue
            model = names[-1]
            product_url = f"{ESTUN_ENGLISH_SITE}/?list_{m.group(1)}/{m.group(2)}.html"
            hero = ""
            for raw in re.findall(r'src=["\']([^"\']+)["\']', chunk):
                url = _abs_image_url(raw)
                if is_product_upload_image(url) and not is_junk_image_url(url):
                    hero = url
                    break
            entry = catalog.setdefault(
                model,
                {
                    "url": product_url,
                    "image": hero,
                    "list_url": list_url,
                    "list_key": list_key,
                },
            )
            if hero and not entry.get("image"):
                entry["image"] = hero
            if list_url and not entry.get("list_url"):
                entry["list_url"] = list_url
                entry["list_key"] = list_key
    return catalog


def _numeric_fingerprint(name: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", name or ""))


def _pick_catalog_candidate(name: str, candidates: list[str]) -> str:
    if len(candidates) == 1:
        return candidates[0]
    query = _normalize_model(name)
    scored: list[tuple[int, str]] = []
    for cand in candidates:
        cand_norm = _normalize_model(cand)
        score = sum(1 for a, b in zip(query, cand_norm) if a == b)
        if "sr" in query and "sr" in cand_norm:
            score += 5
        if "mi" in query and "mi" in cand_norm:
            score += 5
        if cand_norm.endswith("f") and not query.endswith("f"):
            score -= 3
        scored.append((score, cand))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def _estun_fuzzy_keys(name: str) -> list[str]:
    """Generate normalized lookup keys for iER/ER/B-variant naming on Estun English site."""
    keys: list[str] = []
    for alias in search_model_name_aliases(name):
        keys.append(_normalize_model(alias))
        compact = re.sub(r"[^a-z0-9]", "", alias.lower()).removeprefix("i")
        keys.append(compact)
        keys.append(re.sub(r"er(\d+)b", r"er\1", compact))
        keys.append(re.sub(r"er(\d+)c", r"er\1", compact))
        keys.append(
            compact.replace("uno", "").replace("hi", "").replace("dw", "").replace("pl", "").replace("pr", "")
        )
    return list(dict.fromkeys(k for k in keys if k))


def _enrich_entry(hit: str, catalog: dict[str, dict[str, str]], query_name: str) -> dict[str, str]:
    entry = {"name": hit, **catalog[hit]}
    family = derive_estun_family_metadata(query_name or hit, list_key=entry.get("list_key") or "")
    entry.update(family)
    if entry.get("image"):
        entry["image_candidate"] = build_structured_estun_image(
            image_url=entry["image"],
            source_page_url=entry.get("url") or "",
            list_url=entry.get("list_url") or "",
        )
    return entry


def lookup_estun_english_entry(name: str, model_name: str = "") -> dict[str, str] | None:
    """Resolve a staged/DB robot name to English catalog URL + image using iER/ER aliases."""
    catalog = build_estun_english_catalog()
    if not catalog:
        return None
    by_norm = {_normalize_model(k): k for k in catalog}
    query_name = model_name or name
    for key in _estun_fuzzy_keys(query_name):
        hit = by_norm.get(key)
        if hit:
            return _enrich_entry(hit, catalog, query_name)

    cat_by_fp: dict[tuple[int, ...], list[str]] = {}
    for catalog_name in catalog:
        cat_by_fp.setdefault(_numeric_fingerprint(catalog_name), []).append(catalog_name)

    for alias in search_model_name_aliases(query_name):
        fp = _numeric_fingerprint(alias)
        if fp:
            hits = cat_by_fp.get(fp)
            if hits:
                hit = _pick_catalog_candidate(query_name, hits)
                return _enrich_entry(hit, catalog, query_name)
        compact = re.sub(r"[^a-z0-9]", "", alias.lower()).removeprefix("i")
        b_fp = _numeric_fingerprint(re.sub(r"er(\d+)", r"er\1b", compact, count=1))
        if b_fp and b_fp != fp:
            hits = cat_by_fp.get(b_fp)
            if hits:
                hit = _pick_catalog_candidate(query_name, hits)
                return _enrich_entry(hit, catalog, query_name)

    if re.search(r"sr", query_name, re.I):
        nums = _numeric_fingerprint(query_name)
        if len(nums) >= 2:
            series, spec = nums[0], nums[-1]
            sr_hits = [
                cn
                for cn in catalog
                if re.search(r"sr", cn, re.I) and spec in _numeric_fingerprint(cn)
            ]
            if sr_hits:
                if len(sr_hits) == 1:
                    return _enrich_entry(sr_hits[0], catalog, query_name)
                ranked = sorted(
                    sr_hits,
                    key=lambda cn: (
                        abs((_numeric_fingerprint(cn) or (0,))[0] - series),
                        len(cn),
                        cn,
                    ),
                )
                hit = ranked[0]
                return _enrich_entry(hit, catalog, query_name)

    query = _normalize_model(query_name)
    if len(query) >= 8:
        best_name = ""
        best_score = 0
        for catalog_name in catalog:
            stem = _normalize_model(catalog_name)
            score = 0
            limit = min(len(query), len(stem))
            while score < limit and query[score] == stem[score]:
                score += 1
            if score > best_score:
                best_score = score
                best_name = catalog_name
        if best_name and best_score >= max(8, int(len(query) * 0.7)):
            return _enrich_entry(best_name, catalog, query_name)
    return None


def preferred_estun_search_site(company_website: str) -> str:
    """Prefer English site for Estun product URL search."""
    if is_estun_website(company_website):
        return ESTUN_ENGLISH_SITE
    return company_website
