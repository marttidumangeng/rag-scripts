# -*- coding: utf-8 -*-
"""Scrape Realman EN PDP hero images into docs/_realman_qa/."""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunsplit

import requests

BASE = "https://www.realman-robotics.com"
CORE_PRODUCTS = f"{BASE}/en/main/core-products.html"
OUT_DIR = Path(__file__).resolve().parent / "docs" / "_realman_qa"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"{BASE}/",
    }
)

# robot_id -> PDP URL candidates (in order)
KNOWN: dict[int, list[str]] = {
    5220: [f"{BASE}/en/products/eco62.html"],
    5221: [f"{BASE}/en/products/eco63.html"],
    5222: [f"{BASE}/en/products/eco65.html"],
    5227: [f"{BASE}/en/products/rm65.html", f"{BASE}/en/products/rm65-b.html"],
    5228: [f"{BASE}/en/products/rm75.html"],
    5229: [f"{BASE}/en/products/rml63.html"],
    5230: [f"{BASE}/en/products/rx71.html"],
    5231: [f"{BASE}/en/products/rx75.html"],
    5219: [f"{BASE}/en/products/dual-arm-lift.html"],
    5232: [f"{BASE}/en/products/single-arm-lift.html"],
    5224: [
        f"{BASE}/en/products/realbot-humanoid.html",
        f"{BASE}/en/products/realbot-01.html",
        f"{BASE}/en/products/realbot.html",
    ],
    5225: [f"{BASE}/en/products/realbot-l2.html"],
    5226: [f"{BASE}/en/products/realbot-s2.html"],
    5223: [f"{BASE}/en/products/four-steer-chassis.html"],
    5233: [
        f"{BASE}/en/products/dual-wheel-chassis.html",
        f"{BASE}/en/products/two-wheel-chassis.html",
    ],
}

LOGO_HINTS = (
    "logo",
    "favicon",
    "icon",
    "sprite",
    "avatar",
    "wechat",
    "qrcode",
    "qr-code",
    "share",
)


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.imgs: list[dict[str, str]] = []
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag == "a" and "href" in ad:
            self.hrefs.append(ad["href"])
        if tag == "meta":
            prop = (ad.get("property") or ad.get("name") or "").lower()
            if prop in ("og:image", "twitter:image", "og:image:url") and ad.get("content"):
                self.meta[prop] = ad["content"]
        if tag == "img":
            self.imgs.append(
                {
                    "src": ad.get("src") or ad.get("data-src") or ad.get("data-original") or "",
                    "srcset": ad.get("srcset") or "",
                    "alt": ad.get("alt") or "",
                    "class": ad.get("class") or "",
                }
            )


def encode_url_path(url: str) -> str:
    """Percent-encode non-ASCII path segments."""
    parts = urlsplit(url)
    # encode each path segment but keep slashes
    segs = parts.path.split("/")
    enc = "/".join(quote(seg, safe="!$&'()*+,;=:@-~.") for seg in segs)
    return urlunsplit((parts.scheme, parts.netloc, enc, parts.query, parts.fragment))


def fetch(url: str, method: str = "GET", **kw) -> requests.Response | None:
    try:
        safe = encode_url_path(url) if "://" in url else url
        return SESSION.request(method, safe, timeout=45, allow_redirects=True, **kw)
    except requests.RequestException as e:
        print(f"  ERROR {method} {url!r}: {e}", file=sys.stderr)
        return None


def collect_product_links(html: str, base: str) -> list[str]:
    p = LinkCollector()
    try:
        p.feed(html)
    except Exception:
        pass
    out: list[str] = []
    seen: set[str] = set()
    candidates = list(p.hrefs)
    candidates += re.findall(
        r'href=["\']([^"\']*?/en/products/[^"\']+\.html)', html, re.I
    )
    for h in candidates:
        full = urljoin(base, h).split("#")[0]
        path = urlparse(full).path.lower()
        if "/en/products/" in path and path.endswith(".html"):
            if full not in seen:
                seen.add(full)
                out.append(full)
    return sorted(out)


def extract_image_candidates(html: str, page_url: str) -> list[tuple[int, str]]:
    """Return (priority, url) sorted later by score."""
    p = LinkCollector()
    try:
        p.feed(html)
    except Exception:
        pass
    scored: list[tuple[int, str]] = []

    def add(u: str, boost: int = 0) -> None:
        if not u or u.startswith("data:"):
            return
        full = urljoin(page_url, u.strip())
        low = full.lower()
        if any(h in low for h in LOGO_HINTS):
            return
        if not re.search(r"\.(jpg|jpeg|png|webp)(?:$|\?)", low.split("#")[0]):
            return
        scored.append((boost, full))

    for k in ("og:image", "twitter:image", "og:image:url"):
        if k in p.meta:
            add(p.meta[k], 100_000)

    for img in p.imgs:
        boost = 0
        alt = (img.get("alt") or "").lower()
        src = img.get("src") or ""
        if "main" in alt or "hero" in alt or "standard" in alt:
            boost += 200_000
        if "products-images" in src.lower() or "product" in src.lower():
            boost += 80_000
        if "thumb" in src.lower() or "angle" in alt:
            boost -= 30_000
        add(src, boost)
        if img.get("srcset"):
            for part in img["srcset"].split(","):
                bit = part.strip().split()[0] if part.strip() else ""
                add(bit, boost)

    for m in re.finditer(
        r'(?:src|href|content|data-src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']',
        html,
        re.I,
    ):
        add(m.group(1), 10_000 if "products-images" in m.group(1).lower() else 0)

    # dedupe keep max boost
    best: dict[str, int] = {}
    for boost, u in scored:
        best[u] = max(best.get(u, -10**9), boost)
    return sorted(((b, u) for u, b in best.items()), key=lambda x: -x[0])


def verify_image(url: str) -> tuple[bool, int, str, int]:
    r = fetch(url, "HEAD")
    if r is not None and r.status_code == 200:
        ct = r.headers.get("Content-Type", "")
        cl = int(r.headers.get("Content-Length") or 0)
        if ct.startswith("image") and cl > 20_000:
            return True, r.status_code, ct, cl
        if ct.startswith("image") and cl == 0:
            # fall through to GET
            pass
        elif not ct.startswith("image") or r.status_code >= 400:
            pass
        elif cl and cl <= 20_000:
            return False, r.status_code, ct, cl

    r = fetch(url, "GET")
    if r is None:
        return False, 0, "", 0
    ct = r.headers.get("Content-Type", "")
    cl = len(r.content)
    ok = r.status_code == 200 and ct.startswith("image") and cl > 20_000
    # stash body for reuse via _last_body
    verify_image.last_body = r.content if ok else None  # type: ignore[attr-defined]
    verify_image.last_ct = ct  # type: ignore[attr-defined]
    return ok, r.status_code, ct, cl


verify_image.last_body = None  # type: ignore[attr-defined]
verify_image.last_ct = ""  # type: ignore[attr-defined]


def pick_and_download(robot_id: int, page_url: str, html: str) -> dict | None:
    cands = extract_image_candidates(html, page_url)
    print(f"  candidates ({len(cands)}):")
    verified: list[tuple[int, str, str, int, bytes]] = []
    for boost, u in cands[:25]:
        verify_image.last_body = None  # type: ignore[attr-defined]
        ok, status, ct, cl = verify_image(u)
        safe_disp = u.encode("ascii", "backslashreplace").decode("ascii")
        print(f"    [{'OK' if ok else 'no'}] {status} {cl}B {ct} boost={boost} {safe_disp[:140]}")
        if ok:
            body = verify_image.last_body  # type: ignore[attr-defined]
            if body is None:
                r = fetch(u, "GET")
                if not r or r.status_code != 200:
                    continue
                body = r.content
                ct = r.headers.get("Content-Type", ct)
                cl = len(body)
            if len(body) <= 20_000:
                continue
            verified.append((boost + cl, u, ct, cl, body))
    if not verified:
        return None
    verified.sort(key=lambda x: -x[0])
    _, best_url, ct, cl, data = verified[0]
    ext = ".jpg"
    low = best_url.lower()
    ct_l = (ct or "").lower()
    if "png" in ct_l or low.endswith(".png"):
        ext = ".png"
    elif "webp" in ct_l or low.endswith(".webp"):
        ext = ".webp"
    fname = f"{robot_id}{ext}"
    (OUT_DIR / fname).write_bytes(data)
    print(f"  SAVED {fname} ({len(data)} bytes)")
    return {
        "url": best_url,
        "file": fname,
        "bytes": len(data),
        "content_type": ct,
        "page": page_url,
    }


def resolve_page(robot_id: int) -> tuple[str | None, str | None]:
    for url in KNOWN.get(robot_id, []):
        print(f"  try {url}")
        r = fetch(url)
        if r is None:
            continue
        if r.status_code == 404:
            print("    404")
            continue
        if r.status_code != 200:
            print(f"    status {r.status_code}")
            continue
        if len(r.text) < 800:
            print("    body too short")
            continue
        # detect charset
        r.encoding = r.apparent_encoding or "utf-8"
        return url, r.text
    return None, None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    product_links: list[str] = []

    print("=== Discover product links ===")
    for src in (CORE_PRODUCTS, f"{BASE}/", f"{BASE}/en/products/eco62.html"):
        print(f"  fetch {src}")
        r = fetch(src)
        if not r or r.status_code != 200:
            print(f"    fail {r.status_code if r else None}")
            continue
        r.encoding = r.apparent_encoding or "utf-8"
        found = collect_product_links(r.text, src)
        print(f"    found {len(found)}")
        for pl in found:
            if pl not in product_links:
                product_links.append(pl)

    # also list any from KNOWN that aren't discovered
    for urls in KNOWN.values():
        for u in urls:
            if u not in product_links:
                # probe existence later; still list attempted known
                pass

    print(f"\n=== /en/products/*.html links ({len(product_links)}) ===")
    for pl in sorted(product_links):
        print(f"  {pl}")

    heroes: dict[str, dict] = {}
    for rid in sorted(KNOWN.keys()):
        print(f"\n=== robot {rid} ===")
        page, html = resolve_page(rid)
        if not page or html is None:
            print("  NO PAGE FOUND")
            continue
        print(f"  page: {page}")
        info = pick_and_download(rid, page, html)
        if info:
            heroes[str(rid)] = {k: info[k] for k in ("url", "file", "bytes", "content_type")}
            heroes[str(rid)]["page"] = info["page"]
        else:
            print("  NO HERO IMAGE")

    out_json = OUT_DIR / "heroes.json"
    # store without page in the required schema; keep page as extra is fine
    dump = {
        rid: {k: v for k, v in meta.items() if k in ("url", "file", "bytes", "content_type")}
        for rid, meta in heroes.items()
    }
    # also keep page for QA in a sidecar field - user asked for url,file,bytes,content_type
    # Include page as helpful - actually stick to requested schema
    out_json.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== heroes.json ===")
    print(json.dumps(dump, indent=2, ensure_ascii=False))
    print(f"\nWrote {out_json}")
    print(f"Downloaded {len(dump)} / {len(KNOWN)} robots")

    index_path = OUT_DIR / "product_links.json"
    index_path.write_text(json.dumps(sorted(product_links), indent=2), encoding="utf-8")
    print(f"Wrote {index_path}")


if __name__ == "__main__":
    main()
