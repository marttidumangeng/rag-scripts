"""Measure the DEPTH opportunity: how many robot models do under-covered
companies actually list on their own sites, versus how many we hold?

Turns the "maybe 5 each" assumption behind the 654-company depth estimate
into a measured per-company yield.

Method
------
Random stratified sample of companies holding 0-3 robots WITH a website on
file. Sampling is deliberately random, NOT hand-picked: the population
genuinely contains component suppliers and conglomerates that correctly have
zero robots (FAULHABER, motor makers, materials firms). Cherry-picking the
recognizable robot brands would produce a number that cannot be extrapolated.

For each company, enumerate candidate product pages by:
  1. sitemap.xml (plus sitemap-index children) — the most reliable
     enumeration of a site's own pages, and the thing round-1's miner never
     used. Round 1 read the homepage plus ONE listing page, capped at 40
     links, which structurally cannot see a paginated catalogue.
  2. homepage product/catalogue link mining as a fallback.

IMPORTANT: the counts here are an UPPER BOUND on models. A product-path URL
may be an accessory, a category page, a spare part or a localisation
duplicate. Sample URLs are emitted per company precisely so the number can
be eyeballed rather than trusted blind. Read-only; nothing is imported.
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env()

BASELINE = _HERE / "staging" / "reports" / "prod_baseline.json"
OUT = _HERE / "staging" / "reports" / "depth-opportunity-sizing.json"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# URL path segments that indicate an individual product page.
PRODUCT_PATH_RE = re.compile(
    r"/(product|products|produkt|produkte|produit|producto|prodotto|"
    r"robot|robots|roboter|cobot|cobots|model|models|series|"
    r"machine|machines|equipment|solutions?/[^/]+/[^/]+)/",
    re.I,
)
# Paths that are clearly NOT an individual product.
NON_PRODUCT_RE = re.compile(
    r"/(news|blog|press|article|event|career|job|contact|about|support|"
    r"download|privacy|terms|legal|cookie|search|tag|category/?$|page/\d+|"
    r"wp-content|wp-json|feed|author|comment)",
    re.I,
)
ACCESSORY_RE = re.compile(
    r"(spare|accessor|cable|connector|bracket|mount-kit|manual|datasheet|"
    r"software|licen[cs]e|training|service-plan|warranty)",
    re.I,
)


def get(url: str, sess: requests.Session, timeout: int = 15) -> requests.Response | None:
    try:
        r = sess.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def sitemap_urls(base: str, sess: requests.Session, budget: int = 6) -> tuple[list[str], str]:
    """Collect URLs from sitemap.xml, following one level of sitemap-index.
    Returns (urls, status) where status explains failures for honest reporting."""
    root = re.match(r"(https?://[^/]+)", base)
    if not root:
        return [], "bad_url"
    origin = root.group(1)
    seen: list[str] = []
    tried = []
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/robots.txt"):
        r = get(origin + path, sess)
        if not r:
            continue
        tried.append(path)
        if path == "/robots.txt":
            found = re.findall(r"(?i)^sitemap:\s*(\S+)", r.text, re.M)
            for f in found[:budget]:
                rr = get(f, sess)
                if rr:
                    seen.extend(_parse_sitemap(rr.text, sess, budget))
            continue
        seen.extend(_parse_sitemap(r.text, sess, budget))
        if seen:
            break
    if not seen:
        return [], ("no_sitemap" if not tried else "sitemap_empty")
    return list(dict.fromkeys(seen)), "ok"


def _parse_sitemap(text: str, sess: requests.Session, budget: int) -> list[str]:
    out: list[str] = []
    cleaned = re.sub(r'\sxmlns="[^"]+"', "", text, count=1)
    try:
        rootel = ET.fromstring(cleaned)
    except ET.ParseError:
        return out
    # sitemap index -> fetch children (bounded)
    children = [e.text.strip() for e in rootel.findall(".//sitemap/loc") if e.text]
    if children:
        for c in children[:budget]:
            rr = get(c, sess)
            if rr:
                out.extend(_parse_sitemap(rr.text, sess, 0))
        return out
    out.extend(e.text.strip() for e in rootel.findall(".//url/loc") if e.text)
    return out


def classify(urls: list[str], origin_host: str) -> dict[str, Any]:
    prod, accessory, rejected = [], [], 0
    for u in urls:
        host = urlparse(u).netloc.replace("www.", "").lower()
        if origin_host and host and origin_host not in host:
            continue
        path = urlparse(u).path
        if not path or path == "/":
            continue
        if NON_PRODUCT_RE.search(path):
            rejected += 1
            continue
        if not PRODUCT_PATH_RE.search(path + "/"):
            rejected += 1
            continue
        if ACCESSORY_RE.search(path):
            accessory.append(u)
            continue
        prod.append(u)
    return {"product_like": prod, "accessory_like": accessory, "rejected": rejected}


def main() -> None:
    seed = 20260801
    n_zero, n_low = 12, 12

    b = json.loads(BASELINE.read_text(encoding="utf-8"))
    cos = {c["id"]: c for c in b["companies"]}
    cnt: Counter = Counter()
    for r in b["robots"]:
        cid = r.get("company_ref") or r.get("company_id")
        if isinstance(cid, dict):
            cid = cid.get("id")
        cnt[cid] += 1

    zero = [c for cid, c in cos.items() if cnt.get(cid, 0) == 0 and c.get("website")]
    low = [c for cid, c in cos.items() if 1 <= cnt.get(cid, 0) <= 3 and c.get("website")]

    rnd = random.Random(seed)
    sample = [("zero", c) for c in rnd.sample(zero, min(n_zero, len(zero)))]
    sample += [("low", c) for c in rnd.sample(low, min(n_low, len(low)))]

    print(f"population: {len(zero)} zero-robot + {len(low)} low(1-3) companies with websites")
    print(f"sampling {len(sample)} at random (seed {seed})\n", flush=True)

    sess = requests.Session()
    results = []
    for i, (stratum, c) in enumerate(sample, 1):
        site = c["website"]
        if "://" not in site:
            site = "https://" + site
        host = urlparse(site).netloc.replace("www.", "").lower()
        held = cnt.get(c["id"], 0)

        urls, status = sitemap_urls(site, sess)
        cls = classify(urls, host)
        n_prod = len(cls["product_like"])

        row = {
            "stratum": stratum,
            "company": c.get("name"),
            "website": site,
            "robots_held": held,
            "sitemap_status": status,
            "sitemap_urls_total": len(urls),
            "product_like": n_prod,
            "accessory_like": len(cls["accessory_like"]),
            "sample_product_urls": cls["product_like"][:6],
        }
        results.append(row)
        print(f"[{i}/{len(sample)}] {c.get('name','?')[:38]:40} held={held:2} "
              f"sitemap={status:13} product_like={n_prod:4}", flush=True)
        time.sleep(0.5)

    ok = [r for r in results if r["sitemap_status"] == "ok"]
    with_products = [r for r in ok if r["product_like"] > 0]
    counts = sorted(r["product_like"] for r in with_products)
    median = counts[len(counts) // 2] if counts else 0
    mean = round(sum(counts) / len(counts), 1) if counts else 0

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "population": {"zero_robot_with_site": len(zero), "low_1_3_with_site": len(low),
                       "total_under_covered": len(zero) + len(low)},
        "sampled": len(sample),
        "sitemap_reachable": len(ok),
        "sitemap_unreachable": len(results) - len(ok),
        "with_product_pages": len(with_products),
        "product_like_median": median,
        "product_like_mean": mean,
        "caveat": "product_like is an UPPER BOUND — a product-path URL may be an "
                  "accessory, category page, spare part or locale duplicate. "
                  "Eyeball sample_product_urls before trusting any extrapolation.",
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nsitemap reachable: {len(ok)}/{len(results)}   "
          f"with product pages: {len(with_products)}")
    print(f"product_like per company — median {median}, mean {mean}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
