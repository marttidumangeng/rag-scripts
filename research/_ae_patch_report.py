"""Patch ae-heroes/scrape-report.json with domain fetch + enrichment scope."""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
REPORT = BASE / "staging/reports/ae-heroes/scrape-report.json"
HEADERS = {"User-Agent": "RobotAIGeek-ResearchAgent/1.0"}


def fetch_domain(url: str) -> dict:
    out = {"url": url, "status": None, "final_url": None, "html_len": 0, "title": None, "js_shell": False, "error": None, "product_pages": []}
    try:
        r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
        out["status"] = r.status_code
        out["final_url"] = r.url
        out["html_len"] = len(r.text)
        m = re.search(r"<title[^>]*>([^<]+)</title>", r.text, re.I)
        out["title"] = m.group(1).strip() if m else None
        out["js_shell"] = out["html_len"] < 5000 or bool(re.search(r'id=["\']app["\']|react-root|__NEXT_DATA__', r.text, re.I))
        links = sorted(set(re.findall(r'href=["\']([^"\']+)["\']', r.text, re.I)))
        for href in links:
            low = href.lower()
            if "/product" in low and ".html" in low:
                if href.startswith("/"):
                    href = f"https://www.automationar.com{href}"
                if href.startswith("http") and href not in out["product_pages"]:
                    out["product_pages"].append(href)
        out["product_pages"] = out["product_pages"][:40]
    except requests.RequestException as e:
        out["error"] = str(e)
    return out


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))

    domain_fetch = {
        "aerobot_cc": {
            "urls_tried": [
                "https://www.aerobot.cc",
                "https://www.aerobot.cc/en",
                "https://www.aerobot.cc/en/products",
                "https://www.aerobot.cc/products",
            ],
            "dns_resolves": False,
            "error": "NameResolutionError — www.aerobot.cc does not resolve (dead DNS)",
            "note": "Company CRM website is aerobot.cc but live storefront is automationar.com",
        },
        "automationar_com": fetch_domain("https://www.automationar.com"),
    }
    ae_listing = fetch_domain("https://www.automationar.com/products/ae-robot-arm.html")
    domain_fetch["automationar_ae_listing"] = ae_listing

    brand_counts = Counter(r.get("brand_class") or "unknown" for r in report["robots"])
    ae_own = [r for r in report["robots"] if r.get("brand_class") == "ae_own"]
    reseller = [r for r in report["robots"] if r.get("brand_class") in ("fanuc", "aubo", "jaka", "ur", "youibot")]
    other = [r for r in report["robots"] if r.get("brand_class") not in ("ae_own", "fanuc", "aubo", "jaka", "ur", "youibot")]

    # CRM gaps: no image or no features in prod (from probe)
    crm_gapped_ids = {3534, 4810, 4811, 4812, 4813, 4814, 4815, 4816, 4817, 4818, 4819, 4820, 4821, 4822, 4823, 4824, 4825, 4826, 4827, 4828, 4829, 4830, 4831, 4832, 4833, 4834}
    ae_own_gapped = [r for r in ae_own if r["id"] in crm_gapped_ids or not r.get("features")]

    yt_candidates: list[dict] = []
    seen_urls: set[str] = set()
    reject = re.compile(
        r"(?i)\b(tutorial|training|electrical interface|teach pendant|program editor|"
        r"authorization import|version update|file backup|ethernet communication)\b",
    )
    for r in report["robots"]:
        for v in r.get("youtube") or []:
            url = v.get("url") or ""
            title = v.get("title") or ""
            if not url or url in seen_urls or not title:
                continue
            if reject.search(title):
                continue
            seen_urls.add(url)
            yt_candidates.append(
                {
                    "url": url,
                    "title": title,
                    "robot_name": r["name"],
                    "brand_class": r.get("brand_class"),
                }
            )

    ae_yt = [v for v in yt_candidates if v["brand_class"] == "ae_own" or re.search(r"(?i)\bae\b|automationar|air\d", v["title"])]
    ae_yt = [v for v in ae_yt if not re.search(r"(?i)\b(aubo|jaka|fanuc|ur\d|universal robot)\b", v["title"])]

    report["domain_fetch"] = domain_fetch
    report["brand_classification"] = {
        "ae_own": {"count": brand_counts["ae_own"], "models": sorted({r["name"] for r in ae_own})},
        "reseller": {
            "count": sum(brand_counts.get(b, 0) for b in ("fanuc", "aubo", "jaka", "ur", "youibot")),
            "by_brand": {b: brand_counts.get(b, 0) for b in ("fanuc", "aubo", "jaka", "ur", "youibot")},
        },
        "other": {"count": len(other), "models": sorted({r["name"] for r in other})},
    }
    report["youtube_candidates"] = {
        "all_filtered": yt_candidates[:30],
        "ae_own_filtered": ae_yt,
    }
    report["enrichment_recommendation"] = {
        "preferred_source": "automationar.com (aerobot.cc DNS dead)",
        "scope": "ae_own_only",
        "rationale": (
            "19 of 41 CRM robots are AE-branded own products (AIR*, SCARA, Delta AR-*, Trans, AE-25, AE20 Cobot). "
            "22 are third-party resales (AUBO, Fanuc, JAKA, UR, Youibot) — enrich from OEM/reseller pages, not as AE products. "
            "Recommend fix_ae_robots.py targeting ~19 AE-own robots first; defer reseller SKUs or tag as reseller."
        ),
        "ae_own_count": len(ae_own),
        "reseller_count": len(reseller),
        "total_crm_robots": len(report["robots"]),
        "crm_gapped_count": len(crm_gapped_ids),
        "heroes_downloaded": sum(1 for r in report["robots"] if r.get("hero_file")),
        "ae_own_with_hero": sum(1 for r in ae_own if r.get("hero_file")),
        "duplicate_ae_skus": [
            "1446/4831 AIR3-A",
            "1448/4832 AIR7L-B",
            "1449/4833 AIR8-A",
            "1450/4834 AIR10-A",
            "1451/3534 AIR20-A",
        ],
    }
    report["patched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Patched", REPORT)
    print(json.dumps(report["enrichment_recommendation"], indent=2))
    print("YouTube AE candidates:", len(ae_yt))
    for v in ae_yt[:8]:
        print(" ", v["title"][:90])


if __name__ == "__main__":
    main()
