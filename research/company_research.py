"""
Research missing company info using Apify (search + scrape) + Gemini (extraction).

Flow:
  1. Apify rag-web-browser searches Google and returns clean Markdown from top pages
  2. Markdown is fed to Gemini as context — no Google Search grounding needed
  3. Gemini extracts structured fields and returns JSON

Cost: ~$0.004 Apify + ~$0.0002 Gemini per company (vs ~$0.035 with grounding).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from apify_client import ApifyClient
from google import genai
from google.genai import types


MODEL = "models/gemini-2.5-flash"

# Valid choices — must match Django model
COMPANY_STATUS_CHOICES   = {"public", "private"}
COMPANY_MATURITY_CHOICES = {"seed", "series_a", "series_b", "series_c", "series_d_plus", "public_company"}
PRODUCT_TYPE_CHOICES     = {"b2b", "b2c", "both"}

APIFY_MAX_RESULTS  = 5   # pages to scrape per search
APIFY_MAX_CHARS    = 8000  # markdown chars to keep per result (token budget)


@dataclass
class CompanyResearchResult:
    # Basic info
    website: str = ""
    country_code: str = ""        # ISO alpha-2 e.g. "US", "JP"
    description: str = ""
    hq_address: str = ""
    logo_url: str = ""            # direct image URL to download
    contact_info: str = ""
    leaders_roles: str = ""       # founders / CEO / key leadership
    sources: str = ""

    # Classification (must match model choices)
    company_status: str = ""      # public | private
    company_maturity: str = ""    # seed | series_a | … | public_company
    product_type: str = ""        # b2b | b2c | both

    # Employees
    employee_count: int | None = None
    employee_min: int | None = None
    employee_max: int | None = None

    # Focus areas
    primary_focus: list[str] = field(default_factory=list)

    confidence: str = "low"       # low | medium | high


_SYSTEM = """\
You are a robotics industry researcher. You will be given web research results (scraped pages) \
about a company. Extract the following fields from that content:

- website: official website URL
- country_code: ISO alpha-2 headquarters country (e.g. US, JP, DE, CN, KR, SG)
- description: 2-4 sentence English description of what the company builds/does in robotics
- hq_address: headquarters city/country (full address if available)
- logo_url: direct URL to a PNG/JPG/SVG/WEBP logo (prefer official site or LinkedIn)
- contact_info: email, phone, or contact page URL
- leaders_roles: founder(s) and/or CEO name and title (e.g. "John Smith - CEO & Co-Founder")
- sources: comma-separated list of source domains used
- company_status: "public" if publicly traded, "private" if not (or "" if unknown)
- company_maturity: one of: seed, series_a, series_b, series_c, series_d_plus, public_company (or "" if unknown)
- product_type: "b2b" if sells to businesses, "b2c" if to consumers, "both" if both (or "" if unknown)
- employee_count: total headcount as integer (or null if unknown)
- employee_min: lower bound of employee range as integer (or null)
- employee_max: upper bound of employee range as integer (or null)
- primary_focus: array of focus area strings from: ["industrial", "service", "medical", "defense", \
"logistics", "agriculture", "construction", "inspection", "humanoid", "mobile", "manipulation", \
"drone", "underwater", "space", "education", "research", "ai_software"]
- confidence: "high" if most fields found, "medium" if some, "low" if little found

Only return factual information present in the research content. Leave string fields as "" and \
arrays as [] if not found. Do not fabricate. Respond ONLY with valid JSON — no markdown fences.
"""

_LOW_CONFIDENCE_DOMAINS = {
    "facebook.com", "instagram.com", "x.com", "twitter.com",
    "tiktok.com", "linkedin.com", "medium.com",
}


def _apify_search(query: str) -> str:
    """Run Apify rag-web-browser and return merged Markdown from top results."""
    api_key = os.environ.get("APIFY_API_KEY", "")
    if not api_key:
        raise RuntimeError("APIFY_API_KEY not set in environment")

    client = ApifyClient(api_key, max_retries=2)
    # apify-client 3.x renamed wait_secs -> wait_duration (timedelta)
    run = client.actor("apify/rag-web-browser").call(
        run_input={
            "query": query,
            "maxResults": APIFY_MAX_RESULTS,
            "outputFormats": ["markdown"],
            "removeCookieWarnings": True,
        },
        wait_duration=timedelta(seconds=120),
    )

    items = list(client.dataset(run.default_dataset_id).iterate_items())

    # Prefer non-social-media sources
    preferred = [
        item for item in items
        if not any(
            d in item.get("searchResult", {}).get("url", "")
            for d in _LOW_CONFIDENCE_DOMAINS
        )
    ]
    items = preferred or items

    parts = []
    for item in items:
        sr = item.get("searchResult", {})
        title = sr.get("title", "")
        url = sr.get("url", "")
        snippet = sr.get("description") or sr.get("snippet") or ""
        markdown = (item.get("markdown") or "").strip()
        if len(markdown) > APIFY_MAX_CHARS:
            markdown = markdown[:APIFY_MAX_CHARS] + "\n[truncated]"
        parts.append(f"## {title}\nURL: {url}\nSnippet: {snippet}\n\n{markdown}")

    return "\n\n---\n\n".join(parts)


def research_company(
    name: str,
    known_website: str = "",
    *,
    fields_needed: list[str] | None = None,
) -> CompanyResearchResult:
    """
    Use Apify (search+scrape) + Gemini (extraction) to find missing company info.

    Args:
        name: Company name to research.
        known_website: Existing website URL (included in search query).
        fields_needed: Which fields to look for (default: all).
    """
    fields_needed = fields_needed or [
        "website", "country_code", "description", "hq_address", "logo_url",
        "contact_info", "leaders_roles", "company_status", "company_maturity",
        "product_type", "employee_count", "employee_min", "employee_max",
        "primary_focus",
    ]

    # Build a targeted search query
    site_hint = f'site:{_domain(known_website)} OR ' if known_website else ""
    query = f'{site_hint}"{name}" robotics company headquarters employees funding'

    web_content = _apify_search(query)

    hint = f"Known website: {known_website}\n" if known_website else ""
    user_msg = (
        f"Company: {name}\n{hint}"
        f"Fields needed: {', '.join(fields_needed)}\n\n"
        f"--- Web research results ---\n\n{web_content}"
    )

    gemini = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY", ""),
        http_options={"api_version": "v1beta"},
    )
    response = gemini.models.generate_content(
        model=MODEL,
        contents=f"{_SYSTEM}\n\n{user_msg}",
        config=types.GenerateContentConfig(temperature=0.1),
    )

    return _parse_result(response.text or "")


def _domain(url: str) -> str:
    """Extract bare domain from a URL for search hints."""
    url = re.sub(r'^https?://', '', url).split('/')[0]
    return url.lstrip('www.')


def _parse_result(text: str) -> CompanyResearchResult:
    text = re.sub(r'^```[a-z]*\n?', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'```$', '', text.strip())
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return CompanyResearchResult()
    try:
        data: dict[str, Any] = json.loads(match.group())
    except json.JSONDecodeError:
        return CompanyResearchResult()

    return CompanyResearchResult(
        website=_str(data.get("website")),
        country_code=_str(data.get("country_code")).upper()[:2],
        description=_str(data.get("description")),
        hq_address=_str(data.get("hq_address")),
        logo_url=_str(data.get("logo_url")),
        contact_info=_str(data.get("contact_info")),
        leaders_roles=_str(data.get("leaders_roles")),
        sources=_str(data.get("sources")),
        company_status=_validated(data.get("company_status"), COMPANY_STATUS_CHOICES),
        company_maturity=_validated(data.get("company_maturity"), COMPANY_MATURITY_CHOICES),
        product_type=_validated(data.get("product_type"), PRODUCT_TYPE_CHOICES),
        employee_count=_int(data.get("employee_count")),
        employee_min=_int(data.get("employee_min")),
        employee_max=_int(data.get("employee_max")),
        primary_focus=_str_list(data.get("primary_focus")),
        confidence=_str(data.get("confidence", "low")),
    )


def _str(v: Any) -> str:
    return str(v).strip() if v else ""


def _validated(v: Any, choices: set[str]) -> str:
    s = _str(v).lower()
    return s if s in choices else ""


def _int(v: Any) -> int | None:
    try:
        return int(v) if v is not None and str(v).strip() not in ("", "null") else None
    except (ValueError, TypeError):
        return None


def _str_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if x]
    return []
