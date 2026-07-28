"""Compare Realman (882) inventory vs OEM product catalog for missing variants."""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

COMPANY_ID = 882
BASE = "https://www.realman-robotics.com"
OUT = Path(__file__).resolve().parent / "staging" / "reports" / "realman-variant-gap.json"

# Known EN product pages (arms + mobiles) from prior enrich work.
KNOWN_PRODUCT_PATHS = [
    "/en/products/rm65.html",
    "/en/products/rm75.html",
    "/en/products/rml63.html",
    "/en/products/eco62.html",
    "/en/products/eco63.html",
    "/en/products/eco65.html",
    "/en/products/rx71.html",
    "/en/products/rx75.html",
    "/en/products/realbot-01.html",
    "/en/products/realbot-l2.html",
    "/en/products/realbot-s2.html",
    "/en/products/",
]

UA = {
    "User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(url: str) -> str:
    try:
        r = requests.get(url, headers=UA, timeout=45)
        if r.ok:
            return r.text
    except requests.RequestException:
        pass
    return ""


def list_db_robots(client: ResearchApiClient) -> list[dict]:
    rows: list[dict] = []
    for status in (
        "pending_review",
        "approved",
        "published",
        "rejected",
        "draft",
    ):
        page = 1
        while True:
            data = client._get(
                "robots/robots/",
                params={
                    "company_ref": COMPANY_ID,
                    "status": status,
                    "page": page,
                    "page_size": 50,
                },
            )
            batch = data.get("results") or []
            rows.extend(batch)
            if not data.get("next") or not batch:
                break
            page += 1
            time.sleep(0.05)
    # de-dupe by id
    by_id: dict[int, dict] = {}
    for r in rows:
        by_id[int(r["id"])] = r
    return list(by_id.values())


def discover_product_links(html: str) -> set[str]:
    links = set()
    for m in re.finditer(r'href=["\']([^"\']*products/[^"\']+\.html)["\']', html, re.I):
        links.add(urljoin(BASE, m.group(1)))
    return links


def extract_variant_hints(html: str, page_url: str) -> list[dict]:
    """Pull Standard / Force / Vision variant signals from PDP HTML."""
    hints: list[dict] = []
    # Chinese + EN edition markers in prop paths and text
    patterns = [
        (r"标准版|Standard", "standard"),
        (r"六维力|Six[- ]?Axis Force|Force", "force"),
        (r"视觉|Vision", "vision"),
    ]
    found = set()
    for pat, key in patterns:
        if re.search(pat, html, re.I):
            found.add(key)
    # model family from URL slug
    slug = page_url.rstrip("/").split("/")[-1].replace(".html", "").lower()
    for key in sorted(found) or ["base"]:
        hints.append({"family": slug, "variant": key, "page_url": page_url})
    return hints


def normalize_name(name: str) -> str:
    n = (name or "").casefold()
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return " ".join(n.split())


def main() -> int:
    client = ResearchApiClient()
    robots = list_db_robots(client)
    status_counts = Counter((r.get("status") or "?") for r in robots)
    print("DB robots", len(robots), dict(status_counts))

    # Crawl product index + known pages
    seed_urls = {urljoin(BASE, p) for p in KNOWN_PRODUCT_PATHS}
    index = fetch(f"{BASE}/en/products/")
    if not index:
        index = fetch(f"{BASE}/en/")
    seed_urls |= discover_product_links(index)
    # also CN products hub if present
    for extra in (f"{BASE}/products/", f"{BASE}/"):
        seed_urls |= discover_product_links(fetch(extra))

    product_pages: dict[str, str] = {}
    for url in sorted(seed_urls):
        if "realman" not in url.lower():
            continue
        html = fetch(url)
        if html:
            product_pages[url] = html
            seed_urls |= discover_product_links(html)
        time.sleep(0.15)

    # Second pass for newly discovered
    for url in sorted(seed_urls - set(product_pages)):
        if not url.endswith(".html"):
            continue
        html = fetch(url)
        if html:
            product_pages[url] = html
        time.sleep(0.15)

    print("OEM product pages fetched", len(product_pages))

    oem_variants: list[dict] = []
    for url, html in sorted(product_pages.items()):
        if "/products/" not in url or not url.endswith(".html"):
            continue
        # skip pure hubs if no model slug
        slug = url.rstrip("/").split("/")[-1].replace(".html", "")
        if slug in ("products", "index", "en"):
            continue
        oem_variants.extend(extract_variant_hints(html, url))

    # Expected SKU names (human labels we use in CRM)
    expected: list[dict] = []
    for v in oem_variants:
        fam = v["family"].upper().replace("REALBOT-", "RealBot-")
        # nicer family label
        fam_map = {
            "rm65": "RM65",
            "rm75": "RM75",
            "rml63": "RML63",
            "eco62": "ECO62",
            "eco63": "ECO63",
            "eco65": "ECO65",
            "rx71": "RX71",
            "rx75": "RX75",
            "realbot-01": "RealBot-01",
            "realbot-l2": "RealBot-L2",
            "realbot-s2": "RealBot-S2",
        }
        label = fam_map.get(v["family"], fam)
        if v["variant"] == "standard":
            name = f"{label} Standard"
        elif v["variant"] == "force":
            name = f"{label} Six-Axis Force"
        elif v["variant"] == "vision":
            name = f"{label} Vision"
        else:
            name = label
        expected.append({**v, "expected_name": name, "family_label": label})

    # Deduplicate expected by (family, variant)
    uniq: dict[tuple[str, str], dict] = {}
    for e in expected:
        uniq[(e["family"], e["variant"])] = e
    expected = list(uniq.values())

    # Mobile / chassis pages may not be .html products — scan for lift/chassis mentions
    # From prior inventory we know these names exist in DB:
    extra_oem_names = [
        "Dual-Arm Lift",
        "Single-Arm Lift",
        "Four-Steer Four-Drive Chassis",
        "Two-Wheel Differential Chassis",
    ]

    db_by_norm = {normalize_name(r.get("name") or ""): r for r in robots}
    db_names = sorted(db_by_norm.keys())

    matched = []
    missing = []
    for e in sorted(expected, key=lambda x: x["expected_name"]):
        n = normalize_name(e["expected_name"])
        # also try base name without variant for 'base'
        hit = db_by_norm.get(n)
        if not hit and e["variant"] == "base":
            # match any robot whose name starts with family
            fam = normalize_name(e["family_label"])
            for kn, r in db_by_norm.items():
                if kn == fam or kn.startswith(fam + " "):
                    hit = r
                    break
        if hit:
            matched.append({"expected": e["expected_name"], "id": hit["id"], "db_name": hit.get("name"), "status": hit.get("status")})
        else:
            missing.append(e)

    # Also: DB rows that look like near-duplicate bases of Standard variants
    duplicates_suspect = []
    by_family = defaultdict(list)
    for r in robots:
        name = r.get("name") or ""
        m = re.match(r"^(RM65|RM75|RML63|ECO62|ECO63|ECO65|RX71|RX75|RealBot-01|RealBot-L2|RealBot-S2)\b", name, re.I)
        if m:
            by_family[m.group(1).upper()].append(r)
    for fam, rs in by_family.items():
        names = [x.get("name") for x in rs]
        has_base = any(normalize_name(n) == normalize_name(fam) for n in names)
        has_std = any("standard" in (n or "").casefold() for n in names)
        if has_base and has_std:
            duplicates_suspect.append(
                {
                    "family": fam,
                    "rows": [{"id": x["id"], "name": x.get("name"), "status": x.get("status")} for x in rs],
                }
            )

    # Reverse: OEM page exists but only base in DB without Standard/Force when OEM has both
    variant_gaps = []
    for fam, rs in by_family.items():
        keys = {normalize_name(x.get("name") or "") for x in rs}
        # check expected for this family
        fam_key = fam.lower()
        for e in expected:
            if e["family"] != fam_key:
                continue
            en = normalize_name(e["expected_name"])
            if en not in keys and e["variant"] != "base":
                # if only base exists, still count as missing named variant
                if not any(en == k for k in keys):
                    variant_gaps.append(
                        {
                            "family": fam,
                            "missing_variant": e["expected_name"],
                            "have": [x.get("name") for x in rs],
                        }
                    )

    report = {
        "company_id": COMPANY_ID,
        "db_count": len(robots),
        "status_counts": dict(status_counts),
        "db_robots": [
            {
                "id": r["id"],
                "name": r.get("name"),
                "status": r.get("status"),
                "url": r.get("url"),
            }
            for r in sorted(robots, key=lambda x: int(x["id"]))
        ],
        "oem_pages": sorted(product_pages.keys()),
        "expected_variants": [
            {"name": e["expected_name"], "family": e["family"], "variant": e["variant"], "page": e["page_url"]}
            for e in sorted(expected, key=lambda x: x["expected_name"])
        ],
        "matched": matched,
        "missing_expected": [
            {"name": e["expected_name"], "family": e["family"], "variant": e["variant"], "page": e["page_url"]}
            for e in missing
        ],
        "variant_gaps": variant_gaps,
        "duplicate_base_and_standard": duplicates_suspect,
        "known_extra_mobile_names": extra_oem_names,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n=== DB inventory ===")
    for r in report["db_robots"]:
        print(f"{r['id']:5d} {r['status']:15s} {r['name']}")
    print("\n=== Expected OEM variants ===")
    for e in report["expected_variants"]:
        print(f"  {e['name']:40s} ({e['variant']}) {e['page']}")
    print("\n=== Missing expected ===")
    for e in report["missing_expected"]:
        print(f"  MISSING {e['name']} ← {e['page']}")
    print("\n=== Base+Standard duplicate suspects ===")
    for d in duplicates_suspect:
        print(f"  {d['family']}: {[x['name'] for x in d['rows']]}")
    print("\n=== Variant gaps ===")
    for g in variant_gaps:
        print(f"  {g}")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
