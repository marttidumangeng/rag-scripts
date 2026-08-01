"""Automated per-robot web research → staging JSON."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from google import genai
from google.genai import types as genai_types

from api_client import ResearchApiClient
from company_country_resolve import country_from_domain
from evidence_store import EvidenceStore, LOW_VERIFY_SCORE, sweep_company_evidence
from grounded_select import (
    MAX_IMAGE_CANDIDATES,
    confirm_product_url,
    filter_videos,
    pick_hero_image,
)

# Minimum visual confidence for the vision fallback to accept a hero. High enough
# that a hedged guess never becomes a robot's headline photo; the model is told to
# score logos/banners/other models under 30.
MIN_VISION_HERO_SCORE = 60
from release_year_lookup import citation_line, lookup_release_year
from robot_categories import derive_category_slugs
from schema import SourceRef, StagedRobot, VideoRef
from slug_utils import resolve_company_slug, slugify_company_name
from product_url_search import is_weak_product_url, search_product_url_for_robot
from estun_english_catalog import (
    ESTUN_ENGLISH_LIST_URLS,
    is_estun_website,
    lookup_estun_english_entry,
)
from hikrobot_catalog import (
    is_hikrobot_website,
    normalize_hikrobot_model,
    hikrobot_category_url_for_model,
    extract_hikrobot_tab,
    hikrobot_tab_to_page_content,
)
from tag_suggest import TagCatalog, suggest_robot_tags
from validate_staging import purpose_duplicates_description, validate_robot
from youtube_metadata import enrich_video_list
from web_extract import (
    PageContent,
    WebFetcher,
    build_image_candidates_for_pages,
    company_website_alternates,
    confirm_target_on_page,
    discover_sitemap_urls,
    extract_series_hint,
    extract_specs_from_text,
    find_youtube_on_domain,
    parse_page,
    rank_candidate_urls,
    robot_name_tokens,
    same_site,
    score_image,
    score_url_for_robot,
    search_model_name_aliases,
    select_confident_videos,
    select_hero_from_candidates,
)

RESEARCH_DIR = Path(__file__).resolve().parent
STAGING_ROBOTS = RESEARCH_DIR / "staging" / "robots"


def slugify_robot_name(name: str) -> str:
    slug = slugify_company_name(name)
    return slug or "robot"


def _join_pipe(items: list[str]) -> str:
    return "|".join(dict.fromkeys(i.strip() for i in items if i and i.strip()))


def _m2m_keys(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    return _join_pipe([str(i.get("key") or i.get("label") or "") for i in items])


def _is_blank(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, (list, dict)):
        return len(val) == 0
    return False


# CJK ranges. description must be English end-to-end — validate_robots_xlsx rejects CJK
# as a hard ERROR ("must be English; translate or remove before importing"), so a
# non-English value must never reach a staged description, not even as a fallback.
_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")


def _is_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(str(text or "")))


# Lazy-load placeholders: a blurred ~10px LQIP stand-in served until the real image
# loads. On ubtrobot.com one occupied a slot in the vision pool as a 260-byte 10x10
# blur — indistinguishable from a real photo by URL alone, useless to look at.
_LQIP_RE = re.compile(r"blur,|(?:^|[^a-z])f[wh]_\d{1,2}(?:\D|$)", re.I)


def _clean_vision_pool(urls, *, limit: int) -> list[str]:
    """Shortlist distinct, inspectable images for the vision pass.

    The raw page pool wastes the (small) candidate budget two ways: CDNs serve the
    SAME file both bare and with a query string, and lazy-load placeholders look like
    ordinary images. Measured on ubtrobot.com's uKit AI page, 8 raw slots carried one
    LQIP placeholder and three duplicate pairs — only 5 distinct photos reached the
    model, out of 19 available. Dedupe on the path (ignoring query) and drop
    placeholders so the budget buys distinct, real images.
    """
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if not url:
            continue
        base = url.split("?", 1)[0]
        if base in seen or _LQIP_RE.search(url):
            continue
        seen.add(base)
        out.append(url)
        if len(out) >= limit:
            break
    return out


def _merge_staged(
    base: StagedRobot,
    patch: StagedRobot,
    force_fields: frozenset[str] = frozenset(),
) -> StagedRobot:
    """Backfill mode: only fill blank fields on base from patch.

    Fields named in `force_fields` bypass the "only if currently blank" check and
    always take the freshly-researched value, as long as that value is non-blank —
    used to explicitly refresh fields that are populated but wrong (e.g. photos
    shared/duplicated across sibling robots), not just to fill genuinely empty ones.
    """
    data = base.to_dict()
    incoming = patch.to_dict()
    for key, val in incoming.items():
        force = key in force_fields
        if key == "sources":
            if (force or not data.get("sources")) and not _is_blank(val):
                data["sources"] = val
            continue
        if key in ("images", "video_urls", "sensors", "materials"):
            if force and _is_blank(val):
                data[key] = [] if key != "video_urls" else []
            elif (force or not data.get(key)) and not _is_blank(val):
                if key == "video_urls":
                    data[key] = [v.to_dict() if hasattr(v, "to_dict") else v for v in val]
                else:
                    data[key] = val
            continue
        if force and _is_blank(val) and key in ("image", "url"):
            data[key] = ""
            continue
        if (force or _is_blank(data.get(key))) and not _is_blank(val):
            data[key] = val
    return StagedRobot.from_dict(data)


class RobotAutoResearcher:
    def __init__(
        self,
        *,
        fetcher: WebFetcher | None = None,
        use_playwright: bool | None = None,
        use_stealth: bool | None = None,
        use_apify: bool | None = None,
        grounded: bool = False,
        max_pages: int = 12,
        tag_catalog: TagCatalog | None = None,
        client: ResearchApiClient | None = None,
    ):
        if use_stealth is None:
            use_stealth = os.environ.get("RESEARCH_USE_STEALTH", "").lower() in ("1", "true", "yes")
        self.fetcher = fetcher or WebFetcher(stealth=bool(use_stealth), apify_fallback=use_apify)
        self.client = client or ResearchApiClient()
        if use_playwright is None:
            use_playwright = os.environ.get("RESEARCH_USE_PLAYWRIGHT", "").lower() in ("1", "true", "yes")
        self.use_playwright = use_playwright
        self.max_pages = max_pages
        self.tag_catalog = tag_catalog
        # Hikrobot: cache all tabs for a family in one Playwright session so we
        # don't re-launch the browser for every robot in the same family.
        # key = family (LMR/FMR/CMR/CTU), value = dict[model → HikrobotTabResult]
        self._hikrobot_family_cache: dict[str, dict] = {}
        # Grounded selection (Gemini vision/text picks over heuristic candidates).
        # None when disabled or GEMINI_API_KEY is missing — heuristics still run.
        self.grounded_client = None
        if grounded:
            try:
                from verify_lib import gemini_client
                self.grounded_client = gemini_client()
            except Exception:
                self.grounded_client = None
            if self.grounded_client is None:
                print("  (grounded selection requested but unavailable — using heuristics)", flush=True)

    def research_robot(
        self,
        robot: dict[str, Any],
        *,
        company_slug: str,
        company_name: str,
        company_website: str,
        manufacturer_country_code: str = "",
        trust_stored_url: bool = True,
        refresh_description: bool = False,
        blocked_hero_urls: set[str] | None = None,
        evidence: EvidenceStore | None = None,
    ) -> StagedRobot | None:
        name = str(robot.get("name") or "").strip()
        model_name = str(robot.get("model_name") or name).strip()
        tokens = robot_name_tokens(name, model_name)
        robot_id = robot.get("id")
        page_paths_lean: list[str] = []

        website = (company_website or robot.get("url") or "").strip()
        if website and not website.startswith("http"):
            website = "https://" + website.lstrip("/")

        website_origins = company_website_alternates(website) if website else []
        if not website_origins and website:
            website_origins = [website.rstrip("/")]

        pages: list[PageContent] = []
        stored_url = str(robot.get("url") or "").strip()
        product_url = stored_url if trust_stored_url else ""
        estun_entry: dict[str, str] | None = None
        candidate_urls: list[str] = []

        if website_origins and is_estun_website(website_origins[0]):
            candidate_urls.extend(ESTUN_ENGLISH_LIST_URLS)
            estun_entry = lookup_estun_english_entry(name, model_name)

        for origin in website_origins:
            parsed = urlparse(origin)
            candidate_urls.extend(discover_sitemap_urls(self.fetcher, origin))
            homepage = parse_page(self.fetcher, origin, rendered=False)
            if homepage:
                pages.append(homepage)
                soup_links = re.findall(r'href=["\']([^"\']+)["\']', homepage.html)
                for link in soup_links:
                    full = link if link.startswith("http") else f"{origin.rstrip('/')}/{link.lstrip('/')}"
                    if same_site(full, parsed.netloc) and score_url_for_robot(full, tokens) > 0:
                        candidate_urls.append(full)

        if website_origins:
            parsed = urlparse(website_origins[0])
        else:
            parsed = urlparse(website) if website else None

        if stored_url and not trust_stored_url:
            if not website_origins or same_site(stored_url, urlparse(website_origins[0]).netloc):
                candidate_urls.append(stored_url)
            for alt in website_origins[1:]:
                if same_site(stored_url, urlparse(alt).netloc):
                    candidate_urls.append(stored_url)
                    break

        ranked = rank_candidate_urls(list(dict.fromkeys(candidate_urls)), tokens)
        if product_url:
            ranked = [product_url] + [u for u in ranked if u != product_url]
        elif ranked:
            product_url = ranked[0]

        home_path = urlparse(website_origins[0]).path.rstrip("/") if website_origins else ""
        if product_url and urlparse(product_url).path.rstrip("/") in ("", home_path) and ranked:
            product_url = ranked[0]

        if estun_entry and (
            not product_url
            or is_weak_product_url(product_url, website_origins[0] if website_origins else website, tokens)
        ):
            product_url = estun_entry["url"]
            print(f"         product URL via en.estun.com catalog: {product_url}", flush=True)

        # Hikrobot: SPA category pages with per-model tabs. Use Playwright to click
        # the matching tab and extract model-specific content before the normal fetch
        # pipeline runs. This bypasses the target_not_found gate for all Hikrobot models.
        # Family-level cache: all models in the same family share one Playwright session
        # (loaded once, all tabs clicked in sequence) to avoid re-launching the browser.
        hikrobot_entry: dict | None = None
        if is_hikrobot_website(website):
            from hikrobot_catalog import hikrobot_family_for_model, extract_all_hikrobot_tabs
            bare_model = normalize_hikrobot_model(name, model_name)
            cat_url = hikrobot_category_url_for_model(bare_model)
            family = hikrobot_family_for_model(bare_model) if bare_model else None
            if cat_url and family:
                # Populate family cache on first encounter
                if family not in self._hikrobot_family_cache:
                    print(f"         [hikrobot] loading all tabs for family {family!r} ...", flush=True)
                    self._hikrobot_family_cache[family] = extract_all_hikrobot_tabs(
                        family, stealth=self.fetcher.stealth
                    )
                    print(
                        f"         [hikrobot] family {family!r} cached: "
                        f"{len(self._hikrobot_family_cache[family])} tabs",
                        flush=True,
                    )
                family_tabs = self._hikrobot_family_cache.get(family, {})
                # Find the tab that matches this model (case-insensitive)
                tab_result = None
                for tab_model, tab_res in family_tabs.items():
                    if tab_model.upper() == bare_model.upper():
                        tab_result = tab_res
                        break
                if tab_result is None:
                    # Fallback: individual tab extraction (model not in family cache)
                    print(f"         [hikrobot] extracting tab for {bare_model!r} from {cat_url}", flush=True)
                    tab_result = extract_hikrobot_tab(bare_model, stealth=self.fetcher.stealth)
                if tab_result and tab_result.success:
                    hikrobot_page = hikrobot_tab_to_page_content(tab_result)
                    pages.insert(0, hikrobot_page)
                    product_url = cat_url
                    hikrobot_entry = {"url": cat_url, "model": bare_model}
                    print(
                        f"         [hikrobot] tab extracted: tab_id={tab_result.tab_id!r} "
                        f"images={len(tab_result.images)}",
                        flush=True,
                    )
                elif tab_result:
                    print(f"         [hikrobot] tab extraction failed: {tab_result.error}", flush=True)
                else:
                    print(f"         [hikrobot] Playwright unavailable for {bare_model!r}", flush=True)

        if (
            not estun_entry
            and not hikrobot_entry
            and is_weak_product_url(product_url, website_origins[0] if website_origins else website, tokens)
        ):
            searched = ""
            for alias in search_model_name_aliases(model_name):
                for site_origin in website_origins:
                    searched = search_product_url_for_robot(
                        name,
                        company_name,
                        model_name=alias,
                        company_website=site_origin,
                    )
                    if searched:
                        break
                if searched:
                    break
            if not searched:
                searched = search_product_url_for_robot(
                    name,
                    company_name,
                    model_name=model_name,
                    company_website=website_origins[0] if website_origins else website,
                )
            if searched:
                product_url = searched
                print(f"         product URL via search: {searched}", flush=True)

        fetch_urls = ranked[: self.max_pages]
        if product_url and product_url not in fetch_urls:
            fetch_urls.insert(0, product_url)

        for url in fetch_urls:
            page = parse_page(self.fetcher, url, rendered=self.use_playwright)
            if page:
                pages.append(page)
            if product_url and not product_url.startswith("http"):
                product_url = url

        # Lean evidence: parsed text for every fetched page (enrich provenance).
        if evidence and pages:
            for page in pages:
                entry = evidence.save_page(
                    page.url,
                    text=page.text or "",
                    title=page.title or "",
                    source="playwright" if self.use_playwright else "fetch",
                    robot_id=robot_id,
                    lean=True,
                )
                page_paths_lean.append(entry["path"])

        # Grounded URL check: the pages are already fetched, so asking the model
        # "is this THIS robot's product page?" costs one text call and catches the
        # catalog-page / sibling-model URLs that token heuristics wave through.
        grounded_url_payload: dict[str, Any] | None = None
        if self.grounded_client and product_url and pages:
            product_url, grounded_url_payload = self._grounded_product_url(
                product_url, pages, name=name, model_name=model_name, company_name=company_name,
            )
            if evidence and grounded_url_payload is not None:
                evidence.save_extract(
                    product_url or (pages[0].url if pages else ""),
                    grounded_url_payload,
                    extractor="gemini_confirm_product_url",
                    robot_id=robot_id,
                )

        # Fail closed: when we fetched pages for a claimed product URL, the robot
        # name/model must appear somewhere in that evidence. Otherwise skip rather
        # than staging whole-page heroes/specs for the wrong model.
        # Hikrobot: skip the gate — the tab extractor already confirmed the model
        # by clicking its named tab; the text is pre-seeded with the model name.
        if (
            not estun_entry
            and not hikrobot_entry
            and product_url
            and pages
            and not any(confirm_target_on_page(name, model_name, p) for p in pages)
        ):
            print(
                f"         SKIP target_not_found: {name!r} not confirmed on fetched pages "
                f"(product_url={product_url})",
                flush=True,
            )
            if evidence:
                html_paths: list[str] = []
                for page in pages:
                    entry = evidence.save_page(
                        page.url,
                        html=page.html or "",
                        text=page.text or "",
                        title=page.title or "",
                        source="enrich_target_not_found",
                        robot_id=robot_id,
                        lean=False,
                        force_html=True,
                    )
                    html_paths.append(entry["path"])
                evidence.note_target_not_found(
                    product_url,
                    name,
                    detail="name/model not confirmed on fetched pages",
                    robot_id=robot_id,
                    page_paths=html_paths or page_paths_lean,
                )
            return None

        all_videos: list[str] = []
        combined_text = ""
        product_text = ""
        best_description = ""

        for page in pages:
            all_videos.extend(page.video_urls)
            if "/blog/" in page.url.lower() or "/resource/" in page.url.lower():
                continue
            # main_text, not text: this text drives specs, classification, movement and
            # features, and every one of those consumers truncates it. Full page text is
            # mostly site chrome — avinc.com's mega-menu alone is ~9k chars, so the nav
            # filled _classify_robot's 2500-char window and an underwater ROV was
            # classified "flying". Fall back to text when a page has no main content.
            page_text = page.main_text or page.text
            combined_text += " " + page_text
            if page.url == product_url or (product_url and product_url.rstrip("/") in page.url.rstrip("/")):
                if (page.meta_description
                        and not _is_cjk(page.meta_description)
                        and len(page.meta_description) > len(best_description)):
                    best_description = page.meta_description
                if len(page_text) > len(product_text):
                    product_text = page_text

        # Facts about THIS robot come from its own product page. combined_text concatenates
        # every crawled page, so a sibling's numbers bleed in — that is how Ally (an
        # underwater ROV) staged as "aerial|swimming|wheeled" carrying another model's
        # 16.8 kg payload. Only fall back to the concatenation when no product page matched.
        source_text = product_text or combined_text
        # No keyword gate: features used to be extracted only if the page contained one of
        # ("payload", "runtime", "lumabot", "put-to-light") — two of them single-company
        # hacks — so Ally's "300-meter depth rating" and "manipulator lifts up to 21 lbs"
        # yielded nothing, leaving `differentiator` to fall back to a stray spec.
        best_features = source_text[:1200]

        all_videos = list(dict.fromkeys(all_videos + find_youtube_on_domain(self.fetcher, pages)))

        youtube_search = search_youtube_videos_for_robot(
            name, company_name, model_name=model_name, company_website=website,
        )
        all_videos = list(dict.fromkeys(youtube_search["video_urls"] + all_videos))

        image_pages = pages
        if estun_entry and estun_entry.get("image"):
            image_pages = [
                PageContent(
                    url=estun_entry.get("url") or product_url,
                    html="",
                    text=f"{name} {model_name}",
                    title=f"{name} {model_name}",
                    images=[estun_entry["image"]],
                ),
                *pages,
            ]
        filtered_image_pages = [
            PageContent(
                url=page.url,
                html=page.html,
                text=page.text,
                title=page.title,
                meta_description=page.meta_description,
                images=[
                    image_url
                    for image_url in page.images
                    if image_url not in (blocked_hero_urls or set())
                ],
                video_urls=page.video_urls,
                # Both must be carried over: this rebuild constructs fresh PageContent
                # objects, so anything not named here is silently lost. Dropping
                # main_images sent the whole-page pool (other products' nav thumbnails
                # included) to the vision pass; dropping model_scoped re-breaks
                # model-scoped image selection.
                main_images=[
                    image_url
                    for image_url in (getattr(page, "main_images", None) or [])
                    if image_url not in (blocked_hero_urls or set())
                ],
                model_scoped=getattr(page, "model_scoped", False),
            )
            for page in image_pages
        ]
        image_candidates = build_image_candidates_for_pages(
            filtered_image_pages,
            product_url=product_url,
            name=name,
            model_name=model_name,
            tokens=tokens,
            company_name=company_name,
        )

        # Vision fallback. The scored ladder verifies a photo by finding the model
        # token in its URL, which yields NOTHING on OEMs that serve CMS/date/hash
        # filenames — hikrobotics.com and ubtrobot.com both do, so `missing_image`
        # was unfixable there even though the pages carry good photos. When scoring
        # finds nothing, let the model look at the actual pixels instead: it is the
        # only signal left once filenames carry no information.
        # Deliberately a FALLBACK, not a replacement — when token scoring did produce
        # candidates, provenance stays authoritative and vision only reorders (below).
        if not image_candidates and self.grounded_client:
            # The PRODUCT page's own images must come first. The candidate budget is
            # small (MAX_IMAGE_CANDIDATES), and pages arrive in crawl order — on the
            # uKit AI run, banner images from other pages (2025/2026 .jpg) filled all 8
            # slots and every one scored 0, while the product page's actual photos
            # (2024 .png, later scored 95) never reached the model at all.
            def _is_product_page(page) -> bool:
                if not product_url:
                    return False
                page_url = (page.url or "").split("?", 1)[0].rstrip("/")
                target = product_url.split("?", 1)[0].rstrip("/")
                return bool(page_url) and (page_url == target or page_url in target or target in page_url)

            ordered_pages = sorted(filtered_image_pages, key=lambda pg: not _is_product_page(pg))
            pool = _clean_vision_pool(
                (
                    url
                    for page in ordered_pages
                    # main_images first: nav-scoped, so it excludes OTHER products'
                    # thumbnails that would otherwise be offered to the model.
                    for url in (page.main_images or page.images)
                ),
                limit=MAX_IMAGE_CANDIDATES,
            )
            if pool:
                vision = pick_hero_image(
                    self.grounded_client,
                    self.fetcher.session,
                    name=name,
                    model_name=model_name,
                    company_name=company_name,
                    description=best_description,
                    candidates=pool,
                )
                hero = (vision or {}).get("hero") or ""
                hero_score = (vision or {}).get("scores", {}).get(hero)
                # hero="" means the model looked and rejected everything — honour that
                # rather than falling back, and require a confident score so a weak
                # guess never becomes a robot's headline photo.
                if hero and isinstance(hero_score, (int, float)) and hero_score >= MIN_VISION_HERO_SCORE:
                    approved = [hero, *[
                        url for url in (vision.get("gallery") or [])
                        if (vision.get("scores", {}).get(url) or 0) >= MIN_VISION_HERO_SCORE
                    ]]
                    # Route through the normal candidate builder via a model_scoped
                    # page: vision has done the disambiguation filename matching could
                    # not, so provenance/confidence scoring still applies as usual.
                    image_candidates = build_image_candidates_for_pages(
                        [PageContent(url=product_url or website, html="",
                                     images=approved, model_scoped=True)],
                        product_url=product_url,
                        name=name,
                        model_name=model_name,
                        tokens=tokens,
                        company_name=company_name,
                    )
                    print(
                        f"         vision image pick: hero={hero_score}/100 "
                        f"approved={len(approved)} from pool={len(pool)}",
                        flush=True,
                    )
                elif vision is None:
                    # None means grounding could not RUN (client/download/API failure) —
                    # a different thing from "looked and rejected", and conflating the
                    # two hides real breakage as if it were a clean negative verdict.
                    print(
                        f"         vision image pick: UNAVAILABLE (could not run) pool={len(pool)}",
                        flush=True,
                    )
                else:
                    best = max((vision.get("scores") or {}).values(), default=None)
                    print(
                        f"         vision image pick: rejected all {len(pool)} candidates"
                        f" (best {best}/100, need {MIN_VISION_HERO_SCORE})",
                        flush=True,
                    )

        # Grounded image pick: let the model look at the actual pixels of the
        # scored candidates. It may only reorder candidates already in the core
        # ladder; structured provenance and confidence remain authoritative.
        grounded_hero_score: int | None = None
        if self.grounded_client:
            candidates = [candidate["url"] for candidate in image_candidates]
            picked = pick_hero_image(
                self.grounded_client,
                self.fetcher.session,
                name=name,
                model_name=model_name,
                company_name=company_name,
                description=best_description,
                candidates=candidates,
            )
            if picked is not None:
                preferred_urls = [
                    url
                    for url in [picked.get("hero"), *(picked.get("gallery") or [])]
                    if url in candidates
                ]
                preferred = set(preferred_urls)
                image_candidates = sorted(
                    image_candidates,
                    key=lambda candidate: (
                        preferred_urls.index(candidate["url"])
                        if candidate["url"] in preferred
                        else len(preferred_urls)
                    ),
                )
                grounded_hero_score = (
                    picked["scores"].get(picked.get("hero"))
                    if picked.get("hero") in candidates
                    else None
                )
                print(
                    f"         grounded image reorder: hero={'YES (' + str(grounded_hero_score) + '/100)' if picked.get('hero') in candidates else 'none passed'}"
                    f", preferred={len(preferred)}",
                    flush=True,
                )
                if evidence:
                    evidence.save_extract(
                        product_url or (pages[0].url if pages else website or ""),
                        {
                            "request": {
                                "name": name,
                                "model_name": model_name,
                                "candidates": candidates,
                            },
                            "response": picked,
                        },
                        extractor="gemini_pick_hero_image",
                        robot_id=robot_id,
                    )
                    # Low grounded image score → keep raw HTML for audit
                    low_scores = [
                        s for s in (picked.get("scores") or {}).values()
                        if isinstance(s, (int, float)) and s < LOW_VERIFY_SCORE
                    ]
                    if (grounded_hero_score is not None and grounded_hero_score < LOW_VERIFY_SCORE) or (
                        not picked.get("hero") and low_scores
                    ):
                        for page in pages:
                            evidence.save_page(
                                page.url,
                                html=page.html or "",
                                text=page.text or "",
                                title=page.title or "",
                                source="enrich_low_verify_score",
                                robot_id=robot_id,
                                lean=False,
                                force_html=True,
                            )

        if estun_entry and estun_entry.get("url"):
            product_url = estun_entry["url"]
        if hikrobot_entry and hikrobot_entry.get("url"):
            product_url = hikrobot_entry["url"]

        hero_image = select_hero_from_candidates(image_candidates)
        gallery_images = [
            candidate["url"]
            for candidate in image_candidates
            if candidate.get("url") and candidate["url"] != hero_image
        ][:5]

        enriched_videos = enrich_video_list(all_videos[:15], session=self.fetcher.session)
        confident_videos = None
        if self.grounded_client:
            confident_videos = filter_videos(
                self.grounded_client,
                name=name,
                model_name=model_name,
                company_name=company_name,
                videos=enriched_videos,
            )
        if confident_videos is None:  # grounding unavailable/failed — heuristic fallback
            confident_videos = select_confident_videos(enriched_videos, tokens)
        video_refs = [VideoRef.from_item(v) for v in confident_videos if VideoRef.from_item(v)]

        specs = extract_specs_from_text(source_text)

        sources: list[SourceRef] = []
        if estun_entry and estun_entry.get("url"):
            sources.append(SourceRef(url=estun_entry["url"], type="website", title="Product page"))
        else:
            if product_url:
                sources.append(SourceRef(url=product_url, type="website", title="Product page"))
            if website and website != product_url:
                sources.append(SourceRef(url=website, type="website", title="Manufacturer website"))
            if youtube_search["channel_url"]:
                sources.append(SourceRef(url=youtube_search["channel_url"], type="video", title="Official YouTube channel"))
            for page in pages[:3]:
                if page.url not in {s.url for s in sources}:
                    sources.append(SourceRef(url=page.url, type="website"))

        # On a description refresh the stored value is known-bad, so it must not seed
        # anything — including purpose, which must never be re-derived from it.
        stored_description = "" if refresh_description else str(robot.get("description") or "").strip()
        description = stored_description or best_description
        purpose = "" if refresh_description else str(robot.get("purpose") or "").strip()
        # A stored purpose that merely repeats the description is the old pipeline's bug
        # (purpose used to be `description.split(".")[0]`). Drop it so it gets regenerated
        # as a real task statement below instead of being carried forward.
        if purpose and purpose_duplicates_description(purpose, description):
            purpose = ""

        # Use Gemini to classify movement types, sub-category, uses, industries
        classification = _classify_robot(name, source_text)
        if evidence:
            evidence.save_extract(
                product_url or website or "",
                {
                    "request": {"name": name, "text_preview": (source_text or "")[:800]},
                    "response": classification,
                },
                extractor="gemini_classify",
                robot_id=robot_id,
            )

        # Fall back to existing DB values if Gemini returns nothing
        movement_types = (
            "|".join(classification.get("movement_types") or [])
            or _m2m_keys(robot.get("movement_types"))
            or _infer_movement(name, source_text)
        )
        sub_category = (
            classification.get("sub_category")
            or _infer_sub_category(name, source_text)
        )
        industry_keys = (
            "|".join(classification.get("industries") or [])
            or _m2m_keys(robot.get("industries"))
        )
        use_keys = (
            "|".join(classification.get("uses") or [])
            or _m2m_keys(robot.get("uses"))
        )

        # Purpose is its own field, sourced from the page's stated task — never a slice of
        # the description (that produced purpose==description across the catalog). Order:
        # keep a good stored value, else the classifier's task phrase, else a deterministic
        # phrase from the taxonomy. Blank beats a duplicate: `missing_purpose` is a warning,
        # a purpose that parrots the description is misinformation.
        if not purpose:
            purpose = classification.get("purpose") or _purpose_from_taxonomy(use_keys, sub_category)
        if purpose and purpose_duplicates_description(purpose, description):
            purpose = _purpose_from_taxonomy(use_keys, sub_category)
            if purpose and purpose_duplicates_description(purpose, description):
                purpose = ""

        # `sub_category` resolves to RobotSubCategory ("Applications"), which is NOT
        # the Category M2M that `quality.missing_category` counts — so classifying a
        # robot never used to give it a category, and the flag stayed up through any
        # number of re-enrichments. Derive the Category assignment from the same
        # signals, against a fixed vocabulary of slugs that already exist on prod.
        # `fallback="other"` is honest here and only here: we have fetched and read
        # the product page, so "nothing matched" is a finding, not a blank.
        category_slugs = derive_category_slugs(
            name=name,
            text=source_text or "",
            movement_type_keys=movement_types,
            sub_category_slug=sub_category,
            use_keys=use_keys,
            industry_keys=industry_keys,
            existing=_category_slugs_from_robot(robot),
            fallback="other" if source_text else "",
        )

        staged = StagedRobot(
            name=name,
            model_name=model_name,
            company_slug=company_slug,
            company_name=company_name,
            # Order: caller's value (the company's country) -> whatever the robot
            # already had -> the company domain's ccTLD. The ccTLD tier is free and
            # offline, and it is the difference between a blank field and a correct
            # one for every manufacturer on a .jp/.de/.cn domain whose Company row
            # nobody has filled in yet. Anything less certain is left to
            # `resolve_company_country`, which fixes the Company instead.
            manufacturer_country_code=(
                manufacturer_country_code
                or _country_code_from_robot(robot)
                or country_from_domain(company_website)
            ),
            # On a URL refresh, a failed re-derivation must stage a blank URL (not the homepage)
            # so _merge_staged keeps the DB value instead of force-overwriting it with junk.
            url=product_url or (website if trust_stored_url else ""),
            image=hero_image,
            images=image_candidates,
            video_urls=video_refs,
            description=description,
            purpose=purpose,
            features=_summarize_features(best_features),
            availability_status_key=_key_from_obj(robot.get("availability_status"), "available"),
            movement_type_keys=movement_types,
            industry_keys=industry_keys,
            use_keys=use_keys,
            sub_category_slug=sub_category,
            category_slugs=category_slugs,
            payload_kg=specs.get("payload_kg") if isinstance(specs.get("payload_kg"), (int, float)) else None,
            reach_mm=specs.get("reach_mm") if isinstance(specs.get("reach_mm"), (int, float)) else None,
            repeatability_mm=specs.get("repeatability_mm") if isinstance(specs.get("repeatability_mm"), (int, float)) else None,
            dof=specs.get("dof") if isinstance(specs.get("dof"), int) else None,
            voltage=str(specs.get("voltage") or ""),
            weight_kg=specs.get("weight_kg") if isinstance(specs.get("weight_kg"), (int, float)) else None,
            speed=specs.get("speed") if isinstance(specs.get("speed"), (int, float)) else None,
            speed_ms=specs.get("speed_ms") if isinstance(specs.get("speed_ms"), (int, float)) else None,
            runtime=str(specs.get("runtime") or ""),
            runtime_minutes=specs.get("runtime_minutes") if isinstance(specs.get("runtime_minutes"), int) else None,
            programming_interface=classification.get("programming_interface", ""),
            safety_fencing=classification.get("safety_fencing", ""),
            mounting_options=classification.get("mounting_options", ""),
            deployment_context=classification.get("deployment_context", ""),
            ecosystem_compatibility=classification.get("ecosystem_compatibility", ""),
            sources=sources,
            confidence={},
            research_notes=_build_research_notes(hero_image, gallery_images, video_refs, self.use_playwright),
        )

        movement = staged.movement_type_keys or _infer_movement(name, source_text)
        staged.movement_type_keys = movement
        if not staged.tags.strip():
            catalog = self.tag_catalog
            if catalog is None:
                try:
                    catalog = TagCatalog.load(self.client)
                    self.tag_catalog = catalog
                except Exception:
                    catalog = None
            if catalog and catalog.tags:
                staged.tags = suggest_robot_tags(staged, catalog)

        # Family / variant, from the vendor's OWN taxonomy (breadcrumb or "<X> Series"
        # wording on the product page). Nothing in discovery or enrichment ever set
        # these before, so every family value in the DB came from a hand-written
        # retrofit — see feedback_discovery_include_family_data. Only fills blanks:
        # a curated family already on the robot always wins. `family_key` is left to
        # the server, which derives {company_slug}:{slug(family_name)} on import.
        if not str(robot.get("family_name") or "").strip():
            series_html = ""
            for page in pages:
                if product_url and page.url and page.url.split("?", 1)[0].rstrip("/") in product_url:
                    series_html = page.html
                    break
            series = extract_series_hint(series_html or (pages[0].html if pages else ""), robot_name=name)
            if series:
                staged.family_name = series
                remainder = name[len(series):].strip(" -–—:") if name.lower().startswith(series.lower()) else ""
                if remainder:
                    staged.variant_label = remainder
                print(f"         family: {series!r} variant={remainder or '(base)'!r} [vendor taxonomy]", flush=True)

        # Release year: not on product pages — needs a search-grounded lookup against
        # press releases / dated docs. Only runs when the DB value is blank (patch-mode
        # merge would ignore it otherwise), and only stages a year that carries a
        # citation, which goes into research_notes for human audit.
        if not robot.get("release_year"):
            try:
                year_hit = lookup_release_year(name, company_name, model_name=model_name)
            except Exception:
                year_hit = None
            if year_hit:
                staged.release_year = year_hit["year"]
                staged.confidence["release_year"] = year_hit["confidence"]
                staged.research_notes = (
                    (staged.research_notes + "\n" if staged.research_notes else "")
                    + citation_line(year_hit)
                )
                print(f"         release year: {year_hit['year']} [{year_hit['confidence']}]", flush=True)

        # Content-brief description: when the DB had no description, replace the
        # scraped meta-description fallback with a validated brief-style one
        # written from the collected facts (same generator as the server-side
        # admin button — see description_lib). Runs last so the facts (taxonomy,
        # specs, release year) are as complete as this enrichment pass gets.
        if refresh_description or not str(robot.get("description") or "").strip():
            try:
                from description_lib import generate_for_staged

                gen = generate_for_staged(staged)
            except Exception:
                gen = None
            if gen:
                staged.description = gen["text"]
                staged.confidence["description"] = "medium"
                # Purpose is NOT derived from this generated description — doing so is what
                # produced purpose==description at scale. If it is still blank here, the
                # taxonomy is the only honest source; otherwise leave it blank and let the
                # `missing_purpose`/`purpose_duplicates_description` flags surface it.
                if not staged.purpose:
                    staged.purpose = _purpose_from_taxonomy(staged.use_keys, staged.sub_category_slug)
                if staged.purpose and purpose_duplicates_description(staged.purpose, staged.description):
                    staged.purpose = ""
                print(
                    f"         brief description generated "
                    f"({gen['model'].split('/')[-1]}, {len(gen['text'].split())} words)",
                    flush=True,
                )

        # Last line of defence. The generator answers in the language of the facts it is
        # given, so a CJK fact slot yields a CJK description that passes every other check
        # (it is distinct, on-brief, banner-free) and only fails at import. Blank it rather
        # than stage it: _merge_staged then keeps the DB value instead of writing non-English.
        if _is_cjk(staged.description):
            staged.description = ""
            print("         description dropped — non-English output", flush=True)
        if _is_cjk(staged.purpose):
            staged.purpose = ""

        if staged.payload_kg:
            staged.confidence["payload_kg"] = "high"
        if staged.runtime:
            staged.confidence["runtime"] = "medium"
        if staged.image:
            if grounded_hero_score is not None:
                # Visual confirmation beats filename heuristics.
                staged.confidence["image"] = "high" if grounded_hero_score >= 85 else "medium"
            else:
                img_score = score_image(staged.image, tokens)
                staged.confidence["image"] = "high" if img_score >= 16 else "medium"

        if evidence:
            evidence.link_robot(
                product_url or (pages[0].url if pages else website or ""),
                name,
                robot_id=robot_id,
            )

        return staged

    def _grounded_product_url(
        self,
        product_url: str,
        pages: list[PageContent],
        *,
        name: str,
        model_name: str,
        company_name: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Confirm the heuristic product_url against its fetched page; when it fails,
        promote the best-scoring alternative among the other fetched pages. Keeps the
        heuristic choice when grounding can't run or nothing scores better.

        Returns (chosen_url, evidence_payload_or_none).
        """

        scores: dict[str, Any] = {}

        def page_for(url: str) -> PageContent | None:
            target = url.rstrip("/")
            for page in pages:
                if page.url.rstrip("/") == target or target in page.url.rstrip("/"):
                    return page
            return None

        def score_page(page: PageContent) -> int | None:
            result = confirm_product_url(
                self.grounded_client,
                name=name,
                model_name=model_name,
                company_name=company_name,
                page_url=page.url,
                page_title=page.title,
                page_text=page.text,
            )
            if result:
                scores[page.url] = {"score": result[0], "reason": result[1]}
                return result[0]
            return None

        current = page_for(product_url)
        current_score = score_page(current) if current else None
        payload: dict[str, Any] = {
            "request": {
                "name": name,
                "model_name": model_name,
                "company_name": company_name,
                "initial_product_url": product_url,
            },
            "response": {"scores": scores, "chosen_url": product_url},
        }
        if current_score is None or current_score >= 50:
            payload["response"]["chosen_url"] = product_url
            return product_url, payload if scores else None

        best_url, best_score = product_url, current_score
        checked = 0
        for page in pages:
            if checked >= 4:
                break
            if page is current or "/blog/" in page.url.lower() or "/resource/" in page.url.lower():
                continue
            score = score_page(page)
            checked += 1
            if score is not None and score > best_score:
                best_url, best_score = page.url, score
                if score >= 85:
                    break
        if best_url != product_url:
            print(
                f"         grounded URL check: {product_url} scored {current_score}/100 — "
                f"switched to {best_url} ({best_score}/100)",
                flush=True,
            )
        payload["response"] = {
            "scores": scores,
            "chosen_url": best_url,
            "initial_score": current_score,
            "best_score": best_score,
        }
        return best_url, payload

    def write_staging_file(self, staged: StagedRobot, company_slug: str) -> Path:
        out_dir = STAGING_ROBOTS / company_slug
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{slugify_robot_name(staged.name)}.json"
        path.write_text(json.dumps(staged.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path


def _country_code_from_robot(robot: dict[str, Any]) -> str:
    ref = robot.get("manufacturer_country_ref") or {}
    if isinstance(ref, dict):
        return str(ref.get("code") or "").upper()
    return ""


def _category_slugs_from_robot(robot: dict[str, Any]) -> str:
    """Existing categories as a pipe-joined string.

    The API serializes `categories` as display NAMES ("Industrial-Robot"), not
    slugs; `derive_category_slugs` normalizes either form, and the importer
    slugifies whatever it is sent, so names round-trip to the same rows.
    """
    cats = robot.get("categories")
    if not isinstance(cats, list):
        return ""
    out = []
    for c in cats:
        val = c.get("name") or c.get("slug") if isinstance(c, dict) else c
        if val:
            out.append(str(val))
    return "|".join(out)


def _key_from_obj(obj: Any, default: str = "") -> str:
    if isinstance(obj, dict):
        return str(obj.get("key") or default)
    return default


_VALID_MOVEMENT_TYPES = {"wheeled", "legged", "aerial", "tracked", "stationary", "swimming", "other"}
_VALID_SUB_CATEGORIES = {
    "personal-assistants", "service-hospitality", "personal-mobility",
    "retail-customer-engagement", "learning", "logistics-warehouse",
    "agriculture", "companionship", "manufacturing-industrial",
    "cleaning-facilities", "security", "healthcare", "military",
}
_VALID_USES = {
    "assembly", "cleaning", "entertainment", "exploration", "other", "others",
    "palletizing", "pick-and-place", "research", "surgery", "cooking", "delivery",
    "guiding", "helping", "inspection", "inventory", "monitoring", "patrol",
    "picking", "reception", "remote", "sanitizing", "scanning", "transport", "education",
}
_VALID_INDUSTRIES = {
    "adult", "defence", "others", "research", "space", "agriculture", "airports",
    "cleaning", "construction", "education", "healthcare", "homes", "hotels",
    "logistics", "manufacturing", "restaurants", "retail", "story", "security",
}

_CLASSIFY_SYSTEM = """\
You are a robotics catalog classifier. Given a robot's name and a snippet of its product page, \
return a JSON object with these fields:

- "movement_types": array of movement types from: ["wheeled","legged","aerial","tracked","stationary","swimming","other"]
- "sub_category": single slug from: ["personal-assistants","service-hospitality","personal-mobility",
  "retail-customer-engagement","learning","logistics-warehouse","agriculture","companionship",
  "manufacturing-industrial","cleaning-facilities","security","healthcare","military"]
- "uses": array of use keys from: ["assembly","cleaning","entertainment","exploration","other","others",
  "palletizing","pick-and-place","research","surgery","cooking","delivery","guiding","helping",
  "inspection","inventory","monitoring","patrol","picking","reception","remote","sanitizing",
  "scanning","transport","education"]
- "industries": array of industry keys from: ["adult","defence","others","research","space",
  "agriculture","airports","cleaning","construction","education","healthcare","homes","hotels",
  "logistics","manufacturing","restaurants","retail","story","security"]
- "purpose": a SHORT phrase (max 120 chars) naming what this robot is FOR — its primary
  task. NOT a summary of the page and NOT a sentence copied from the product description.
  Write it as a task, e.g. "Hotel room-service delivery", "Spot welding in automotive body
  shops", "Short-range reconnaissance and surveillance". No brand name, no marketing
  adjectives, no trailing period. Return "" if the page does not state a clear task.
Also return these five optional narrative string fields (use "" for any the page does not
mention; never invent information not present in the text):
    - "programming_interface": how the robot is programmed or taught (e.g. "Drag-and-drop
      tablet UI, no coding required" or "UR Script / Polyscope 5"). Max 120 chars.
    - "safety_fencing": whether a safety fence/cage is required (e.g. "Not required in
      collaborative mode" or "Full perimeter fencing required"). Max 120 chars.
    - "mounting_options": supported mounting orientations (e.g. "Floor, wall, ceiling,
      inverted"). Max 80 chars.
    - "deployment_context": typical installation or deployment time/effort (e.g.
      "Operational within a single shift"). Max 120 chars.
    - "ecosystem_compatibility": certified accessories, partner ecosystem, or integration
      standards (e.g. "300+ UR+ certified accessories", "ROS 2 compatible"). Max 150 chars.

Only return values from the lists above for taxonomy fields. Return empty arrays [] if
genuinely uncertain. Use "" for any narrative field not stated on the page.
Respond ONLY with valid JSON — no markdown, no explanation.

Example:
{"movement_types":["wheeled"],"sub_category":"service-hospitality","uses":["delivery","guiding"],"industries":["hotels","restaurants"],"purpose":"Hotel room-service delivery","programming_interface":"Mobile app, no coding required","safety_fencing":"Not required","mounting_options":"","deployment_context":"","ecosystem_compatibility":""}
"""


def _classify_robot(name: str, text: str) -> dict[str, Any]:
    """Use Gemini to infer movement types, sub-category, uses, and industries from page text."""
    snippet = f"Robot: {name}\n\n{text[:2500]}"
    try:
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            http_options={"api_version": "v1beta"},
        )
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=f"{_CLASSIFY_SYSTEM}\n\n{snippet}",
            config=genai_types.GenerateContentConfig(temperature=0.0),
        )
        raw = (response.text or "").strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
    except Exception:
        return {}

    def _filter(values: Any, valid: set) -> list[str]:
        if not isinstance(values, list):
            return []
        return [v for v in values if isinstance(v, str) and v in valid]

    purpose = data.get("purpose")
    purpose = purpose.strip().rstrip(".") if isinstance(purpose, str) else ""

    # Sanitize the flat narrative fields — keep strings, truncate to per-field limits.
    _NARRATIVE_LIMITS = {
        "programming_interface": 120,
        "safety_fencing": 120,
        "mounting_options": 80,
        "deployment_context": 120,
        "ecosystem_compatibility": 150,
    }
    narrative = {}
    for key, max_len in _NARRATIVE_LIMITS.items():
        val = data.get(key)
        narrative[key] = val.strip()[:max_len] if isinstance(val, str) and val.strip() else ""

    return {
        "movement_types": _filter(data.get("movement_types"), _VALID_MOVEMENT_TYPES),
        "sub_category": _one_of(data.get("sub_category"), _VALID_SUB_CATEGORIES),
        "uses": _filter(data.get("uses"), _VALID_USES),
        "industries": _filter(data.get("industries"), _VALID_INDUSTRIES),
        "purpose": purpose[:200],
        **narrative,
    }


def _one_of(value: Any, allowed: Any) -> str:
    """One allowed key from a model field that is *supposed* to be a single string.

    The model sometimes answers with a LIST where the schema asks for one value, and
    the previous bare `value in allowed` test raised `TypeError: unhashable type:
    'list'` — which propagated out of `_classify_robot` and aborted that robot's
    ENTIRE research pass. Measured on the first continuous run: 3 of 64 robots lost
    per cycle (DJI, UBTech, ...) purely to this. Every neighbouring field is already
    type-guarded; this one was not. Recover the first valid entry rather than
    discarding the robot, and never let a malformed response raise.
    """
    if isinstance(value, str):
        return value if value in allowed else ""
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item in allowed:
                return item
    return ""


def _purpose_from_taxonomy(use_keys: str, sub_category: str) -> str:
    """Deterministic fallback purpose built from the classified taxonomy.

    Used only when the model returns no purpose — still a real task statement rather than
    a slice of the description.
    """
    uses = [u.replace("-", " ").strip() for u in (use_keys or "").split("|") if u.strip()]
    uses = [u for u in uses if u not in ("other", "others")]
    if not uses:
        return ""
    tasks = ", ".join(u.capitalize() if i == 0 else u for i, u in enumerate(uses[:3]))
    context = (sub_category or "").replace("-", " ").strip()
    return f"{tasks} in {context}"[:200] if context else tasks[:200]


_YOUTUBE_HOST_RE = re.compile(r"(?:^|\.)(?:youtube\.com|youtu\.be)$", re.I)
_YOUTUBE_CHANNEL_PATH_RE = re.compile(r"^/(@[\w.-]+|channel/|c/)", re.I)
_YOUTUBE_VIDEO_PATH_RE = re.compile(r"watch\?v=|^/shorts/", re.I)


def _resolve_grounding_url(uri: str, *, timeout: int = 10) -> str:
    """Grounding chunks give a Google redirect URL (vertexaisearch.cloud.google.com/...), not
    the real destination — must resolve it to know if it's actually a YouTube link."""
    try:
        resp = requests.head(uri, timeout=timeout, allow_redirects=True)
        if resp.status_code >= 400:
            resp = requests.get(uri, timeout=timeout, allow_redirects=True, stream=True)
            resp.close()
        return resp.url
    except requests.RequestException:
        return ""


def search_youtube_videos_for_robot(
    robot_name: str,
    company_name: str,
    *,
    model_name: str = "",
    company_website: str = "",
    max_videos: int = 5,
) -> dict[str, Any]:
    """Use Gemini + Google Search grounding to find the company's official YouTube channel and
    videos specifically about this robot. A single grounded search naturally covers both cases
    the research agent needs: official-channel videos when they exist, and third-party
    robotics/AI creator coverage when they don't (it's a general web search, not scoped to one
    channel) — falling back to page-scraped videos entirely is what causes sibling product
    variants sharing one page to end up with identical, often irrelevant, video picks.

    Real URLs come from the response's grounding citations (real search results), not from the
    model's own free-text — asking the model to transcribe a specific video URL/ID from memory
    is what caused it to hallucinate a fake video ID and get stuck in a repetition loop until
    MAX_TOKENS. thinking_budget=0 is also required: with thinking enabled, Flash spent its
    entire output budget on hidden reasoning for this grounded query and never emitted an
    answer at all (finish_reason=MAX_TOKENS with zero visible text and zero grounding chunks).
    """
    disambiguation = f' (website: {company_website})' if company_website else ''
    prompt = f"""Search for the official YouTube channel of "{company_name}"{disambiguation} and any \
YouTube videos showing or demoing the robot "{robot_name}" (model: {model_name or robot_name}).
Briefly summarize in 2-3 sentences what you found: the channel name/handle, and whether you found \
robot-specific videos or only generic company videos. Do not fabricate URLs or video IDs."""

    try:
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            http_options={"api_version": "v1beta"},
        )
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=800,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
            ),
        )
        grounding = response.candidates[0].grounding_metadata if response.candidates else None
        chunks = grounding.grounding_chunks if grounding else None
    except Exception:
        return {"channel_url": "", "video_urls": []}

    channel_url = ""
    video_urls: list[str] = []
    seen: set[str] = set()
    for chunk in chunks or []:
        web = getattr(chunk, "web", None)
        if not web or not web.uri:
            continue
        resolved = _resolve_grounding_url(web.uri)
        if not resolved:
            continue
        parsed = urlparse(resolved)
        if not _YOUTUBE_HOST_RE.search(parsed.netloc):
            continue
        if not channel_url and _YOUTUBE_CHANNEL_PATH_RE.match(parsed.path):
            channel_url = resolved
        elif _YOUTUBE_VIDEO_PATH_RE.search(resolved) and resolved not in seen:
            seen.add(resolved)
            video_urls.append(resolved)

    return {"channel_url": channel_url, "video_urls": video_urls[:max_videos]}


def _infer_movement(name: str, text: str) -> str:
    """Keyword fallback for movement type (used when Gemini classification isn't available)."""
    blob = f"{name} {text}".lower()
    if any(x in blob for x in ("quadruped", "legged", "biped")):
        return "legged"
    if any(x in blob for x in ("drone", "aerial", "uav")):
        return "aerial"
    if any(x in blob for x in ("tracked",)):
        return "tracked"
    if any(x in blob for x in ("arm", "manipulator", "cobot", "stationary")):
        return "stationary"
    return "wheeled"


def _infer_sub_category(name: str, text: str) -> str:
    """Keyword fallback for sub-category (used when Gemini classification isn't available)."""
    blob = f"{name} {text}".lower()
    if any(x in blob for x in ("warehouse", "fulfillment", "logistics", "amr", "agv", "forklift")):
        return "logistics-warehouse"
    if any(x in blob for x in ("surgical", "healthcare", "medical", "hospital")):
        return "healthcare"
    if any(x in blob for x in ("hotel", "waiter", "receptionist", "concierge", "hospitality", "restaurant")):
        return "service-hospitality"
    if any(x in blob for x in ("retail", "shop", "store", "promoter")):
        return "retail-customer-engagement"
    if any(x in blob for x in ("companion", "home", "personal")):
        return "companionship"
    if any(x in blob for x in ("manufactur", "industrial", "assembly", "weld")):
        return "manufacturing-industrial"
    if any(x in blob for x in ("clean", "disinfect", "sanitize")):
        return "cleaning-facilities"
    if any(x in blob for x in ("security", "patrol", "surveillance")):
        return "security"
    return ""


# Page furniture that shares the sentence window with real product copy. <main> still
# holds the product header, its CTA buttons and a related-solutions rail, and these land
# inside the 40-300 char window — avinc.com's opening chunk runs the header and CTAs
# straight into the first real sentence with no full stop between them, so a length
# window cannot separate them (TEL620 staged "TEL620 Multi-Domain Download Data Sheet
# Inquire Land TEL620" as its entire feature list). Match the furniture and drop the chunk.
_FEATURE_CHROME_RE = re.compile(
    r"\b(data\s+sheet|inquire|view\s+all|see\s+all|learn\s+more|read\s+more|"
    r"related\s+solutions|featured\s+capabilities|previous\s+next|skip\s+to\s+content|"
    r"contact\s+us|subscribe|sign\s+up|request\s+a\s+quote|back\s+to\s+top|"
    r"all\s+rights\s+reserved|privacy\s+policy|cookies?|consent)\b",
    re.IGNORECASE,
)

# Corporate voice, not a product fact. When a robot's URL resolves to an About/media
# page rather than a product page, the copy is company marketing in the first person
# ("Our All Domain Dominance approach keeps customers ahead of evolving threats") —
# the brief bans first person in descriptions for the same reason. Empty beats wrong.
_FEATURE_FIRST_PERSON_RE = re.compile(r"\b(our|we|us|ours)\b", re.IGNORECASE)

# Abbreviations that must not end a sentence: "the pioneering spirit of Dr. MacCready"
# otherwise splits mid-name. Python's re has no variable-width lookbehind, so protect
# the period, split, then restore it.
# Includes bare middle initials ("Dr. Paul B. MacCready"), which split just as badly.
_ABBREV_RE = re.compile(
    r"\b(Dr|Mr|Mrs|Ms|Jr|Sr|St|Co|Inc|Ltd|Corp|vs|etc|No|Fig|Mt|[A-Z])\.")


def _split_sentences(text: str) -> list[str]:
    protected = _ABBREV_RE.sub(lambda m: m.group(0)[:-1] + "\x00", text)
    return [p.replace("\x00", ".") for p in re.split(r"(?<=[.!?])\s+", protected.strip())]


def _summarize_features(text: str) -> str:
    """Pick product-fact sentences out of the product page's own copy.

    Chunks are filtered, not merely length-bounded: a chunk must be a complete sentence
    and must not carry page furniture. Newline-joined — features are stored one item per
    line (outline form), matching the discovery extractor and the content-queue display.
    """
    if not text:
        return ""
    picked: list[str] = []
    for chunk in _split_sentences(text):
        c = chunk.strip()
        if not 40 <= len(c) <= 300:
            continue
        # A complete sentence — spec tables and nav rails run on without terminal
        # punctuation, and extract_specs_from_text() already mines those separately.
        if not c.endswith((".", "!", "?")):
            continue
        if _FEATURE_CHROME_RE.search(c) or _FEATURE_FIRST_PERSON_RE.search(c):
            continue
        picked.append(c)
        if len(picked) >= 4:
            break
    return "\n".join(picked)[:800]


def _build_research_notes(
    hero_image: str,
    gallery_images: list[str],
    videos: list,
    used_playwright: bool,
) -> str:
    parts: list[str] = ["Auto-researched from official manufacturer website."]
    if not hero_image:
        parts.append(
            "No model-specific product image found (site icons/generic assets skipped); add image manually."
        )
    elif used_playwright:
        parts.append("Images extracted via Playwright-rendered pages.")
    if gallery_images:
        parts.append(f"Gallery: {len(gallery_images)} additional model-relevant image(s).")
    if videos:
        parts.append(f"Attached {len(videos)} model-specific video(s) with YouTube metadata where available.")
    elif not videos:
        parts.append("No model-specific videos attached (generic company intros skipped).")
    return " ".join(parts)


def research_robots_for_company(
    company_id: int,
    *,
    client: ResearchApiClient | None = None,
    only_missing: bool = True,
    merge_existing_db: bool = True,
    use_playwright: bool | None = None,
    use_stealth: bool | None = None,
    use_apify: bool | None = None,
    grounded: bool = False,
    force_fields: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    client = client or ResearchApiClient()
    company = client.get_company(company_id)
    company_slug = resolve_company_slug(
        str(company.get("name") or ""),
        company.get("slug"),
    )
    company_name = str(company.get("name") or "")
    website = str(company.get("website") or "")

    # Prefer staged company website if API company lacks it
    staged_company_path = RESEARCH_DIR / "staging" / "companies" / f"{company_slug}.json"
    if staged_company_path.is_file():
        staged_co = json.loads(staged_company_path.read_text(encoding="utf-8"))
        website = staged_co.get("website") or website
        manufacturer_cc = staged_co.get("country_code") or ""
    else:
        manufacturer_cc = ""

    if only_missing:
        from workflow_backfill import fetch_robots_missing_for_company
        robots = fetch_robots_missing_for_company(company_id, client=client)
        if not robots:
            # Missing-data queue empty — still research company robots lacking media
            robots = [
                r for r in client.list_robots_for_company(company_id)
                if not r.get("image") or not r.get("url")
            ]
    else:
        robots = client.list_robots_for_company(company_id)

    # Safety guard: automated research/refresh must never directly overwrite an already
    # approved/published (live, customer-facing) robot. If a robot needs fixing, it should be
    # moved back to draft/pending_review for re-review first — regardless of which selection
    # path (missing-data queue or full company list) surfaced it.
    skipped_live = [r for r in robots if str(r.get("status") or "").lower() not in ("draft", "pending_review")]
    robots = [r for r in robots if str(r.get("status") or "").lower() in ("draft", "pending_review")]

    researcher = RobotAutoResearcher(
        use_playwright=use_playwright, use_stealth=use_stealth, use_apify=use_apify, grounded=grounded,
    )
    evidence = EvidenceStore(company_slug, pipeline="enrich")
    print(f"Evidence   : {evidence.relative_root}", flush=True)
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    skipped_target_not_found: list[str] = []
    blocked_hero_urls: set[str] = set()

    for robot_idx, robot in enumerate(robots, 1):
        rid = robot.get("id")
        rname = robot.get("name") or f"id={rid}"
        print(f"  [{robot_idx}/{len(robots)}] Researching: {rname} ...", flush=True)
        try:
            researched = researcher.research_robot(
                robot,
                company_slug=company_slug,
                company_name=company_name,
                company_website=website,
                manufacturer_country_code=manufacturer_cc or _country_code_from_robot(robot),
                trust_stored_url="url" not in force_fields,
                refresh_description="description" in force_fields,
                blocked_hero_urls=blocked_hero_urls,
                evidence=evidence,
            )
            if researched is None:
                print(f"         skipped — target_not_found", flush=True)
                errors.append(f"target_not_found: {rname}")
                skipped_target_not_found.append(str(rname))
                continue
            if researched.image and score_image(
                researched.image,
                robot_name_tokens(researched.name, researched.model_name),
            ) < 16:
                # Block generic heroes already used for a sibling when URL lacks strong token match.
                blocked_hero_urls.add(researched.image)
            if merge_existing_db:
                base = _robot_api_to_staged(robot, company_slug, company_name)
                researched = _merge_staged(base, researched, force_fields=force_fields)
            validation = validate_robot(researched)
            path = researcher.write_staging_file(researched, company_slug)
            img_status = f"image={'YES' if researched.image else 'none'} +{len(researched.images)} extra"
            print(f"         done — {img_status}, {len(researched.video_urls)} video(s)", flush=True)
            results.append({
                "robot_id": rid,
                "name": researched.name,
                "staging_file": str(path.relative_to(RESEARCH_DIR.parent.parent)).replace("\\", "/"),
                "image": researched.image,
                "images_count": len(researched.images),
                "videos_count": len(researched.video_urls),
                "validation_ok": validation.ok,
                "warnings": [f"{i.field}: {i.message}" for i in validation.warnings()],
            })
        except Exception as exc:
            print(f"         ERROR: {exc}", flush=True)
            errors.append(f"robot {rid} ({robot.get('name')}): {exc}")

    evidence.finish(
        robots_researched=len(results),
        skipped_target_not_found=len(skipped_target_not_found),
        errors=len(errors),
        company_id=company_id,
        website=website,
    )
    sweep = sweep_company_evidence(company_slug)
    print(f"Evidence saved → {evidence.relative_root} (sweep deleted={sweep.get('deleted')})", flush=True)

    return {
        "ok": not errors,
        "company_id": company_id,
        "company_slug": company_slug,
        "robots_researched": len(results),
        "results": results,
        "errors": errors,
        "skipped_target_not_found": skipped_target_not_found,
        "evidence_dir": evidence.relative_root,
        "evidence_run_id": evidence.run_id,
        "evidence_sweep": sweep,
        "skipped_live_status": [
            {"robot_id": r.get("id"), "name": r.get("name"), "status": r.get("status")}
            for r in skipped_live
        ],
    }


def _robot_api_to_staged(robot: dict[str, Any], company_slug: str, company_name: str) -> StagedRobot:
    return StagedRobot.from_dict({
        "name": robot.get("name") or "",
        "model_name": robot.get("model_name") or robot.get("name") or "",
        "company_slug": company_slug,
        "company_name": company_name,
        "manufacturer_country_code": _country_code_from_robot(robot),
        "url": robot.get("url") or "",
        "image": robot.get("image") or "",
        "description": robot.get("description") or "",
        "purpose": robot.get("purpose") or "",
        "availability_status_key": _key_from_obj(robot.get("availability_status")),
        "industry_keys": _m2m_keys(robot.get("industries")),
        "use_keys": _m2m_keys(robot.get("uses")),
        # Carried so a remedy can SEE the current assignment: without these the
        # merge base was blank, the researched row was blank, and every remedy
        # wrote back a robot with no categories and no movement types — which is
        # why `remedy_missing_category` could never clear its own flag.
        "movement_type_keys": _m2m_keys(robot.get("movement_types")),
        "category_slugs": _category_slugs_from_robot(robot),
        # `features`/`tags` had the SAME bug as the four fields above and were
        # missed when those were fixed: every write uses force_overwrite=True
        # (full replace, not safe-patch), so a blank base here means any pass
        # that doesn't itself re-discover features/tags silently blanks out
        # real existing data as a side effect — found live on AgileX
        # (2026-08-01, robots 1680/1681/1776): `missing_family` remedies wiped
        # `features` even though that flag never touches it.
        "features": robot.get("features") or "",
        "tags": _join_pipe([str(t) for t in (robot.get("tags") or []) if str(t).strip()])
                if isinstance(robot.get("tags"), list)
                else str(robot.get("tags") or ""),
        "sources": [{"url": robot.get("url"), "type": "website"}] if robot.get("url") else [],
    })
