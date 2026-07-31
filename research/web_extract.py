"""HTTP fetch, site crawl, and media extraction for robot auto-research."""

from __future__ import annotations

import json
import os
import random
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html import unescape
from typing import Callable
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

_USER_AGENT = (
    "Mozilla/5.0 (compatible; RobotAIGeek-ResearchAgent/1.0; +https://robotaigeek.com)"
)

# Stealth mode (bot-detection avoidance, per RAI CrewAI handoff spec):
#   Tier 1 — curl_cffi with real-Chrome TLS fingerprint impersonation. Rotate only
#            recent Chrome versions: older ones (chrome110 era) trigger modern
#            Cloudflare blocks instead of bypassing them.
#   Tier 2 — Playwright with playwright-stealth v2, used when Tier 1 is blocked
#            (403/404) or returns a JS shell (almost no meaningful text).
_CHROME_IMPERSONATE = ("chrome124", "chrome131", "chrome136", "chrome142")
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# Under this much visible text the page is assumed to be a JS shell needing a render
_JS_SHELL_TEXT_CHARS = 5000
# Playwright's sync API drives a single process-wide greenlet dispatcher — two
# threads each opening their own sync_playwright() context at the same time
# corrupts it. Each render call still gets its own fresh browser (see
# get_rendered below); this lock only serializes the render *calls* themselves,
# so concurrent workers stay parallel for everything except the rare Tier-2
# escalation. Cheaper than forcing single-threaded operation project-wide.
_PLAYWRIGHT_LOCK = threading.Lock()
# Extension may sit mid-URL when a CDN transform suffix or query params follow
# (Storyblok: .../photo.webp/m/750x869/...; Next.js: /_next/image?url=...photo.png&w=3840).
_IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|avif)(?:[?&]|$|/m/)", re.I)
# AVIF decodes fine downstream (pillow-avif-plugin server-side), but when a CDN
# serves the same asset in both avif and a classic format (Wix: one media id,
# enc_avif transform), keep the classic sibling and drop the avif twin.
_AVIF_URL_RE = re.compile(r"\.avif(?:[?&]|$|/m/)", re.I)
# UI chrome, footer/social icons, nav sprites — never product photos.
_SKIP_IMAGE_RE = re.compile(
    r"(favicon|sprite|icon-|icons/|button-icons|megamenu|/icons/|"
    r"logo.*\.(?:png|svg)|badge|avatar|pixel|spacer|1x1|"
    r"skin/images/f-|/f-phone|/f-mail|/f-addr|/f-a\d|"
    r"skin/picture/top_pic|/skin/picture/|"
    r"gzh\.jpg|/dy\.jpg|wechat|weixin|tiktok|douyin|"
    r"search\.png|arrowup|arrow-down|/skin/images/|/assets/img/)",
    re.I,
)
_PRODUCT_UPLOAD_RE = re.compile(r"/(?:uploads?|static/upload/image)/", re.I)
# Minimum relevance scores for attaching media (see score_image / score_video).
_MIN_HERO_IMAGE_SCORE = 8   # at least one robot name token in the image URL
_MIN_GALLERY_IMAGE_SCORE = 6
_MIN_VIDEO_SCORE = 8          # at least one robot name token in title/description/url
_YOUTUBE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{11})",
    re.I,
)
_PAYLOAD_LBS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)", re.I)
_PAYLOAD_KG_RE = re.compile(r"(\d+(?:\.\d+)?)\s*kg", re.I)
_RUNTIME_HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\+?\s*hours?", re.I)
_JSON_URL_RE = re.compile(r'https?://[^"\']+(?:hubfs|hs-fs)[^"\']+\.(?:jpe?g|png|webp|avif)', re.I)
# --- Track B spec extraction patterns (added for long-description readiness) ---
# Repeatability: ±0.02 mm / +/-0.025mm / ≤0.05 mm
_REPEATABILITY_RE = re.compile(
    r"(?:repeatability|repeat(?:able)?(?:\s+accuracy)?)[^\n]{0,60}?[\u00b1+\-\u2264<]{1,3}\s*(\d+(?:\.\d+)?)\s*mm",
    re.I,
)
# Reach: 850 mm / 1.3 m (arm reach, not walking range)
_REACH_MM_RE = re.compile(
    r"(?:reach|working\s+radius|arm\s+reach)[^\n]{0,40}?(\d{3,4}(?:\.\d+)?)\s*mm",
    re.I,
)
_REACH_M_RE = re.compile(
    r"(?:reach|working\s+radius|arm\s+reach)[^\n]{0,40}?(\d+(?:\.\d+)?)\s*m(?!m)",
    re.I,
)
# DOF: 6-DOF / 6 DOF / 6 degrees of freedom / 6-axis
_DOF_RE = re.compile(
    r"(\d{1,2})\s*[-]?\s*(?:dof|degrees?\s+of\s+freedom|axis|axes)",
    re.I,
)
# Voltage: 24V / 48 VDC / 100-240 VAC
_VOLTAGE_RE = re.compile(
    r"(\d{2,3}(?:[\-\u2013]\d{2,3})?\s*V(?:DC|AC)?)",
    re.I,
)
# Max TCP speed: 1.5 m/s
_SPEED_MS_RE = re.compile(
    r"(?:max(?:imum)?\s+)?(?:tcp\s+)?speed[^\n]{0,40}?(\d+(?:\.\d+)?)\s*m/s",
    re.I,
)
# Max speed in km/h
_SPEED_KMH_RE = re.compile(
    r"(?:max(?:imum)?\s+)?speed[^\n]{0,40}?(\d+(?:\.\d+)?)\s*km/h",
    re.I,
)
# Robot body weight: 18 kg  (distinct from payload)
_WEIGHT_KG_RE = re.compile(
    r"(?:(?:robot\s+)?weight|mass)[^\n]{0,40}?(\d+(?:\.\d+)?)\s*kg",
    re.I,
)
# Runtime in minutes: 90 min / 90 minutes
_RUNTIME_MIN_RE = re.compile(
    r"(\d+)\s*(?:min(?:utes?)?)(?:\s|$)",
    re.I,
)



@dataclass
class PageContent:
    url: str
    html: str
    text: str = ""
    # Product copy only, with site chrome removed. `text` keeps the whole page for
    # model-name matching and the evidence archive; anything that feeds an LLM a
    # truncated prefix must use this instead — on nav-heavy sites (avinc.com) the
    # mega-menu alone runs past 9k chars, so a prefix of `text` is pure navigation.
    main_text: str = ""
    title: str = ""
    meta_description: str = ""
    images: list[str] = field(default_factory=list)
    # Images from the product content region only (nav/header/footer stripped), the
    # visual counterpart to `main_text`. `images` keeps the whole-page pool because
    # some sites put the hero outside <main>; prefer `main_images` whenever the goal
    # is "photos OF this product" rather than "photos on this page".
    main_images: list[str] = field(default_factory=list)
    video_urls: list[str] = field(default_factory=list)
    # True when a site-specific extractor already isolated this content to ONE model
    # (e.g. the Hikrobot per-model tab panel). Image selection normally verifies a
    # photo by finding the model token in its URL, which fails on CMS/date/hash
    # filenames like `/image/2022/3/24/20220324111716904.png`. For a model-scoped
    # page that check is redundant — the extractor already did the disambiguation —
    # so its images may be shortlisted without a filename match. Never set this for
    # family/category pages: those carry several models' photos and trusting them
    # blindly is how one image ends up pinned across a whole company's catalog.
    model_scoped: bool = False


def _resp_text(resp) -> str:
    """resp.text, but UTF-8-first when the server omits charset: HTTP's ISO-8859-1
    default mojibakes UTF-8 pages (e.g. CJK image paths on realman-robotics.com),
    producing image URLs that 404."""
    try:
        ctype = (resp.headers.get("content-type") or "").lower()
    except Exception:
        ctype = ""
    if "charset" not in ctype:
        content = getattr(resp, "content", None)
        if content:
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError:
                pass
    return resp.text


class WebFetcher:
    def __init__(
        self,
        timeout: int = 25,
        stealth: bool = False,
        apify_fallback: bool | None = None,
        apify_budget: int = 8,
    ):
        self.timeout = timeout
        self.stealth = stealth
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": _USER_AGENT, "Accept-Language": "en"})
        self._impersonate_idx = 0
        self._curl_requests = None
        # Tier 4 (Apify website-content-crawler): opt-in per run because each call is
        # an actor run (~30-90s). Budget caps the damage a fully-dead site can do to
        # a batch — after `apify_budget` rescue attempts we stop paying for that host.
        if apify_fallback is None:
            apify_fallback = os.environ.get("RESEARCH_USE_APIFY", "").lower() in ("1", "true", "yes")
        self.apify_fallback = bool(apify_fallback)
        self._apify_budget = apify_budget
        if stealth:
            try:
                from curl_cffi import requests as curl_requests
                self._curl_requests = curl_requests
            except ImportError:
                print("[stealth] curl_cffi not installed (pip install curl_cffi) — "
                      "falling back to plain requests for Tier 1", flush=True)

    def get(self, url: str) -> str | None:
        if self.stealth:
            return self._get_stealth(url)
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if resp.status_code >= 400:
                return None
            return _resp_text(resp)
        except requests.RequestException:
            return None

    def _get_stealth(self, url: str) -> str | None:
        """Tier 1: curl_cffi Chrome impersonation; Tier 2: stealth Playwright on
        block (403/404) or JS shell. Sitemaps/XML never trigger the render tier."""
        html = None
        blocked = False
        if self._curl_requests is not None:
            fingerprint = _CHROME_IMPERSONATE[self._impersonate_idx % len(_CHROME_IMPERSONATE)]
            self._impersonate_idx += 1
            domain = urlparse(url).netloc
            headers = {
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": f"https://www.google.com/search?q={domain}",
            }
            for imp in (fingerprint, "chrome"):  # retry with generic alias if version unsupported
                try:
                    resp = self._curl_requests.get(
                        url, impersonate=imp, timeout=self.timeout,
                        allow_redirects=True, headers=headers,
                    )
                    blocked = resp.status_code in (403, 404)
                    html = _resp_text(resp) if resp.status_code < 400 else None
                    break
                except Exception as exc:
                    if "impersonate" in str(exc).lower():
                        continue
                    break
        else:
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                blocked = resp.status_code in (403, 404)
                html = _resp_text(resp) if resp.status_code < 400 else None
            except requests.RequestException:
                pass

        # XML (sitemaps, feeds) can't be a JS shell — no point rendering it
        if url.lower().rstrip("/").endswith(".xml") or (html or "").lstrip()[:5] == "<?xml":
            return html

        needs_render = blocked or html is None
        if not needs_render and html is not None:
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            needs_render = len(text) < _JS_SHELL_TEXT_CHARS
        if needs_render:
            rendered = self.get_rendered(url)
            if rendered:
                return rendered
        return html

    def apify_get(self, url: str) -> str | None:
        """Tier 4: Apify website-content-crawler (headless Firefox + rotating proxy).
        Runs only when enabled, budgeted, and worth it — sitemap/XML probes 404
        legitimately all the time and never warrant a paid actor run."""
        if not self.apify_fallback or self._apify_budget <= 0:
            return None
        if url.lower().rstrip("/").endswith(".xml"):
            return None
        from apify_fetch import apify_enabled, wcc_fetch_html
        if not apify_enabled():
            return None
        self._apify_budget -= 1
        print(f"    [apify] tier-4 fetch ({self._apify_budget} budget left): {url}", flush=True)
        return wcc_fetch_html(url)

    def get_rendered(self, url: str) -> str | None:
        """Optional Playwright render for JS-heavy sites. In stealth mode the page is
        patched with playwright-stealth (WebDriver flag, canvas fingerprint, plugins)
        and browses with a real Chrome UA + human-like dwell time."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None
        try:
            with _PLAYWRIGHT_LOCK, sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent=_CHROME_UA if self.stealth else _USER_AGENT,
                    locale="en-US",
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                if self.stealth:
                    try:
                        from playwright_stealth import Stealth
                        Stealth().apply_stealth_sync(page)
                    except ImportError:
                        pass
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                if self.stealth:
                    # human-like dwell + scroll so lazy-loaded media appears
                    time.sleep(random.uniform(1.5, 4.0))
                    try:
                        page.mouse.wheel(0, 1200)
                        time.sleep(random.uniform(0.5, 1.5))
                    except Exception:
                        pass
                html = page.content()
                browser.close()
                return html
        except Exception:
            return None


def normalize_url(url: str, base: str = "") -> str:
  url = unescape((url or "").strip())
  if not url:
    return ""
  if url.startswith("//"):
    url = "https:" + url
  if base and not url.startswith(("http://", "https://")):
    url = urljoin(base, url)
  # Next.js image proxy wraps the real CDN asset: /_next/image?url=<urlencoded>&w=...
  # Unwrap to the underlying image so downstream checks/copies hit the actual file.
  if "/_next/image" in url:
    from urllib.parse import parse_qs, unquote
    inner = parse_qs(urlparse(url).query).get("url", [""])[0]
    if inner:
      url = unquote(inner)
      if url.startswith("//"):
        url = "https:" + url
      elif base and not url.startswith(("http://", "https://")):
        url = urljoin(base, url)
  parsed = urlparse(url)
  if parsed.scheme not in ("http", "https"):
    return ""
  return urlunparse(parsed._replace(fragment=""))


def same_site(url: str, base_netloc: str) -> bool:
  host = urlparse(url).netloc.lower().removeprefix("www.")
  base = base_netloc.lower().removeprefix("www.")
  return host == base or host.endswith("." + base)


def discover_sitemap_urls(fetcher: WebFetcher, base_url: str, limit: int = 80) -> list[str]:
  parsed = urlparse(base_url)
  origin = f"{parsed.scheme}://{parsed.netloc}"
  candidates = [urljoin(origin, "/sitemap.xml"), urljoin(origin, "/sitemap_index.xml")]
  urls: list[str] = []
  seen: set[str] = set()

  for sm_url in candidates:
    xml = fetcher.get(sm_url)
    if not xml:
      continue
    try:
      root = ET.fromstring(xml)
    except ET.ParseError:
      continue
    tag = root.tag.rsplit("}", 1)[-1]
    if tag == "sitemapindex":
      for loc in root.iter():
        if loc.tag.rsplit("}", 1)[-1] == "loc" and loc.text:
          child_xml = fetcher.get(loc.text.strip())
          if child_xml:
            try:
              child_root = ET.fromstring(child_xml)
              for child_loc in child_root.iter():
                if child_loc.tag.rsplit("}", 1)[-1] == "loc" and child_loc.text:
                  u = normalize_url(child_loc.text.strip())
                  if u and u not in seen:
                    seen.add(u)
                    urls.append(u)
            except ET.ParseError:
              continue
    else:
      for loc in root.iter():
        if loc.tag.rsplit("}", 1)[-1] == "loc" and loc.text:
          u = normalize_url(loc.text.strip())
          if u and u not in seen:
            seen.add(u)
            urls.append(u)
    if urls:
      break
  return urls[:limit]


def extract_youtube_ids(html: str) -> list[str]:
  ids: list[str] = []
  seen: set[str] = set()
  for match in _YOUTUBE_RE.finditer(html or ""):
    vid = match.group(1)
    if vid not in seen:
      seen.add(vid)
      ids.append(vid)
  return ids


def youtube_watch_url(video_id: str) -> str:
  return f"https://www.youtube.com/watch?v={video_id}"


def _avif_twin_key(url: str) -> str:
  """Format-insensitive asset identity: extension tokens are normalized and CDN
  transform path segments (Wix/Cloudinary "w_740,h_986,...,enc_avif,quality_auto")
  are dropped — the avif and png renditions of one asset differ only there."""
  key = re.sub(r"\.(?:jpe?g|png|webp|avif)\b", ".*", url, flags=re.I)
  return "/".join(p for p in key.split("/") if "," not in p)


def _drop_avif_twins(urls: list[str]) -> list[str]:
  non_avif_keys = {_avif_twin_key(u) for u in urls if not _AVIF_URL_RE.search(u)}
  return [u for u in urls if not _AVIF_URL_RE.search(u) or _avif_twin_key(u) not in non_avif_keys]


def extract_image_urls(html: str, base_url: str) -> list[str]:
  urls: list[str] = []
  seen: set[str] = set()

  def add(raw: str) -> None:
    u = normalize_url(raw, base_url)
    if not u or u in seen:
      return
    if _SKIP_IMAGE_RE.search(u):
      return
    if not _IMAGE_EXT_RE.search(u) and "hubfs" not in u.lower() and "hs-fs" not in u.lower():
      return
    seen.add(u)
    urls.append(u)

  if not html:
    return urls

  for m in _JSON_URL_RE.findall(html):
    add(m)

  soup = BeautifulSoup(html, "html.parser")
  for tag, attr in (("meta", "content"), ("link", "href"), ("img", "src"), ("img", "data-src")):
    for el in soup.find_all(tag):
      val = el.get(attr) or ""
      if tag == "meta" and el.get("property") not in ("og:image", "twitter:image") and el.get("name") not in ("og:image", "twitter:image"):
        if attr == "content" and tag == "meta":
          continue
      if tag == "link" and el.get("rel") not in (["image_src"], "image_src"):
        continue
      if val:
        add(val)

  for el in soup.find_all(style=True):
    for m in re.findall(r"url\(['\"]?([^)'\"]+)['\"]?\)", el.get("style", "")):
      add(m)

  # Responsive/lazy-loaded images: srcset holds "url width, url width" pairs and is
  # often the ONLY place product carousel photos appear (e.g. Storyblok/Next.js sites).
  for el in soup.find_all(["img", "source"]):
    for attr in ("srcset", "data-srcset", "data-lazy-src", "data-original"):
      val = el.get(attr) or ""
      if not val:
        continue
      if attr.endswith("srcset"):
        # split on ",<space>" only: Wix/Cloudinary URLs carry commas inside the
        # path (w_359,h_472,al_c,q_auto/...) and a bare comma split turns the tail
        # into a bogus relative URL (site.com/q_auto/img.png -> 404)
        for part in re.split(r",\s+", val):
          candidate = part.strip().split(" ")[0]
          if candidate:
            add(candidate)
      else:
        add(val)

  return _drop_avif_twins(urls)


_NOISE_SELECTORS = (
  "[aria-label*=cookie i]", "[id*=cookie i]", "[class*=cookie i]",
  "[id*=consent i]", "[class*=consent i]", "[id*=onetrust i]", "[class*=onetrust i]",
  "[role=navigation]",
  # Dropdown option lists. A country/region picker renders its full option set into
  # the DOM, and on ubtrobot.com that put ~2100 chars of country names ("Afghanistan
  # Albania Algeria …") at the very START of main_text. Downstream consumers read a
  # truncated prefix — features uses text[:1200], classification ~2500 — so the whole
  # window was country names and `_summarize_features` returned nothing while the
  # real copy sat further down the page. Option lists are form controls, never
  # product copy, so they are always safe to drop.
  "[role=listbox]", "[role=option]",
)
_MAIN_TEXT_MIN_CHARS = 200


def _scrub_noise(el):
  """Drop nav, consent and form-control widgets from an element, in place."""
  for tag in el.find_all(["nav", "script", "style", "noscript", "select", "datalist"]):
    tag.decompose()
  for selector in _NOISE_SELECTORS:
    for tag in el.select(selector):
      tag.decompose()
  return el


def extract_main_text(soup) -> str:
  """Product copy with site chrome stripped.

  Prefers <main>/<article>, scrubbing only nav/consent *inside* it — section
  <header>/<footer> carry product hero copy ("A Compact, Powerful, Entry-Level
  ROV") and must survive. Falls back to the body minus top-level chrome."""
  for tag in ("main", "article"):
    el = soup.find(tag)
    if el:
      text = _scrub_noise(el).get_text(" ", strip=True)
      if len(text) >= _MAIN_TEXT_MIN_CHARS:
        return text
  body = soup.body or soup
  for tag in body.find_all(["nav", "header", "footer"], recursive=False):
    tag.decompose()
  return _scrub_noise(body).get_text(" ", strip=True)


_SERIES_RE = re.compile(r"\b([A-Za-z0-9][\w\-\. ]{1,28}?)\s+(?:series|família|series\b)", re.I)


def extract_series_hint(html: str, *, robot_name: str = "") -> str:
    """The vendor's OWN series name for this product, or "".

    Family metadata should come from the manufacturer's taxonomy rather than from
    splitting our own model names — that is what the discovery feedback asks for,
    and it is what makes `Walker Tienkung` land in the Walker family even though
    the variant token looks nothing like its siblings.

    Two grounded signals, in order: a breadcrumb trail (the vendor's own product
    hierarchy) and explicit "<X> Series" wording on the page. Both are validated
    against the robot's name before being accepted, because a breadcrumb also
    contains generic ancestry ("Home", "Products") and a page can mention other
    products' series in nav or related links.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    head_token = ""
    tokens = re.findall(r"[A-Za-z0-9\-\.]+", robot_name or "")
    if tokens:
        head_token = tokens[0].lower()

    def _plausible(candidate: str) -> bool:
        """Accept only a short series label the robot's own name supports.

        The length/word caps are load-bearing: on epson.com the deepest breadcrumb is
        the full product title ("Flexion N6 Compact 6-Axis Robots - 850mm"), which
        passes the name check (it starts with the family token) yet is a product, not
        a series. A series is a short label — "CL", "Flexion", "MELFA RV-FR" — so
        anything sentence-shaped is rejected rather than written into family_name.
        """
        c = candidate.strip().strip("-–—:|>").strip()
        if not c or len(c) > 24 or len(c.split()) > 3:
            return False
        cl = c.lower()
        if cl in {"home", "products", "product", "index", "robots", "solutions", "en", "shop"}:
            return False
        # Spec-sheet noise that shows up in titles but never names a series.
        if re.search(r"\d+\s*(?:mm|kg|axis)\b|\baxis\b|\brobots?\b$", cl):
            return False
        # The robot must belong to it: either the name starts with the series, or
        # the series starts with the name's leading token ("Walker" <- "Walker S2").
        return bool(head_token) and (
            (robot_name or "").lower().startswith(cl) or cl.startswith(head_token)
        )

    # 1. Breadcrumbs — the vendor's own hierarchy. Deepest plausible crumb wins,
    #    since it is the most specific ancestor of this product.
    crumbs: list[str] = []
    for node in soup.select(
        '[class*=breadcrumb i] a, [class*=breadcrumb i] span, '
        '[id*=breadcrumb i] a, nav[aria-label*=readcrumb] a, [itemprop=itemListElement]'
    ):
        text = node.get_text(" ", strip=True)
        if text:
            crumbs.append(text)
    for crumb in reversed(crumbs):
        if _plausible(crumb):
            return crumb.strip().strip("-–—:|>").strip()

    # 2. Explicit "<X> Series" wording in the product copy.
    for match in _SERIES_RE.finditer(soup.get_text(" ", strip=True)[:6000]):
        candidate = match.group(1)
        if _plausible(candidate):
            return candidate.strip()
    return ""


def extract_main_image_urls(html: str, base_url: str) -> list[str]:
  """Images from the product content region only, with site chrome stripped.

  `extract_image_urls` scans the WHOLE page, so on a per-model product page the
  pool also contains OTHER products' navigation thumbnails (measured on
  ubtrobot.com/en/ai-education/products/ukit-ai: CRUZR.png, CADEBOTL100.png,
  nav_01.png alongside uKit's own photos). Text already avoids this via
  `extract_main_text`; this is the image equivalent, using the same element
  choice and scrubbing so the two stay consistent.
  """
  if not html:
    return []
  soup = BeautifulSoup(html, "html.parser")
  for tag in ("main", "article"):
    el = soup.find(tag)
    if el:
      return extract_image_urls(str(_scrub_noise(el)), base_url)
  body = soup.body or soup
  for tag in body.find_all(["nav", "header", "footer"], recursive=False):
    tag.decompose()
  return extract_image_urls(str(_scrub_noise(body)), base_url)


def page_from_html(url: str, html: str) -> PageContent | None:
  """Build a PageContent from already-obtained HTML (shared by parse_page and
  the Apify site-crawl path in discovery)."""
  if not html:
    return None
  soup = BeautifulSoup(html, "html.parser")
  title = (soup.title.string or "").strip() if soup.title else ""
  meta_desc = ""
  og = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
  if og and og.get("content"):
    meta_desc = og["content"].strip()
  text = soup.get_text(" ", strip=True)
  # Parsed fresh: extract_main_text() mutates the tree it is handed.
  main_text = extract_main_text(BeautifulSoup(html, "html.parser"))
  images = extract_image_urls(html, url)
  main_images = extract_main_image_urls(html, url)
  video_ids = extract_youtube_ids(html)
  return PageContent(
    url=url,
    html=html,
    text=text,
    main_text=main_text,
    title=title,
    meta_description=meta_desc,
    images=images,
    main_images=main_images,
    video_urls=[youtube_watch_url(v) for v in video_ids],
  )


def parse_page(fetcher: WebFetcher, url: str, *, rendered: bool = False) -> PageContent | None:
  html = fetcher.get_rendered(url) if rendered else fetcher.get(url)
  if not html:
    # Tier 4: bot-walled page — try Apify website-content-crawler (no-op unless
    # the fetcher was built with apify_fallback and budget remains).
    html = fetcher.apify_get(url)
  return page_from_html(url, html or "")


def robot_name_tokens(name: str, model_name: str = "") -> list[str]:
  tokens: set[str] = set()
  for raw in (name, model_name):
    parts = [p for p in re.split(r"[^a-z0-9]+", (raw or "").lower()) if p]
    for part in parts:
      if len(part) >= 3 and part not in {"robot", "amr", "the", "and"}:
        tokens.add(part)
    # Keep a short trailing variant suffix (e.g. "365HotelBot - W" -> "w") even though it's
    # below the length-3 cutoff above. Product-line variants that share one page/base name
    # (Model W / S / D, Type A / B, etc.) are only distinguishable by this suffix — dropping
    # it makes every variant produce identical tokens, so image/URL ranking picks the same
    # result for all of them.
    if parts and len(parts[-1]) <= 2 and parts[-1] not in {"robot", "amr"}:
      tokens.add(parts[-1])
  return sorted(tokens)


def _token_matches(tok: str, text: str) -> bool:
  """Boundary-aware match for short tokens and model codes with digits (e.g. 720, ier8)."""
  if len(tok) <= 2 or any(c.isdigit() for c in tok):
    return re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])", text, re.I) is not None
  return tok in text


def _normalize_model_for_match(name: str) -> str:
  """iER8-720-MI-C and ER8-720-MI-PI-C should match the same product page."""
  n = (name or "").strip().upper().replace(" ", "")
  if n.startswith("IER"):
    n = "ER" + n[3:]
  return n.replace("-MI-C", "-MI-PI-C").replace("-MI-PI-PI-C", "-MI-PI-C")


def model_name_in_page(name: str, model_name: str, page: PageContent) -> bool:
  blob = f"{page.title} {page.meta_description} {page.text}".upper().replace(" ", "")
  for candidate in (name, model_name):
    if not candidate:
      continue
    norm = _normalize_model_for_match(candidate)
    if norm and norm in blob:
      return True
    if candidate.upper().replace(" ", "") in blob:
      return True
  return False


def confirm_target_on_page(
  name: str,
  model_name: str,
  page: PageContent | None,
  *,
  also_check_url: bool = True,
) -> bool:
  """Deterministic gate: the named robot/fragment must appear on the page.

  Used for target_not_found fail-closed behavior — never attribute whole-page
  extraction to a robot that is not visibly present on that page.
  """
  if page is None:
    return False
  if model_name_in_page(name, model_name, page):
    return True
  if also_check_url:
    tokens = robot_name_tokens(name, model_name)
    path = (urlparse(page.url).path or "").lower().replace("_", "-")
    for tok in tokens:
      if not tok:
        continue
      # Require model-ish tokens in the path. Short words like "arm"/"bot"
      # appear on many sibling product URLs and would false-positive.
      if len(tok) < 5 and not any(c.isdigit() for c in tok):
        continue
      if tok in path:
        return True
  return False


def search_model_name_aliases(model_name: str) -> list[str]:
  """Extra search/crawl names for locale variants (Estun iER vs ER, clean-room suffix)."""
  model = (model_name or "").strip()
  if not model:
    return []
  aliases = [model]
  upper = model.upper()
  if upper.startswith("IER"):
    er = "ER" + model[3:]
    aliases.append(er)
    if er.upper().endswith("-MI-C"):
      aliases.append(er[:-5] + "-MI-PI-C")
  return list(dict.fromkeys(aliases))


def company_website_alternates(website: str) -> list[str]:
  """Other locales on the same manufacturer domain (e.g. en.estun.com)."""
  website = (website or "").strip().rstrip("/")
  if not website:
    return []
  parsed = urlparse(website if "://" in website else f"https://{website}")
  netloc = parsed.netloc.lower().removeprefix("www.")
  origins = [f"{parsed.scheme}://{parsed.netloc}".rstrip("/")]
  if netloc in ("estun.com", "www.estun.com"):
    origins = [f"{parsed.scheme}://en.estun.com", origins[0]]
  elif netloc == "en.estun.com":
    origins.append("https://www.estun.com")
  return list(dict.fromkeys(origins))


def is_product_upload_image(url: str) -> bool:
  return bool(_PRODUCT_UPLOAD_RE.search(url or ""))


def score_url_for_robot(url: str, tokens: list[str]) -> int:
  path = urlparse(url).path.lower()
  score = 0
  for tok in tokens:
    if _token_matches(tok, path):
      score += 10
  if any(x in path for x in ("product", "robot", "solution", "amr", "device")):
    score += 3
  if any(x in path for x in ("blog", "news", "press", "career", "privacy", "cookie", "login", "glossary")):
    score -= 5
  return score


def rank_candidate_urls(urls: list[str], tokens: list[str]) -> list[str]:
  scored = [(score_url_for_robot(u, tokens), u) for u in urls]
  scored.sort(key=lambda x: (-x[0], x[1]))
  return [u for s, u in scored if s > 0]


def extract_specs_from_text(text: str) -> dict[str, object]:
  """Extract numeric specs from scraped product-page text.

  Returns a dict of field-name → value pairs ready to merge into a StagedRobot.
  All patterns are conservative: they only fire when the spec label is present
  near the number, so false positives on generic prose are rare.

  Fields extracted (Track B readiness):
    payload_kg, reach_mm, repeatability_mm, dof, voltage,
    weight_kg, speed (km/h), speed_ms (m/s), runtime, runtime_minutes
  """
  specs: dict[str, object] = {}
  if not text:
    return specs

  # ── Payload ──────────────────────────────────────────────────────────────
  m = _PAYLOAD_LBS_RE.search(text)
  if m:
    specs["payload_kg"] = round(float(m.group(1)) * 0.453592, 1)
  m = _PAYLOAD_KG_RE.search(text)
  if m:
    specs["payload_kg"] = float(m.group(1))

  # ── Reach ─────────────────────────────────────────────────────────────────
  m = _REACH_MM_RE.search(text)
  if m:
    specs["reach_mm"] = float(m.group(1))
  elif not specs.get("reach_mm"):
    m = _REACH_M_RE.search(text)
    if m:
      specs["reach_mm"] = round(float(m.group(1)) * 1000, 1)

  # ── Repeatability ─────────────────────────────────────────────────────────
  m = _REPEATABILITY_RE.search(text)
  if m:
    specs["repeatability_mm"] = float(m.group(1))

  # ── Degrees of Freedom ────────────────────────────────────────────────────
  m = _DOF_RE.search(text)
  if m:
    val = int(m.group(1))
    if 1 <= val <= 20:  # sanity bound
      specs["dof"] = val

  # ── Voltage ───────────────────────────────────────────────────────────────
  m = _VOLTAGE_RE.search(text)
  if m:
    specs["voltage"] = m.group(1).strip()

  # ── Speed ─────────────────────────────────────────────────────────────────
  m = _SPEED_MS_RE.search(text)
  if m:
    ms = float(m.group(1))
    specs["speed_ms"] = ms
    specs["speed"] = round(ms * 3.6, 2)  # convert to km/h for the DB field
  elif not specs.get("speed"):
    m = _SPEED_KMH_RE.search(text)
    if m:
      specs["speed"] = float(m.group(1))

  # ── Weight ────────────────────────────────────────────────────────────────
  m = _WEIGHT_KG_RE.search(text)
  if m:
    val = float(m.group(1))
    if val < 5000:  # exclude clearly wrong hits (e.g. "max load 2000 kg")
      specs["weight_kg"] = val

  # ── Runtime ───────────────────────────────────────────────────────────────
  m = _RUNTIME_HOURS_RE.search(text)
  if m:
    specs["runtime"] = f"{m.group(1)}+ hours" if "+" in m.group(0) else f"{m.group(1)} hours"
    # Also store structured minutes
    try:
      specs["runtime_minutes"] = int(float(m.group(1)) * 60)
    except ValueError:
      pass
  elif not specs.get("runtime"):
    m = _RUNTIME_MIN_RE.search(text)
    if m:
      mins = int(m.group(1))
      if 5 <= mins <= 1440:  # sanity: 5 min to 24 h
        specs["runtime_minutes"] = mins
        specs["runtime"] = f"{mins} min"

  return specs


def find_youtube_channel_videos(fetcher: WebFetcher, channel_url: str, limit: int = 5) -> list[str]:
  """Parse public /videos page for watch links (no API key)."""
  if not channel_url:
    return []
  videos_url = channel_url.rstrip("/")
  if "/videos" not in videos_url:
    videos_url += "/videos"
  html = fetcher.get(videos_url)
  if not html:
    return []
  ids = extract_youtube_ids(html)
  # ytInitialData often embeds videoId fields
  for m in re.findall(r'"videoId":"([\w-]{11})"', html):
    if m not in ids:
      ids.append(m)
  return [youtube_watch_url(v) for v in ids[:limit]]


def find_youtube_on_domain(fetcher: WebFetcher, pages: list[PageContent]) -> list[str]:
  urls: list[str] = []
  seen: set[str] = set()
  channel: str | None = None
  for page in pages:
    for v in page.video_urls:
      if v not in seen:
        seen.add(v)
        urls.append(v)
    for m in re.findall(r"https?://(?:www\.)?youtube\.com/@[\w.-]+", page.html or ""):
      channel = m
  if channel:
    for v in find_youtube_channel_videos(fetcher, channel, limit=3):
      if v not in seen:
        seen.add(v)
        urls.append(v)
  return urls


def rank_images(images: list[str], tokens: list[str]) -> list[str]:
  """Sort images by relevance. Prefer select_confident_images() for staging/import."""
  unique: list[str] = []
  seen: set[str] = set()
  for url in sorted(images, key=lambda u: score_image(u, tokens), reverse=True):
    if is_junk_image_url(url):
      continue
    if url not in seen:
      seen.add(url)
      unique.append(url)
  return unique


def is_junk_image_url(url: str) -> bool:
  return bool(_SKIP_IMAGE_RE.search(url or ""))


def score_image(url: str, tokens: list[str]) -> int:
  lower = (url or "").lower()
  if is_junk_image_url(url):
    return -100
  s = 0
  for tok in tokens:
    if _token_matches(tok, lower):
      s += 8
  if "hubfs" in lower or "hs-fs" in lower:
    s += 4
  if any(x in lower for x in ("hero", "product", "gallery", "robot", "amr")):
    s += 3
  if any(x in lower for x in ("logo", "icon", "thumb")):
    s -= 6
  return s


def score_video(video: dict, tokens: list[str]) -> int:
  text = f"{video.get('title', '')} {video.get('description', '')} {video.get('url', '')}".lower()
  s = 0
  for tok in tokens:
    if _token_matches(tok, text):
      s += 8
  # Penalize generic company-line intros that apply to every model at the site.
  generic = ("introduction", "intro video", "company profile", "robotics introduction", "overview")
  if any(g in text for g in generic) and s < 16:
    s -= 10
  return s


def select_confident_images(
  images: list[str],
  tokens: list[str],
  *,
  blocked_heroes: set[str] | None = None,
  min_hero_score: int = _MIN_HERO_IMAGE_SCORE,
  min_gallery_score: int = _MIN_GALLERY_IMAGE_SCORE,
  max_gallery: int = 5,
) -> tuple[str, list[str]]:
  """Return (hero_url, gallery_urls). Leaves hero blank when nothing is model-specific enough."""
  blocked = blocked_heroes or set()
  scored: list[tuple[int, str]] = []
  for url in images:
    s = score_image(url, tokens)
    if s > 0:
      scored.append((s, url))
  scored.sort(key=lambda x: (-x[0], x[1]))

  hero = ""
  gallery: list[str] = []
  for s, url in scored:
    if not hero and s >= min_hero_score and url not in blocked:
      hero = url
      continue
    if hero and url != hero and s >= min_gallery_score and url not in gallery:
      gallery.append(url)
    if len(gallery) >= max_gallery:
      break
  return hero, gallery


def select_images_for_pages(
  pages: list[PageContent],
  *,
  product_url: str,
  name: str,
  model_name: str,
  tokens: list[str],
  blocked_heroes: set[str] | None = None,
  max_gallery: int = 5,
) -> tuple[str, list[str]]:
  """Pick images from a model-specific product page when URL tokens are opaque (Estun uploads/)."""
  blocked = blocked_heroes or set()
  product_pages = [
    p for p in pages
    if product_url and (p.url.rstrip("/") == product_url.rstrip("/") or product_url.rstrip("/") in p.url.rstrip("/"))
  ] or pages[:1]

  for page in product_pages:
    if not model_name_in_page(name, model_name, page):
      continue
    uploads = [
      u for u in page.images
      if is_product_upload_image(u) and not is_junk_image_url(u)
    ]
    if not uploads:
      continue
    # Prefer PNG product renders; deprioritize tiny shared JPG banners reused site-wide.
    def upload_rank(url: str) -> tuple[int, str]:
      lower = url.lower()
      score = 0
      if lower.endswith(".png"):
        score += 2
      if "/202509" in lower or "/202603" in lower or "/202605" in lower:
        score += 1
      return (-score, url)

    uploads.sort(key=upload_rank)
    hero = next((u for u in uploads if u not in blocked), "")
    if not hero:
      continue
    gallery = [u for u in uploads if u != hero and u not in blocked][:max_gallery]
    return hero, gallery

  # Fail closed: do NOT fall back to whole-page / sibling images when the model
  # is not confirmed on the product page (target_not_found semantics).
  return "", []


def build_image_candidates_for_pages(
  pages: list[PageContent],
  *,
  product_url: str,
  name: str,
  model_name: str,
  tokens: list[str],
  company_name: str = "",
  source_tier_hint: str = "official_exact",
  max_gallery: int = 5,
) -> list[dict]:
  """Score shortlisted images already extracted from product or linked HTML pages.

  This is the core HTML/page ladder only. PDF extraction and third-party crawling
  remain separate acquisition tiers.
  """
  if not pages:
    return []

  all_images = list(dict.fromkeys(
    image_url
    for page in pages
    for image_url in page.images
    if image_url and not is_junk_image_url(image_url)
  ))
  page_hero, page_gallery = select_images_for_pages(
    pages,
    product_url=product_url,
    name=name,
    model_name=model_name,
    tokens=tokens,
    max_gallery=max_gallery,
  )
  confident_hero, confident_gallery = select_confident_images(
    all_images,
    tokens,
    max_gallery=max_gallery,
  )
  # Model-scoped fallback: images from a page a site-specific extractor already
  # narrowed to THIS model. Token scoring rejects them when the OEM serves
  # CMS/date/hash filenames (no model name to match), which silently yields zero
  # candidates — and an empty candidate list also starves the grounded/vision pass,
  # so nothing downstream can recover. Appended LAST so genuine token matches keep
  # priority and ordering; these only fill slots the scored ladder left empty.
  scoped_images = list(dict.fromkeys(
    image_url
    for page in pages
    if getattr(page, "model_scoped", False)
    for image_url in page.images
    if image_url and not is_junk_image_url(image_url)
  ))
  shortlisted = list(dict.fromkeys(
    image_url
    for image_url in (
      page_hero,
      *page_gallery,
      confident_hero,
      *confident_gallery,
      *scoped_images,
    )
    if image_url
  ))[: max_gallery + 1]
  if not shortlisted:
    return []

  try:
    from image_confidence import build_candidate
  except ImportError:
    # The research package runs both beside Django and as a standalone script.
    import sys
    from pathlib import Path

    server_dir = Path(__file__).resolve().parents[2] / "robotaigeek-server"
    if server_dir.is_dir() and str(server_dir) not in sys.path:
      sys.path.insert(0, str(server_dir))
    from image_confidence import build_candidate

  product_key = (product_url or "").rstrip("/")

  def source_page_for(image_url: str) -> PageContent:
    containing = [page for page in pages if image_url in page.images]
    if product_key:
      product_page = next(
        (
          page for page in containing
          if page.url.rstrip("/") == product_key
          or product_key in page.url.rstrip("/")
        ),
        None,
      )
      if product_page is not None:
        return product_page
    return containing[0] if containing else pages[0]

  candidates: list[dict] = []
  for image_url in shortlisted:
    page = source_page_for(image_url)
    publisher = urlparse(page.url).netloc.lower().removeprefix("www.")
    candidate = build_candidate(
      url=image_url,
      source_page_url=page.url,
      source_tier_hint=source_tier_hint,
      source_publisher=publisher,
      tokens=tokens,
      page_text=f"{page.title} {page.meta_description} {page.text}".strip(),
    )
    candidates.append(candidate)

  # ``company_name`` is part of the stable adapter interface for future source
  # tiers; publisher identity intentionally comes from the traceable page host.
  _ = company_name
  candidates.sort(key=lambda candidate: candidate.get("confidence_score", 0), reverse=True)
  return candidates


def select_hero_from_candidates(candidates: list[dict]) -> str:
  """Choose a reviewable hero without promoting reject-confidence candidates."""
  for candidate in candidates:
    if (
      candidate.get("is_primary_eligible")
      and candidate.get("confidence_level") in {"high", "medium"}
    ):
      return str(candidate.get("url") or "")
  for candidate in candidates:
    if candidate.get("confidence_level") != "reject":
      return str(candidate.get("url") or "")
  return ""


def select_confident_videos(
  videos: list[dict],
  tokens: list[str],
  *,
  min_score: int = _MIN_VIDEO_SCORE,
  max_count: int = 3,
) -> list[dict]:
  """Keep only videos whose title/description/url match this robot's name tokens."""
  ranked = sorted(videos, key=lambda v: score_video(v, tokens), reverse=True)
  return [v for v in ranked if score_video(v, tokens) >= min_score][:max_count]


def rank_videos(videos: list[dict], tokens: list[str]) -> list[dict]:
  """Rank enriched video dicts by relevance. Prefer select_confident_videos() for staging."""
  return sorted(videos, key=lambda v: score_video(v, tokens), reverse=True)
